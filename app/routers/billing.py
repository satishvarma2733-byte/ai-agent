"""Plans, checkout and invoices (Razorpay / Stripe), plus the providers' webhooks."""
import json
import logging
from datetime import timezone
from typing import List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.auth_deps import RoleChecker, get_current_user
from app.core.database import get_db
from app.core.permissions import at_least
from app.core.settings import settings
from app.models.billing import BillingEvent, BillingInvoice, BillingSubscription
from app.models.tenant import Tenant
from app.models.user import User
from app.schemas.common import UTCDateTime
from app.services import audit, billing

logger = logging.getLogger("billing-router")

router = APIRouter(tags=["Billing"])

# Paying for a plan commits the business to spending money, so only the workspace owner does it.
require_owner = RoleChecker(["Owner"])
MAX_WEBHOOK_BYTES = 512 * 1024


class PriceOut(BaseModel):
    provider: str
    amount: float
    currency: str
    available: bool  # the server has this provider's keys


class PlanOut(BaseModel):
    id: str
    name: str
    minutes_included: int
    features: List[str]
    prices: List[PriceOut]


class SubscriptionOut(BaseModel):
    provider: str
    plan_id: str
    plan_name: str
    status: str
    current_period_end: Optional[UTCDateTime] = None
    cancel_at_period_end: bool


class InvoiceOut(BaseModel):
    id: str
    provider: str
    number: Optional[str] = None
    amount: float
    currency: str
    status: str
    url: Optional[str] = None
    period_start: Optional[UTCDateTime] = None
    period_end: Optional[UTCDateTime] = None
    created_at: UTCDateTime


class UsageOut(BaseModel):
    """This month's usage against the plan; a None limit means unlimited."""
    minutes_used: int
    minutes_limit: Optional[int] = None
    agents: int
    agents_limit: Optional[int] = None
    members: int
    members_limit: Optional[int] = None
    outbound_blocked: bool


class BillingOut(BaseModel):
    plan: str
    usage: UsageOut
    subscription: Optional[SubscriptionOut] = None
    plans: List[PlanOut]
    invoices: List[InvoiceOut]
    can_manage: bool


class CheckoutIn(BaseModel):
    plan_id: str
    provider: Literal["razorpay", "stripe"]


class RedirectOut(BaseModel):
    url: str


def _utc(value):
    return value.replace(tzinfo=timezone.utc) if value else None


def _billing(db: Session, user: User) -> BillingOut:
    tenant = db.get(Tenant, user.tenant_id)
    plans = billing.load_plans()
    sub = db.query(BillingSubscription).filter(BillingSubscription.tenant_id == user.tenant_id).first()
    sub_out = None
    if sub is not None and sub.status != "created":
        plan = next((p for p in plans if p.id == sub.plan_id), None)
        sub_out = SubscriptionOut(provider=sub.provider, plan_id=sub.plan_id, plan_name=plan.name if plan else sub.plan_id,
                                  status=sub.status, current_period_end=_utc(sub.current_period_end),
                                  cancel_at_period_end=sub.cancel_at_period_end)
    invoices = db.query(BillingInvoice).filter(BillingInvoice.tenant_id == user.tenant_id).order_by(
        BillingInvoice.created_at.desc()).limit(50).all()
    from app.services import plan_limits
    u = plan_limits.usage(db, tenant)
    return BillingOut(
        plan=tenant.plan if tenant else billing.FREE_PLAN,
        usage=UsageOut(minutes_used=u.minutes_used, minutes_limit=u.minutes_limit, agents=u.agents,
                       agents_limit=u.agents_limit, members=u.members, members_limit=u.members_limit,
                       outbound_blocked=u.outbound_blocked),
        subscription=sub_out,
        plans=[PlanOut(id=p.id, name=p.name, minutes_included=p.minutes_included, features=p.features,
                       prices=[PriceOut(provider=pr.provider, amount=pr.amount, currency=pr.currency,
                                        available=billing.provider_configured(pr.provider)) for pr in p.prices.values()])
               for p in plans if p.prices],  # plans without prices (e.g. "free") only set limits
        invoices=[InvoiceOut(id=i.id, provider=i.provider, number=i.number, amount=i.amount_minor / 100, currency=i.currency,
                             status=i.status, url=i.url, period_start=_utc(i.period_start), period_end=_utc(i.period_end),
                             created_at=_utc(i.created_at)) for i in invoices],
        can_manage=at_least(user.role, "Owner"),
    )


def _return_url() -> str:
    return f"{settings.frontend_base_url}/billing"


def _subscription(db: Session, tenant_id: str) -> BillingSubscription:
    sub = db.query(BillingSubscription).filter(BillingSubscription.tenant_id == tenant_id).first()
    if sub is None or sub.status == "created":
        raise HTTPException(status_code=404, detail="This workspace has no paid plan.")
    return sub


@router.get("/api/billing", response_model=BillingOut)
def billing_overview(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """The workspace's plan, subscription, invoices and the plans it can buy."""
    return _billing(db, current_user)


@router.post("/api/billing/checkout", response_model=RedirectOut)
def checkout(payload: CheckoutIn, request: Request, db: Session = Depends(get_db), current_user: User = Depends(require_owner)):
    """The provider's payment page for a plan. The plan starts when the provider confirms payment."""
    plan = billing.find_plan(payload.plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="Unknown plan")
    tenant = db.get(Tenant, current_user.tenant_id)
    try:
        url = billing.start_checkout(db, tenant, current_user.email, plan, payload.provider, _return_url())
    except billing.BillingError as exc:
        raise HTTPException(status_code=409 if "already has" in str(exc) else 400, detail=str(exc))
    except Exception as exc:  # network failure talking to the provider
        logger.error("[BILLING] Checkout failed for %s: %s", tenant.id, exc)
        raise HTTPException(status_code=502, detail="The payment provider couldn't be reached. Try again.")
    audit.record(db, action="billing_checkout_started", entity="BillingSubscription", tenant_id=tenant.id, user_id=current_user.id,
                 details={"plan": plan.id, "provider": payload.provider}, request=request)
    return RedirectOut(url=url)


@router.post("/api/billing/portal", response_model=RedirectOut)
def billing_portal(db: Session = Depends(get_db), current_user: User = Depends(require_owner)):
    """Stripe's customer portal: card, invoices, plan changes and cancellation."""
    sub = _subscription(db, current_user.tenant_id)
    try:
        return RedirectOut(url=billing.portal_url(sub, _return_url()))
    except billing.BillingError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/api/billing/cancel", response_model=BillingOut)
def cancel_plan(request: Request, db: Session = Depends(get_db), current_user: User = Depends(require_owner)):
    """Cancel at the end of the paid period; the plan stays on until then."""
    sub = _subscription(db, current_user.tenant_id)
    try:
        billing.cancel_at_period_end(db, sub)
    except billing.BillingError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    audit.record(db, action="billing_cancel_requested", entity="BillingSubscription", entity_id=sub.id,
                 tenant_id=current_user.tenant_id, user_id=current_user.id, request=request)
    return _billing(db, current_user)


async def _webhook(request: Request, db: Session, provider: str, signature_ok, event_id_of, handler):
    raw = await request.body()
    if len(raw) > MAX_WEBHOOK_BYTES:
        raise HTTPException(status_code=413, detail="Body too large")
    if not signature_ok(raw):
        raise HTTPException(status_code=401, detail="Bad signature")
    try:
        event = json.loads(raw)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid JSON")
    event_id = event_id_of(event)
    if not event_id:
        raise HTTPException(status_code=400, detail="Missing event id")
    event_type = str(event.get("type") or event.get("event") or "")
    if not billing.first_delivery(db, provider, event_id, event_type):
        return {"status": "duplicate"}
    try:
        tenant_id = handler(db, event)
    except Exception as exc:
        # Forget the event so the provider's retry is processed.
        db.rollback()
        db.query(BillingEvent).filter(BillingEvent.provider == provider, BillingEvent.event_id == event_id).delete()
        db.commit()
        logger.error("[BILLING] %s event %s failed: %s", provider, event_id, exc)
        raise HTTPException(status_code=500, detail="Event not processed")
    if tenant_id:
        db.query(BillingEvent).filter(BillingEvent.provider == provider, BillingEvent.event_id == event_id).update({"tenant_id": tenant_id})
        db.commit()
    return {"status": "ok"}


@router.post("/api/billing/webhook/stripe", include_in_schema=False)
async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
    header = request.headers.get("stripe-signature")
    return await _webhook(request, db, "stripe", lambda raw: billing.stripe_signature_ok(raw, header),
                          lambda e: e.get("id"), billing.handle_stripe)


@router.post("/api/billing/webhook/razorpay", include_in_schema=False)
async def razorpay_webhook(request: Request, db: Session = Depends(get_db)):
    header = request.headers.get("x-razorpay-signature")
    event_header = request.headers.get("x-razorpay-event-id")

    def event_id(e: dict) -> str | None:
        # Razorpay's delivery id; fall back to the event and entity for older payloads.
        if event_header:
            return event_header
        entity = next(iter((e.get("payload") or {}).values()), {}).get("entity", {})
        return f"{e.get('event')}:{entity.get('id')}:{e.get('created_at')}" if entity.get("id") else None

    return await _webhook(request, db, "razorpay", lambda raw: billing.razorpay_signature_ok(raw, header), event_id,
                          billing.handle_razorpay)
