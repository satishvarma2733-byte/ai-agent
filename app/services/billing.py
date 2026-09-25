"""Paid plans through Razorpay (INR) or Stripe (international).

Plans come from a file the operator maintains (BILLING_PLANS_FILE, see configs/billing_plans.example.json):
each plan names the Razorpay plan and/or Stripe price that charges for it. Prices live in those dashboards;
the amounts in the file are only shown to customers. Checkout and card entry happen on the provider's own
pages; signed webhooks then set the subscription, the workspace's plan and its invoices.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import httpx
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.billing import BillingEvent, BillingInvoice, BillingSubscription
from app.models.tenant import Tenant

logger = logging.getLogger("billing")

STRIPE_API = "https://api.stripe.com/v1"
RAZORPAY_API = "https://api.razorpay.com/v1"
TIMEOUT = 20
FREE_PLAN = "Free"
STRIPE_SIGNATURE_TOLERANCE = 300
# A plan stays on while payment is being retried; it goes back to Free only when the subscription ends.
PLAN_ON = ("active", "past_due")


class BillingError(Exception):
    pass


@dataclass
class Price:
    provider: str
    provider_price_id: str  # Razorpay plan_… / Stripe price_…
    amount: float
    currency: str


@dataclass
class Limits:
    """What a plan allows; None means no limit."""
    minutes_per_month: int | None = None
    agents: int | None = None
    members: int | None = None


@dataclass
class Plan:
    id: str
    name: str
    minutes_included: int
    features: list[str] = field(default_factory=list)
    prices: dict[str, Price] = field(default_factory=dict)
    limits: Limits = field(default_factory=Limits)


def http() -> httpx.Client:
    """One client per call; tests replace this to intercept requests."""
    return httpx.Client(timeout=TIMEOUT)


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _from_unix(value) -> datetime | None:
    return datetime.fromtimestamp(int(value), tz=timezone.utc).replace(tzinfo=None) if value else None


# --- Configuration -------------------------------------------------------------------------------

def provider_configured(provider: str) -> bool:
    if provider == "stripe":
        return bool(os.environ.get("STRIPE_SECRET_KEY") and os.environ.get("STRIPE_WEBHOOK_SECRET"))
    if provider == "razorpay":
        return bool(os.environ.get("RAZORPAY_KEY_ID") and os.environ.get("RAZORPAY_KEY_SECRET")
                    and os.environ.get("RAZORPAY_WEBHOOK_SECRET"))
    return False


def load_plans() -> list[Plan]:
    path = Path(os.environ.get("BILLING_PLANS_FILE", "configs/billing_plans.json"))
    if not path.is_file():
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except ValueError as exc:
        logger.error("[BILLING] %s is not valid JSON: %s", path, exc)
        return []
    plans = []
    for item in raw.get("plans", []):
        prices = {}
        for provider, p in (item.get("prices") or {}).items():
            price_id = p.get("plan_id") if provider == "razorpay" else p.get("price_id")
            if provider in ("razorpay", "stripe") and price_id:
                prices[provider] = Price(provider, price_id, float(p.get("amount", 0)), str(p.get("currency", "")).upper())
        raw_limits = item.get("limits") or {}
        limits = Limits(**{k: (int(raw_limits[k]) if raw_limits.get(k) is not None else None)
                           for k in ("minutes_per_month", "agents", "members")})
        plans.append(Plan(id=str(item["id"]), name=str(item["name"]), minutes_included=int(item.get("minutes_included", 0)),
                          features=[str(f) for f in item.get("features", [])], prices=prices, limits=limits))
    return plans


def plan_for_workspace(tenant: Tenant, plans: list[Plan] | None = None) -> Plan | None:
    """The plan whose limits apply: the workspace's paid plan by name, or the "free" entry for Free workspaces."""
    plans = load_plans() if plans is None else plans
    name = (tenant.plan or FREE_PLAN).strip().lower()
    if name == FREE_PLAN.lower():
        return next((p for p in plans if p.id == "free"), None)
    return next((p for p in plans if p.name.lower() == name or p.id == name), None)


def find_plan(plan_id: str) -> Plan | None:
    return next((p for p in load_plans() if p.id == plan_id), None)


def plan_for_price(provider: str, provider_price_id: str | None) -> Plan | None:
    return next((p for p in load_plans() if provider in p.prices and p.prices[provider].provider_price_id == provider_price_id), None)


# --- Checkout, portal, cancel --------------------------------------------------------------------

def _stripe_auth() -> dict:
    return {"Authorization": f"Bearer {os.environ['STRIPE_SECRET_KEY']}"}


def _razorpay_auth() -> tuple[str, str]:
    return os.environ["RAZORPAY_KEY_ID"], os.environ["RAZORPAY_KEY_SECRET"]


def _raise(res: httpx.Response, what: str) -> None:
    if res.status_code < 400:
        return
    try:
        body = res.json()
        detail = (body.get("error") or {}).get("message") or (body.get("error") or {}).get("description") or res.text[:200]
    except ValueError:
        detail = res.text[:200]
    raise BillingError(f"{what} failed: {detail}")


def start_checkout(db: Session, tenant: Tenant, owner_email: str, plan: Plan, provider: str, return_url: str) -> str:
    """Create the provider checkout and return the URL to send the owner to."""
    if provider not in plan.prices:
        raise BillingError(f"The {plan.name} plan can't be paid with {provider}.")
    if not provider_configured(provider):
        raise BillingError(f"{provider.title()} payments aren't set up on this server.")
    sub = db.query(BillingSubscription).filter(BillingSubscription.tenant_id == tenant.id).first()
    if sub is not None and sub.status in PLAN_ON:
        raise BillingError("This workspace already has a paid plan. Manage or cancel it first.")
    price = plan.prices[provider]
    with http() as client:
        if provider == "stripe":
            customer = sub.provider_customer_id if sub and sub.provider == "stripe" else None
            if not customer:
                res = client.post(f"{STRIPE_API}/customers", headers=_stripe_auth(),
                                  data={"email": owner_email, "name": tenant.name, "metadata[tenant_id]": tenant.id})
                _raise(res, "Creating the Stripe customer")
                customer = res.json()["id"]
            res = client.post(f"{STRIPE_API}/checkout/sessions", headers=_stripe_auth(), data={
                "mode": "subscription", "customer": customer, "client_reference_id": tenant.id,
                "line_items[0][price]": price.provider_price_id, "line_items[0][quantity]": "1",
                "subscription_data[metadata][tenant_id]": tenant.id, "subscription_data[metadata][plan_id]": plan.id,
                "success_url": f"{return_url}?checkout=success", "cancel_url": f"{return_url}?checkout=cancelled",
            })
            _raise(res, "Starting Stripe checkout")
            url, provider_sub_id = res.json()["url"], None
        else:
            res = client.post(f"{RAZORPAY_API}/subscriptions", auth=_razorpay_auth(), json={
                "plan_id": price.provider_price_id, "total_count": 120, "customer_notify": 1,
                "notes": {"tenant_id": tenant.id, "plan_id": plan.id},
            })
            _raise(res, "Starting Razorpay checkout")
            body = res.json()
            url, provider_sub_id, customer = body["short_url"], body["id"], None
    if sub is None:
        sub = BillingSubscription(tenant_id=tenant.id, created_at=_now())
        db.add(sub)
    sub.provider, sub.plan_id, sub.provider_customer_id = provider, plan.id, customer
    sub.provider_subscription_id, sub.status, sub.cancel_at_period_end = provider_sub_id, "created", False
    sub.current_period_end, sub.updated_at = None, _now()
    db.commit()
    return url


def portal_url(sub: BillingSubscription, return_url: str) -> str:
    """Stripe's customer portal: card, invoices, plan changes and cancellation."""
    if sub.provider != "stripe" or not sub.provider_customer_id:
        raise BillingError("The billing portal is only available for Stripe subscriptions.")
    with http() as client:
        res = client.post(f"{STRIPE_API}/billing_portal/sessions", headers=_stripe_auth(),
                          data={"customer": sub.provider_customer_id, "return_url": return_url})
    _raise(res, "Opening the Stripe portal")
    return res.json()["url"]


def cancel_at_period_end(db: Session, sub: BillingSubscription) -> None:
    if sub.status not in PLAN_ON or not sub.provider_subscription_id:
        raise BillingError("There is no active subscription to cancel.")
    with http() as client:
        if sub.provider == "stripe":
            res = client.post(f"{STRIPE_API}/subscriptions/{sub.provider_subscription_id}", headers=_stripe_auth(),
                              data={"cancel_at_period_end": "true"})
        else:
            res = client.post(f"{RAZORPAY_API}/subscriptions/{sub.provider_subscription_id}/cancel", auth=_razorpay_auth(),
                              json={"cancel_at_cycle_end": 1})
    _raise(res, "Cancelling the subscription")
    sub.cancel_at_period_end, sub.updated_at = True, _now()
    db.commit()


# --- Webhooks ------------------------------------------------------------------------------------

def stripe_signature_ok(raw: bytes, header: str | None, now: float | None = None) -> bool:
    """Stripe-Signature: t=<unix>,v1=<hex HMAC-SHA256 of "t.body">. Old timestamps are refused (replays)."""
    secret = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
    parts = dict(p.split("=", 1) for p in (header or "").split(",") if "=" in p)
    signatures = [v for k, v in (p.split("=", 1) for p in (header or "").split(",") if "=" in p) if k == "v1"]
    try:
        stamp = int(parts.get("t", ""))
    except ValueError:
        return False
    if not secret or abs((now or time.time()) - stamp) > STRIPE_SIGNATURE_TOLERANCE:
        return False
    expected = hmac.new(secret.encode(), f"{stamp}.".encode() + raw, hashlib.sha256).hexdigest()
    return any(hmac.compare_digest(expected, s) for s in signatures)


def razorpay_signature_ok(raw: bytes, header: str | None) -> bool:
    secret = os.environ.get("RAZORPAY_WEBHOOK_SECRET", "")
    expected = hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
    return bool(secret and header) and hmac.compare_digest(expected, header)


def first_delivery(db: Session, provider: str, event_id: str, event_type: str) -> bool:
    """Record the event; False when it was already handled (providers retry deliveries)."""
    db.add(BillingEvent(provider=provider, event_id=event_id, event_type=event_type, received_at=_now()))
    try:
        db.commit()
        return True
    except IntegrityError:
        db.rollback()
        return False


_STRIPE_STATUS = {"active": "active", "trialing": "active", "past_due": "past_due", "unpaid": "past_due", "paused": "past_due",
                  "canceled": "ended", "incomplete_expired": "ended", "incomplete": "created"}
_RAZORPAY_STATUS = {"created": "created", "authenticated": "active", "active": "active", "pending": "past_due",
                    "halted": "past_due", "paused": "past_due", "cancelled": "ended", "completed": "ended", "expired": "ended"}


def _subscription_for(db: Session, provider: str, provider_sub_id: str | None, tenant_id: str | None) -> BillingSubscription | None:
    sub = None
    if provider_sub_id:
        sub = db.query(BillingSubscription).filter(BillingSubscription.provider_subscription_id == provider_sub_id).first()
    if sub is None and tenant_id:
        sub = db.query(BillingSubscription).filter(BillingSubscription.tenant_id == tenant_id).first()
        if sub is not None and sub.provider_subscription_id not in (None, provider_sub_id):
            return None  # an older subscription; this workspace has moved on
    return sub


def _apply(db: Session, sub: BillingSubscription, status: str, plan: Plan | None, period_end, cancel_at_end: bool) -> None:
    sub.status = status
    if plan is not None:
        sub.plan_id = plan.id
    sub.current_period_end = period_end or sub.current_period_end
    sub.cancel_at_period_end = cancel_at_end
    sub.updated_at = _now()
    tenant = db.get(Tenant, sub.tenant_id)
    if tenant is not None:
        current = plan or find_plan(sub.plan_id)
        tenant.plan = (current.name if current else sub.plan_id) if status in PLAN_ON else FREE_PLAN
    db.commit()


def _invoice(db: Session, tenant_id: str, provider: str, invoice_id: str, *, number, amount_minor, currency, status,
             url, period_start=None, period_end=None) -> None:
    row = db.query(BillingInvoice).filter(BillingInvoice.provider == provider, BillingInvoice.provider_invoice_id == invoice_id).first()
    if row is None:
        row = BillingInvoice(tenant_id=tenant_id, provider=provider, provider_invoice_id=invoice_id, created_at=_now())
        db.add(row)
    row.number, row.amount_minor, row.currency, row.status, row.url = number, int(amount_minor or 0), (currency or "").upper(), status, url
    row.period_start, row.period_end = period_start or row.period_start, period_end or row.period_end
    db.commit()


def handle_stripe(db: Session, event: dict) -> str | None:
    """Apply one Stripe event. Returns the workspace it concerned, if any."""
    kind, obj = event.get("type", ""), (event.get("data") or {}).get("object") or {}
    if kind == "checkout.session.completed" and obj.get("mode") == "subscription":
        sub = _subscription_for(db, "stripe", None, obj.get("client_reference_id"))
        if sub is None or sub.provider != "stripe":
            return None
        sub.provider_subscription_id, sub.provider_customer_id = obj.get("subscription"), obj.get("customer") or sub.provider_customer_id
        db.commit()
        return sub.tenant_id
    if kind.startswith("customer.subscription."):
        sub = _subscription_for(db, "stripe", obj.get("id"), (obj.get("metadata") or {}).get("tenant_id"))
        if sub is None:
            return None
        sub.provider_subscription_id = obj.get("id")
        items = (obj.get("items") or {}).get("data") or [{}]
        plan = plan_for_price("stripe", (items[0].get("price") or {}).get("id"))
        status = "ended" if kind == "customer.subscription.deleted" else _STRIPE_STATUS.get(obj.get("status"), "past_due")
        period_end = obj.get("current_period_end") or items[0].get("current_period_end")
        _apply(db, sub, status, plan, _from_unix(period_end), bool(obj.get("cancel_at_period_end")))
        return sub.tenant_id
    if kind in ("invoice.paid", "invoice.payment_failed", "invoice.finalized"):
        parent = (obj.get("parent") or {}).get("subscription_details") or {}
        sub = _subscription_for(db, "stripe", obj.get("subscription") or parent.get("subscription"), None)
        if sub is None:
            return None
        status = {"invoice.paid": "paid", "invoice.payment_failed": "failed"}.get(kind, "open")
        amount = obj.get("amount_paid") if kind == "invoice.paid" else obj.get("amount_due")
        _invoice(db, sub.tenant_id, "stripe", obj["id"], number=obj.get("number"), amount_minor=amount, currency=obj.get("currency"),
                 status=status, url=obj.get("hosted_invoice_url"), period_start=_from_unix(obj.get("period_start")),
                 period_end=_from_unix(obj.get("period_end")))
        return sub.tenant_id
    return None


def handle_razorpay(db: Session, event: dict) -> str | None:
    kind, payload = event.get("event", ""), event.get("payload") or {}
    if kind.startswith("subscription."):
        entity = (payload.get("subscription") or {}).get("entity") or {}
        sub = _subscription_for(db, "razorpay", entity.get("id"), (entity.get("notes") or {}).get("tenant_id"))
        if sub is None:
            return None
        plan = plan_for_price("razorpay", entity.get("plan_id"))
        status = _RAZORPAY_STATUS.get(entity.get("status"), "past_due")
        # Razorpay keeps a subscription active until the cycle ends after a cancel request; our flag remembers the request.
        _apply(db, sub, status, plan, _from_unix(entity.get("current_end")), sub.cancel_at_period_end and status in PLAN_ON)
        payment = (payload.get("payment") or {}).get("entity")
        if kind == "subscription.charged" and payment:
            _invoice(db, sub.tenant_id, "razorpay", payment.get("invoice_id") or payment["id"], number=payment.get("invoice_id"),
                     amount_minor=payment.get("amount"), currency=payment.get("currency"), status="paid", url=None,
                     period_start=_from_unix(entity.get("current_start")), period_end=_from_unix(entity.get("current_end")))
        return sub.tenant_id
    if kind.startswith("invoice."):
        entity = (payload.get("invoice") or {}).get("entity") or {}
        sub = _subscription_for(db, "razorpay", entity.get("subscription_id"), None)
        if sub is None:
            return None
        status = {"paid": "paid", "expired": "failed", "cancelled": "failed"}.get(entity.get("status"), "open")
        _invoice(db, sub.tenant_id, "razorpay", entity["id"], number=entity.get("receipt") or entity["id"],
                 amount_minor=entity.get("amount_paid") or entity.get("amount"), currency=entity.get("currency"), status=status,
                 url=entity.get("short_url"), period_start=_from_unix(entity.get("billing_start")),
                 period_end=_from_unix(entity.get("billing_end")))
        return sub.tenant_id
    return None
