"""Importing this package registers every model on Base.metadata (used by Alembic)."""
from app.models.tenant import Tenant  # noqa: F401
from app.models.user import User  # noqa: F401
from app.models.lead import Lead, LeadActivity, LeadField  # noqa: F401
from app.models.call import CallLog, CallTurnMetric  # noqa: F401
from app.models.appointment import Appointment  # noqa: F401
from app.models.cms import CMSPage, CMSPrompt, CMSFaq, CMSMedia  # noqa: F401
from app.models.workflow import WebhookEndpoint, Workflow, WorkflowEvent, WorkflowLog  # noqa: F401
from app.models.audit import AuditLog  # noqa: F401
from app.models.agent import Agent, AgentChange, AgentLifecycleEvent, AgentPhoneNumber, AgentVersion  # noqa: F401
from app.models.campaign import Campaign, CampaignLead  # noqa: F401
from app.models.auth import AuthSession, AuthToken, Invitation  # noqa: F401
from app.models.kb import KBChunk, KBDocument, KBIngestJob, KBSource  # noqa: F401
from app.models.notification import Notification  # noqa: F401
from app.models.calendar import AppointmentCalendarEvent, CalendarConnection  # noqa: F401
from app.models.whatsapp import WhatsAppAccount, WhatsAppMessage  # noqa: F401
from app.models.billing import BillingEvent, BillingInvoice, BillingSubscription  # noqa: F401
