"""Dials pending campaign leads for running campaigns, respecting per-campaign concurrency."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from app.core.database import SessionLocal
from app.core.runtime_config import load_runtime_config
from app.models.call import CallLog
from app.models.campaign import Campaign, CampaignLead
from outbound_calls import dispatch_outbound_call

logger = logging.getLogger("campaign-worker")

POLL_SECONDS = 10
# A lead still "calling" after this long never reported back from the voice worker.
CALL_TIMEOUT = timedelta(minutes=20)


def _utcnow() -> datetime:
    # Naive UTC to match the naive DateTime columns.
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _claim_batch() -> list[dict]:
    """Advance campaign state and mark the next leads as calling. Returns dispatch jobs."""
    from app.services import notifications, plan_limits
    db = SessionLocal()
    jobs: list[dict] = []
    blocked: dict[str, bool] = {}
    try:
        now = _utcnow()
        for camp in db.query(Campaign).filter(Campaign.status == "running").all():
            if camp.tenant_id not in blocked:
                try:
                    plan_limits.check_outbound(db, camp.tenant_id)
                    blocked[camp.tenant_id] = False
                except plan_limits.LimitReached:
                    blocked[camp.tenant_id] = True
            if blocked[camp.tenant_id]:
                camp.status = "paused"
                notifications.notify(db, camp.tenant_id, notifications.managers(db, camp.tenant_id), kind="campaign_paused",
                                     title=f"Campaign \"{camp.name}\" paused: this month's call minutes are used up",
                                     body="Start it again after upgrading or next month.", link="/outbound")
                logger.info(f"[CAMPAIGN] Paused campaign {camp.id}: plan minutes used up")
                continue
            leads = db.query(CampaignLead).filter(CampaignLead.campaign_id == camp.id)

            for stale in leads.filter(CampaignLead.status == "calling").all():
                if stale.last_dispatched_at and now - stale.last_dispatched_at > CALL_TIMEOUT:
                    stale.status = "failed"
                    stale.outcome = stale.outcome or "no_answer"

            active = leads.filter(CampaignLead.status == "calling").count()
            pending = leads.filter(CampaignLead.status == "pending").order_by(CampaignLead.created_at).all()
            if not pending and active == 0:
                camp.status = "completed"
                logger.info(f"[CAMPAIGN] Completed campaign {camp.id}")
                continue

            for lead in pending[: max(0, camp.concurrency_limit - active)]:
                lead.status = "calling"
                lead.attempts += 1
                lead.last_dispatched_at = now
                jobs.append({
                    "campaign_lead_id": lead.id,
                    "campaign_id": camp.id,
                    "tenant_id": camp.tenant_id,
                    "agent_id": camp.agent_id,
                    "lead_id": lead.lead_id,
                    "phone": lead.phone,
                    "name": lead.name or "",
                    "retry_limit": camp.retry_limit,
                })
        db.commit()
    finally:
        db.close()
    return jobs


def _record_dispatch(job: dict, room: str | None, error: str | None) -> None:
    db = SessionLocal()
    try:
        lead = db.query(CampaignLead).filter(CampaignLead.id == job["campaign_lead_id"]).first()
        if not lead:
            return
        if error:
            retry = lead.attempts <= job["retry_limit"]
            lead.status = "pending" if retry else "failed"
            lead.outcome = None if retry else "failed"
            logger.error(f"[CAMPAIGN] Dispatch failed for lead {lead.id} (attempt {lead.attempts}): {error}")
        else:
            lead.call_room_id = room
            db.add(CallLog(
                tenant_id=job["tenant_id"],
                phone_number=lead.phone,
                caller_name=lead.name,
                direction="outbound",
                call_room_id=room,
                agent_id=job["agent_id"],
            ))
        db.commit()
    finally:
        db.close()


async def _dispatch(job: dict) -> None:
    try:
        config = await asyncio.to_thread(load_runtime_config)
        result = await dispatch_outbound_call(
            job["phone"],
            config=config,
            caller_name=job["name"],
            extra_metadata={
                "tenant_id": job["tenant_id"],
                "campaign_id": job["campaign_id"],
                "campaign_lead_id": job["campaign_lead_id"],
                "lead_id": job["lead_id"],
                "agent_id": job["agent_id"],
                "direction": "outbound",
            },
        )
        await asyncio.to_thread(_record_dispatch, job, result.get("room"), None)
    except Exception as exc:
        await asyncio.to_thread(_record_dispatch, job, None, str(exc))


async def campaign_worker_loop() -> None:
    logger.info("[WORKER] Campaign worker started.")
    while True:
        try:
            for job in await asyncio.to_thread(_claim_batch):
                asyncio.create_task(_dispatch(job))
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.error(f"[WORKER] Campaign worker error: {exc}")
        await asyncio.sleep(POLL_SECONDS)


_task: asyncio.Task | None = None


def start_campaign_worker() -> None:
    global _task
    if _task is None or _task.done():
        _task = asyncio.create_task(campaign_worker_loop())
