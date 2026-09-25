import json
import asyncio
import logging
import time
from sqlalchemy.orm import Session
from datetime import datetime, timezone
from app.models.workflow import Workflow, WorkflowLog
from app.models.lead import Lead, LeadActivity
from app.models.call import CallLog
from outbound_calls import dispatch_outbound_call
from app.services.placeholders import render

logger = logging.getLogger("workflow-engine")

# Events the API emits. The builder offers exactly these, so a saved workflow can always fire.
TRIGGERS = ("lead_created", "lead_status_changed", "appointment_booked", "appointment_reminder", "call_completed",
            "call_missed", "webhook_received")
# Events about one appointment: its details fill {{appointment.*}} placeholders, and the contact becomes a lead if new.
APPOINTMENT_EVENTS = ("appointment_booked", "appointment_reminder")
# A missed call from an unknown number still needs following up, so it creates the lead.
CREATES_LEAD = ("call_missed",)
POLL_SECONDS = 2
# Names saved by earlier builder versions.
LEGACY_TRIGGERS = {"new_lead": "lead_created", "pipeline_change": "lead_status_changed", "status_changed": "lead_status_changed"}
ACTIONS = ("ai_call", "send_email", "send_whatsapp", "update_crm", "assign_lead", "create_reminder", "delay", "call_webhook")
MAX_DELAY_SECONDS = 3600
# Lead fields a workflow may set; everything else (tenant, ids, timestamps) is off limits.
UPDATABLE_FIELDS = {"status", "score", "assigned_agent", "follow_up_date", "notes", "objection"}


def _appointment_id(event_type: str, ref: str | None) -> str | None:
    """appointment_booked events carry the appointment id as their ref; reminders carry "id|workflow|start"."""
    if not ref:
        return None
    return ref.split("|", 1)[0] if event_type == "appointment_reminder" else ref


def _workspace_name(db: Session, tenant_id: str) -> str:
    from app.models.tenant import Tenant
    tenant = db.get(Tenant, tenant_id)
    return tenant.name if tenant else ""


def normalize_trigger(name: str) -> str:
    return LEGACY_TRIGGERS.get(name, name)


def _stored_triggers(event_type: str) -> list[str]:
    return [event_type] + [old for old, new in LEGACY_TRIGGERS.items() if new == event_type]


class WorkflowEngine:
    """Runs workflows for events in the durable `workflow_events` queue, which the API and the
    voice worker both write to."""
    def __init__(self):
        self.loop_task = None
        self.running: set[asyncio.Task] = set()

    def start(self):
        if not self.loop_task:
            self.loop_task = asyncio.create_task(self._worker_loop())

    async def _worker_loop(self):
        from app.services import appointment_reminders, call_summaries
        last_reminder_check = last_summary_check = 0.0
        while True:
            try:
                if time.monotonic() - last_reminder_check >= appointment_reminders.CHECK_SECONDS:
                    last_reminder_check = time.monotonic()
                    await asyncio.to_thread(appointment_reminders.queue_due)
                if time.monotonic() - last_summary_check >= call_summaries.CHECK_SECONDS:
                    last_summary_check = time.monotonic()
                    await asyncio.to_thread(call_summaries.send_due)
                await self.poll_once()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[WorkflowEngine] Error in worker loop: {e}")
            await asyncio.sleep(POLL_SECONDS)

    async def poll_once(self) -> int:
        """Claim queued events and start a run for each (runs may wait between steps, so they don't block polling)."""
        from app.services import workflow_events
        from app.core.database import SessionLocal

        def claim():
            db = SessionLocal()
            try:
                return [(e.id, e.tenant_id, e.event_type, e.lead_id, e.phone, e.ref) for e in workflow_events.claim_batch(db)]
            finally:
                db.close()

        claimed = await asyncio.to_thread(claim)
        for item in claimed:
            task = asyncio.create_task(self._run_event(*item))
            self.running.add(task)
            task.add_done_callback(self.running.discard)
        return len(claimed)

    async def _run_event(self, event_id: str, tenant_id: str, event_type: str, lead_id: str | None, phone: str | None,
                         ref: str | None = None):
        from app.services import workflow_events
        from app.core.database import SessionLocal
        from app.models.workflow import WorkflowEvent
        error = None
        try:
            if not lead_id:
                db = SessionLocal()
                try:
                    lead = workflow_events.find_lead(db, tenant_id, phone)
                    if lead is None and event_type in CREATES_LEAD:
                        lead = workflow_events.create_lead_for_caller(db, tenant_id, phone)
                    if lead is None and event_type in APPOINTMENT_EVENTS:
                        lead = workflow_events.create_lead_for_appointment(db, tenant_id, _appointment_id(event_type, ref))
                    lead_id = lead.id if lead else None
                finally:
                    db.close()
            if lead_id:
                await self._execute_workflows(event_type, lead_id, tenant_id, ref)
        except Exception as exc:
            error = str(exc)
            logger.error(f"[WorkflowEngine] Event {event_id} failed: {exc}")
        db = SessionLocal()
        try:
            event = db.query(WorkflowEvent).filter(WorkflowEvent.id == event_id).first()
            if event:
                workflow_events.finish(db, event, error)
        finally:
            db.close()

    def dispatch_event(self, event_type: str, lead: Lead, db: Session):
        from app.services import workflow_events
        workflow_events.emit(db, lead.tenant_id, event_type, lead_id=lead.id)

    async def _run_action(self, act_type: str, config: dict, lead: Lead, tenant_id: str, db: Session,
                          appointment=None) -> str:
        """Perform one action and describe what actually happened."""
        if act_type == "ai_call":
            from app.core.runtime_config import load_runtime_config as _load_runtime_config
            result = await dispatch_outbound_call(lead.phone, config=_load_runtime_config(), caller_name=lead.name,
                                                  extra_metadata={"tenant_id": tenant_id})
            db.add(CallLog(tenant_id=tenant_id, phone_number=lead.phone, caller_name=lead.name,
                           direction="outbound", call_room_id=result.get("room")))
            db.commit()
            return f"AI call placed to {lead.phone}"

        if act_type == "send_email":
            if not lead.email:
                return "email skipped: the lead has no email address"
            from app.services.mailer import deliver
            workspace = _workspace_name(db, tenant_id)
            subject = render(str(config.get("subject") or "Following up on your enquiry"), lead, workspace, appointment)
            body = render(str(config.get("body") or f"Hi {lead.name},\n\nThank you for your interest. We will be in touch shortly."),
                          lead, workspace, appointment)
            outcome = deliver(lead.email, subject, body)
            db.add(LeadActivity(lead_id=lead.id, tenant_id=tenant_id, activity_type="crm_update",
                                title="Workflow email", description=f"'{subject}' to {lead.email}: {outcome}"))
            db.commit()
            return f"email to {lead.email}: {outcome}"

        if act_type == "send_whatsapp":
            from app.services import whatsapp
            workspace = _workspace_name(db, tenant_id)
            name = str(config.get("template") or "").strip()
            if name:
                params = [render(p, lead, workspace, appointment) for p in str(config.get("params") or "").splitlines() if p.strip()]
                template = whatsapp.Template(name, str(config.get("language") or "en").strip(), tuple(params))
                text = None
            else:
                template, text = None, render(str(config.get("message") or ""), lead, workspace, appointment).strip()
                if not text:
                    return "WhatsApp skipped: no message or template configured"
            try:
                whatsapp.send(db, tenant_id, lead.phone, text=text, template=template, lead=lead, source="workflow")
            except (whatsapp.WhatsAppNotConnected, whatsapp.WhatsAppError) as exc:
                # A failed step fails the run, so managers are notified.
                raise RuntimeError(f"WhatsApp to {lead.phone} not sent: {exc}") from exc
            return f"WhatsApp {'template ' + name if template else 'message'} sent to {lead.phone}"

        if act_type == "update_crm":
            field, value = config.get("field"), config.get("value")
            if isinstance(field, str) and field.startswith("custom."):
                from app.services.lead_fields import FieldValueError, merge_values
                try:
                    lead.custom_fields = merge_values(db, tenant_id, lead.custom_fields, {field[7:]: value}) or None
                except FieldValueError as exc:
                    return f"CRM update skipped: {exc}"
                db.commit()
                return f"set {field[7:]} to {value!r}"
            if field not in UPDATABLE_FIELDS:
                return f"CRM update skipped: field '{field}' is not configured or not allowed"
            setattr(lead, field, value)
            db.commit()
            return f"set {field} to {value!r}"

        if act_type == "assign_lead":
            from sqlalchemy import func
            from app.models.user import User
            agent = str(config.get("agent") or "").strip()
            if not agent:
                return "assignment skipped: no team member configured"
            member = db.query(User).filter(
                User.tenant_id == tenant_id, User.status == "active",
                (func.lower(User.email) == agent.lower()) | (func.lower(User.name) == agent.lower()),
            ).first()
            if member is None:
                return f"assignment skipped: no active member named or emailed '{agent}'"
            lead.assigned_user_id = member.id
            lead.assigned_agent = member.name
            db.commit()
            return f"assigned to {member.name}"

        if act_type == "create_reminder":
            text = config.get("text") or "Follow up with lead"
            db.add(LeadActivity(lead_id=lead.id, tenant_id=tenant_id, activity_type="crm_update",
                                title="Task Reminder Scheduled", description=f"Reminder: {text}."))
            db.commit()
            return "reminder added to the lead timeline"

        if act_type == "call_webhook":
            from app.models.workflow import WebhookEndpoint
            from app.services import webhooks
            url = str(config.get("url") or "").strip()
            if not url:
                return "webhook skipped: no URL configured"
            endpoint = db.query(WebhookEndpoint).filter(WebhookEndpoint.tenant_id == tenant_id).first()
            secret = webhooks.open_secret(endpoint.signing_secret) if endpoint else None
            lead_data = {c: getattr(lead, c) for c in ("id", "name", "phone", "email", "company", "status", "score",
                                                       "assigned_agent", "follow_up_date", "notes", "custom_fields")}
            try:
                return await asyncio.to_thread(webhooks.post_event, url, secret, "workflow.step", {"workspace_id": tenant_id, "lead": lead_data})
            except webhooks.UnsafeUrl as exc:
                return f"webhook skipped: {exc}"

        if act_type == "delay":
            return f"waited {int(config.get('delay') or 0)}s"

        return f"'{act_type}' skipped: this action is not available yet"

    async def _execute_workflows(self, event_type: str, lead_id: str, tenant_id: str, ref: str | None = None):
        from app.core.database import SessionLocal
        from app.models.appointment import Appointment
        from app.services import appointment_reminders
        db = SessionLocal()
        try:
            lead = db.query(Lead).filter(Lead.id == lead_id, Lead.tenant_id == tenant_id).first()
            if not lead:
                return

            query = db.query(Workflow).filter(
                Workflow.trigger_event.in_(_stored_triggers(event_type)),
                Workflow.is_active == True,
                Workflow.tenant_id == tenant_id
            )
            appointment = None
            if event_type in APPOINTMENT_EVENTS and ref:
                appointment = db.query(Appointment).filter(Appointment.id == _appointment_id(event_type, ref),
                                                           Appointment.tenant_id == tenant_id).first()
            if event_type == "appointment_reminder":
                parsed = appointment_reminders.parse_ref(ref)
                # Each reminder belongs to one workflow, and lapses if the appointment was cancelled or moved since.
                if parsed is None or appointment is None or appointment.status != "scheduled" \
                        or appointment.scheduled_start != parsed[2]:
                    return
                query = query.filter(Workflow.id == parsed[1])
            workflows = query.all()

            for wf in workflows:
                log = WorkflowLog(
                    workflow_id=wf.id,
                    tenant_id=tenant_id,
                    triggered_at=datetime.now(timezone.utc),
                    status="running",
                    message=f"Triggered by '{event_type}' on lead '{lead.name}'."
                )
                db.add(log)
                db.commit()
                db.refresh(log)

                steps: list[str] = []
                try:
                    # visual_layout only stores the canvas.
                    actions = [a for a in json.loads(wf.actions_json) if a.get("type") != "visual_layout"]
                    for action in actions:
                        act_config = action.get("config") or {}
                        delay_seconds = min(max(int(act_config.get("delay") or 0), 0), MAX_DELAY_SECONDS)
                        if delay_seconds > 0:
                            await asyncio.sleep(delay_seconds)
                        condition_status = act_config.get("condition_status")
                        if condition_status and lead.status != condition_status:
                            steps.append(f"{action.get('type')}: skipped (lead status is not {condition_status})")
                            continue
                        steps.append(await self._run_action(action.get("type"), act_config, lead, tenant_id, db, appointment))

                    log.status = "success"
                    log.message = "; ".join(steps) or "No actions to run."
                    db.commit()

                except Exception as inner_e:
                    db.rollback()
                    log.status = "failed"
                    log.message = "; ".join(steps + [f"failed: {inner_e}"])
                    db.commit()
                    from app.services import notifications
                    notifications.notify(db, tenant_id, notifications.managers(db, tenant_id), kind="workflow_failed",
                                         title=f"Workflow \"{wf.name}\" failed", body=log.message[:500], link="/workflows")

        except Exception as e:
            logger.error(f"[WorkflowEngine] Execution error: {e}")
        finally:
            db.close()

workflow_engine = WorkflowEngine()
