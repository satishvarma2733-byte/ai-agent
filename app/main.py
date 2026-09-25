import logging
from datetime import datetime, timezone
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi import HTTPException
from fastapi.responses import FileResponse

from app.core.database import engine, Base, SessionLocal
from app.core.settings import settings
from app.core.security_headers import SecurityHeadersMiddleware
from app.services import media_files
from app.core.security import get_password_hash
from app.models.user import User
from app.models.lead import Lead, LeadActivity
from app.models.call import CallLog, CallTurnMetric
from app.models.appointment import Appointment
from app.models.cms import CMSPage, CMSPrompt, CMSFaq, CMSMedia
from app.models.workflow import Workflow, WorkflowLog
from app.models.audit import AuditLog
from app.models.agent import Agent
from app.models.tenant import Tenant
from app.models.campaign import Campaign, CampaignLead

# Import routers
from app.routers import (
    auth, leads, calls, appointments,
    cms, workflows, analytics, agents,
    kb, inbound, contacts, campaigns, system, team, workspace, lead_fields, webhooks, notifications, calendar, whatsapp, billing
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("avnagent-backend")

if settings.sentry_dsn:
    import sentry_sdk

    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.app_env,
        traces_sample_rate=0.1,
        send_default_pii=False,  # transcripts and phone numbers must not leave via error reports
    )
    logger.info("Sentry error reporting enabled.")

# Apply schema migrations (Alembic). Replaces the old create_all() bootstrap.
from app.core.migrate import run_migrations
from app.core.tenancy import warn_if_rls_bypassed
run_migrations()
warn_if_rls_bypassed()

# Seed a workspace Owner only when explicitly configured, or with local-only defaults.
# Production must set SEED_ADMIN_EMAIL / SEED_ADMIN_PASSWORD or create the first user via signup.
db = SessionLocal()
try:
    seed_email = settings.seed_admin_email.strip().lower()
    seed_password = settings.seed_admin_password.strip()
    if not (seed_email and seed_password) and settings.is_local:
        seed_email, seed_password = "admin@company.com", "adminpassword"

    owner_exists = db.query(User).filter(User.role == "Owner").first()
    if not owner_exists and seed_email and seed_password and not db.query(User).filter(User.email == seed_email).first():
        logger.info("Seeding workspace owner %s...", seed_email)
        tenant = Tenant(name="Default Workspace")
        db.add(tenant)
        db.flush()
        now = datetime.now(timezone.utc)
        db.add(User(
            email=seed_email,
            name="aVn Administrator",
            hashed_password=get_password_hash(seed_password),
            role="Owner",
            status="active",
            tenant_id=tenant.id,
            joined=now.strftime("%Y-%m-%d"),
            email_verified_at=now.replace(tzinfo=None),
        ))
        db.commit()
except Exception as e:
    logger.error(f"Error seeding database: {e}")
finally:
    db.close()

app = FastAPI(
    title="aVn Agent API",
    version="1.0.0",
    description="Production-ready FastAPI backend supporting user authorization, lead records, and calls metrics with a PostgreSQL database.",
    # Interactive docs and the raw schema are for local development only.
    docs_url="/docs" if settings.is_local else None,
    redoc_url="/redoc" if settings.is_local else None,
    openapi_url="/openapi.json" if settings.is_local else None,
)
app.add_middleware(SecurityHeadersMiddleware)

# CORS middleware mapping
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(auth.router)
app.include_router(leads.router)
app.include_router(calls.router)
app.include_router(appointments.router)
app.include_router(cms.router)
app.include_router(workflows.router)
app.include_router(analytics.router)
app.include_router(agents.router)
app.include_router(kb.router)
app.include_router(inbound.router)
app.include_router(contacts.router)
app.include_router(campaigns.router)
app.include_router(system.router)
app.include_router(team.router)
app.include_router(workspace.router)
app.include_router(lead_fields.router)
app.include_router(webhooks.router)
app.include_router(notifications.router)
app.include_router(calendar.router)
app.include_router(whatsapp.router)
app.include_router(billing.router)

# Uploaded CMS media. Only well-formed stored names of allowed passive types are served, with a fixed
# content type and a sandbox CSP (see app/services/media_files.py); everything else is 404.
@app.get("/data/media/{tenant_id}/{name}", include_in_schema=False)
def serve_media(tenant_id: str, name: str):
    path = media_files.resolve(tenant_id, name)
    if path is None:
        raise HTTPException(status_code=404, detail="Not found")
    ext = path.suffix.lower()
    return FileResponse(
        path,
        media_type=media_files.ALLOWED_TYPES[ext],
        headers={
            "Content-Security-Policy": "default-src 'none'; sandbox",
            "Content-Disposition": f'inline; filename="{path.name}"',
            "Cache-Control": "public, max-age=86400",
        },
    )

@app.get("/health")
def health_check():
    """Application health status indicators."""
    return {
        "status": "ok",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "service": "avn-backend-api",
    }

@app.on_event("startup")
def startup_event():
    from app.services.workflow_engine import workflow_engine
    from app.services.campaign_worker import start_campaign_worker
    from app.services.calendar_sync import start_calendar_worker
    workflow_engine.start()
    start_campaign_worker()
    start_calendar_worker()

