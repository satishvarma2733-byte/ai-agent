import csv
import io
import json
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.auth_deps import RoleChecker, get_current_user
from app.core.database import get_db
from app.models.campaign import Campaign, CampaignLead
from app.models.lead import Lead
from app.models.user import User
from app.schemas.campaign import CampaignCreate, CampaignDetailOut, CampaignLeadOut, CampaignOut
from db_backend import normalize_phone_number

router = APIRouter(prefix="/api/crm/campaigns", tags=["Campaigns"])

_FORMULA_START = ("=", "+", "-", "@", "\t", "\r")


def csv_safe(value) -> str:
    """Stop spreadsheets from running cell values as formulas (CSV/formula injection)."""
    text = "" if value is None else str(value)
    return "'" + text if text.startswith(_FORMULA_START) else text

# Voice-worker outcomes → UI buckets. "completed" means a connected conversation (> 15 s).
_QUALIFIED_OUTCOMES = {"completed"}
_SCHEDULED_OUTCOMES = {"booked"}


def _get_campaign(db: Session, campaign_id: str, tenant_id: str) -> Campaign:
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id, Campaign.tenant_id == tenant_id).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return campaign


def _lead_out(lead: CampaignLead) -> CampaignLeadOut:
    try:
        custom = json.loads(lead.custom_fields_json or "{}")
    except ValueError:
        custom = {}
    return CampaignLeadOut(
        id=lead.id, name=lead.name, phone=lead.phone, status=lead.status,
        outcome=lead.outcome, attempts=lead.attempts, custom_fields=custom,
    )


def _campaign_out(campaign: Campaign, leads: List[CampaignLead]) -> dict:
    return dict(
        id=campaign.id, name=campaign.name, status=campaign.status, agent_id=campaign.agent_id,
        concurrency_limit=campaign.concurrency_limit, retry_limit=campaign.retry_limit,
        created_at=campaign.created_at,
        total_leads=len(leads),
        completed_leads=sum(1 for l in leads if l.status == "completed"),
        qualified_leads=sum(1 for l in leads if l.outcome in _QUALIFIED_OUTCOMES),
        scheduled_leads=sum(1 for l in leads if l.outcome in _SCHEDULED_OUTCOMES),
        failed_leads=sum(1 for l in leads if l.status == "failed"),
    )


@router.get("", response_model=List[CampaignOut])
def list_campaigns(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    campaigns = db.query(Campaign).filter(Campaign.tenant_id == current_user.tenant_id).order_by(Campaign.created_at.desc()).all()
    leads_by_campaign: dict[str, list[CampaignLead]] = {c.id: [] for c in campaigns}
    if campaigns:
        for lead in db.query(CampaignLead).filter(CampaignLead.campaign_id.in_(leads_by_campaign.keys())).all():
            leads_by_campaign[lead.campaign_id].append(lead)
    return [_campaign_out(c, leads_by_campaign[c.id]) for c in campaigns]


@router.post("", response_model=CampaignOut, status_code=status.HTTP_201_CREATED)
def create_campaign(
    payload: CampaignCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(RoleChecker(["Admin", "Manager"])),
):
    tenant_id = current_user.tenant_id
    campaign = Campaign(
        tenant_id=tenant_id, name=payload.name.strip(), agent_id=payload.agent_id,
        concurrency_limit=payload.concurrency_limit, retry_limit=payload.retry_limit, status="queued",
    )
    db.add(campaign)
    db.flush()

    leads: list[CampaignLead] = []
    seen: set[str] = set()
    for item in payload.leads:
        phone = normalize_phone_number(item.phone)
        if not phone or phone in seen:
            continue
        seen.add(phone)
        crm_lead = db.query(Lead).filter(
            Lead.tenant_id == tenant_id, Lead.phone == phone, Lead.deleted_at.is_(None)
        ).first()
        if not crm_lead:
            crm_lead = Lead(tenant_id=tenant_id, name=item.name.strip() or phone, phone=phone, email=item.email)
            db.add(crm_lead)
            db.flush()
        lead = CampaignLead(
            tenant_id=tenant_id, campaign_id=campaign.id, lead_id=crm_lead.id,
            name=item.name.strip(), phone=phone, custom_fields_json=json.dumps(item.custom_fields or {}),
        )
        db.add(lead)
        leads.append(lead)

    db.commit()
    db.refresh(campaign)
    return _campaign_out(campaign, leads)


@router.get("/{campaign_id}", response_model=CampaignDetailOut)
def get_campaign(campaign_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    campaign = _get_campaign(db, campaign_id, current_user.tenant_id)
    leads = db.query(CampaignLead).filter(CampaignLead.campaign_id == campaign.id).order_by(CampaignLead.created_at).all()
    return {**_campaign_out(campaign, leads), "leads": [_lead_out(l) for l in leads]}


def _set_status(campaign_id: str, new_status: str, allowed_from: set[str], db: Session, user: User) -> dict:
    campaign = _get_campaign(db, campaign_id, user.tenant_id)
    if campaign.status not in allowed_from:
        raise HTTPException(status_code=409, detail=f"Cannot change a {campaign.status} campaign to {new_status}")
    campaign.status = new_status
    db.commit()
    return {"status": "ok", "campaign_status": new_status}


@router.post("/{campaign_id}/start")
def start_campaign(campaign_id: str, db: Session = Depends(get_db), current_user: User = Depends(RoleChecker(["Admin", "Manager"]))):
    from app.services import plan_limits
    try:
        plan_limits.check_outbound(db, current_user.tenant_id)
    except plan_limits.LimitReached as exc:
        raise HTTPException(status_code=402, detail=str(exc))
    return _set_status(campaign_id, "running", {"queued", "paused"}, db, current_user)


@router.post("/{campaign_id}/pause")
def pause_campaign(campaign_id: str, db: Session = Depends(get_db), current_user: User = Depends(RoleChecker(["Admin", "Manager"]))):
    return _set_status(campaign_id, "paused", {"running"}, db, current_user)


@router.delete("/{campaign_id}")
def delete_campaign(campaign_id: str, db: Session = Depends(get_db), current_user: User = Depends(RoleChecker(["Admin", "Manager"]))):
    campaign = _get_campaign(db, campaign_id, current_user.tenant_id)
    db.query(CampaignLead).filter(CampaignLead.campaign_id == campaign.id).delete()
    db.delete(campaign)
    db.commit()
    return {"status": "ok", "success": True}


@router.get("/{campaign_id}/export")
def export_campaign(campaign_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    campaign = _get_campaign(db, campaign_id, current_user.tenant_id)
    leads = db.query(CampaignLead).filter(CampaignLead.campaign_id == campaign.id).order_by(CampaignLead.created_at).all()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["ID", "Name", "Phone", "Status", "Outcome", "Attempts", "Custom Fields"])
    for lead in leads:
        writer.writerow([csv_safe(v) for v in (lead.id, lead.name, lead.phone, lead.status, lead.outcome or "uncalled",
                                               lead.attempts, lead.custom_fields_json or "{}")])
    output.seek(0)
    return StreamingResponse(
        output,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=campaign-{campaign.id}-results.csv"},
    )
