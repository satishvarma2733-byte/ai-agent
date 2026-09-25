import asyncio
import logging
import db_backend as db
from outbound_calls import dispatch_outbound_call

logger = logging.getLogger("campaign-worker")

_WORKER_TASK: asyncio.Task | None = None
_WORKER_RUNNING = False

async def _process_running_campaigns():
    campaigns = db.fetch_campaigns()
    running_campaigns = [c for c in campaigns if c.get("status") == "running"]
    
    for camp in running_campaigns:
        camp_id = camp.get("id")
        concurrency_limit = camp.get("concurrency_limit") or 5
        agent_id = camp.get("agent_id")
        
        # Fetch all leads for this campaign
        leads = db.fetch_campaign_leads(camp_id)
        
        # Calculate active calls and pending list
        active_leads = [l for l in leads if l.get("campaign_status") == "calling"]
        pending_leads = [l for l in leads if l.get("campaign_status") == "pending"]
        
        # If no pending leads left and no active calls, campaign is completed
        if not pending_leads and not active_leads:
            logger.info(f"[CAMPAIGN] Completed campaign {camp_id}")
            camp["status"] = "completed"
            db.save_campaign(camp)
            continue
            
        # Determine how many slots are open
        available_slots = concurrency_limit - len(active_leads)
        if available_slots <= 0:
            # We are at capacity, wait for current calls to finish
            continue
            
        # Dispatch calls for open slots
        to_dispatch = pending_leads[:available_slots]
        for lead in to_dispatch:
            lead_id = lead.get("id")
            phone = lead.get("phone")
            name = lead.get("name") or "Valued Lead"
            
            logger.info(f"[CAMPAIGN] Dispatching outbound call to {phone} for lead {lead_id} in campaign {camp_id}")
            
            # 1. Update lead status to calling
            db.update_campaign_lead_status(lead_id, campaign_status="calling")
            
            # 2. Dispatch LiveKit agent call
            async def run_dispatch(p=phone, n=name, lid=lead_id, cid=camp_id, aid=agent_id):
                try:
                    # Retrieve agent parameters to use correct personality config
                    agents = db.fetch_agents()
                    target_agent = next((a for a in agents if a.get("id") == aid), None)
                    agent_name = target_agent.get("name") if target_agent else "vobiz-demo-agent"
                    
                    extra_meta = {
                        "lead_id": str(lid),
                        "campaign_id": str(cid),
                        "agent_id": str(aid) if aid else None
                    }
                    
                    res = await dispatch_outbound_call(
                        phone_number=p,
                        caller_name=n,
                        extra_metadata=extra_meta,
                        agent_name=agent_name.lower().replace(" ", "-") # Format agent name for LiveKit dispatch lookup
                    )
                    logger.info(f"[CAMPAIGN] LiveKit dispatch succeeded for lead {lid}: {res}")
                except Exception as exc:
                    logger.error(f"[CAMPAIGN] LiveKit dispatch failed for lead {lid}: {exc}")
                    # Update status to failed
                    db.update_campaign_lead_status(
                        lid,
                        campaign_status="failed",
                        campaign_outcome="failed"
                    )
                    
            asyncio.create_task(run_dispatch())

async def campaign_worker_loop():
    global _WORKER_RUNNING
    _WORKER_RUNNING = True
    logger.info("[WORKER] Campaign background worker started.")
    _consecutive_errors = 0
    
    while _WORKER_RUNNING:
        try:
            await _process_running_campaigns()
            _consecutive_errors = 0
        except Exception as exc:
            _consecutive_errors += 1
            if _consecutive_errors <= 3:
                logger.error(f"[WORKER] Error in campaign queue worker loop: {exc}")
            elif _consecutive_errors == 4:
                logger.warning("[WORKER] Suppressing repeated campaign worker errors (table may not exist yet)")
        await asyncio.sleep(10)

def start_campaign_worker():
    global _WORKER_TASK, _WORKER_RUNNING
    if _WORKER_TASK is not None and not _WORKER_TASK.done():
        logger.info("[WORKER] Worker is already active.")
        return
    _WORKER_TASK = asyncio.create_task(campaign_worker_loop())

def stop_campaign_worker():
    global _WORKER_RUNNING
    _WORKER_RUNNING = False
    logger.info("[WORKER] Stop signal sent to campaign background worker.")
