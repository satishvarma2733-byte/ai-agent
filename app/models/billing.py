import uuid

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, UniqueConstraint

from app.core.database import Base


class BillingSubscription(Base):
    """A workspace's paid plan with Razorpay or Stripe. The provider is the source of truth; webhooks keep this in step."""
    __tablename__ = "billing_subscriptions"

    id = Column(String(50), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(String(50), ForeignKey("tenants.id", ondelete="CASCADE"), unique=True, nullable=False)
    provider = Column(String(20), nullable=False)  # razorpay | stripe
    plan_id = Column(String(50), nullable=False)  # our plan id from the plans file
    provider_customer_id = Column(String(100), nullable=True)
    provider_subscription_id = Column(String(100), unique=True, nullable=True)
    # created (checkout started) | active | past_due | cancelled | ended
    status = Column(String(20), nullable=False)
    current_period_end = Column(DateTime, nullable=True)
    cancel_at_period_end = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, nullable=False)
    updated_at = Column(DateTime, nullable=False)


class BillingInvoice(Base):
    __tablename__ = "billing_invoices"
    __table_args__ = (UniqueConstraint("provider", "provider_invoice_id"),)

    id = Column(String(50), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(String(50), ForeignKey("tenants.id", ondelete="CASCADE"), index=True, nullable=False)
    provider = Column(String(20), nullable=False)
    provider_invoice_id = Column(String(100), nullable=False)
    number = Column(String(100), nullable=True)
    amount_minor = Column(Integer, nullable=False)  # paise / cents
    currency = Column(String(3), nullable=False)
    status = Column(String(20), nullable=False)  # paid | open | failed
    url = Column(String(500), nullable=True)
    period_start = Column(DateTime, nullable=True)
    period_end = Column(DateTime, nullable=True)
    created_at = Column(DateTime, index=True, nullable=False)


class BillingEvent(Base):
    """Provider webhook events already handled, so a retried delivery is applied once."""
    __tablename__ = "billing_events"
    __table_args__ = (UniqueConstraint("provider", "event_id"),)

    id = Column(String(50), primary_key=True, default=lambda: str(uuid.uuid4()))
    provider = Column(String(20), nullable=False)
    event_id = Column(String(150), nullable=False)
    event_type = Column(String(100), nullable=False)
    tenant_id = Column(String(50), nullable=True)
    received_at = Column(DateTime, nullable=False)
