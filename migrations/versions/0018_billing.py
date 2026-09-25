"""billing

Revision ID: 0018
Revises: 0017
Create Date: 2026-09-25
"""
from alembic import op
import sqlalchemy as sa


revision = '0018'
down_revision = '0017'
branch_labels = None
depends_on = None

_TENANT_MATCH = (
    "(NULLIF(current_setting('app.tenant_id', true), '') IS NULL "
    "OR tenant_id = current_setting('app.tenant_id', true))"
)


def upgrade() -> None:
    op.create_table('billing_events',
    sa.Column('id', sa.String(length=50), nullable=False),
    sa.Column('provider', sa.String(length=20), nullable=False),
    sa.Column('event_id', sa.String(length=150), nullable=False),
    sa.Column('event_type', sa.String(length=100), nullable=False),
    sa.Column('tenant_id', sa.String(length=50), nullable=True),
    sa.Column('received_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_billing_events')),
    sa.UniqueConstraint('provider', 'event_id', name=op.f('uq_billing_events_provider'))
    )
    op.create_table('billing_invoices',
    sa.Column('id', sa.String(length=50), nullable=False),
    sa.Column('tenant_id', sa.String(length=50), nullable=False),
    sa.Column('provider', sa.String(length=20), nullable=False),
    sa.Column('provider_invoice_id', sa.String(length=100), nullable=False),
    sa.Column('number', sa.String(length=100), nullable=True),
    sa.Column('amount_minor', sa.Integer(), nullable=False),
    sa.Column('currency', sa.String(length=3), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('url', sa.String(length=500), nullable=True),
    sa.Column('period_start', sa.DateTime(), nullable=True),
    sa.Column('period_end', sa.DateTime(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], name=op.f('fk_billing_invoices_tenant_id_tenants'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_billing_invoices')),
    sa.UniqueConstraint('provider', 'provider_invoice_id', name=op.f('uq_billing_invoices_provider'))
    )
    with op.batch_alter_table('billing_invoices', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_billing_invoices_created_at'), ['created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_billing_invoices_tenant_id'), ['tenant_id'], unique=False)

    op.create_table('billing_subscriptions',
    sa.Column('id', sa.String(length=50), nullable=False),
    sa.Column('tenant_id', sa.String(length=50), nullable=False),
    sa.Column('provider', sa.String(length=20), nullable=False),
    sa.Column('plan_id', sa.String(length=50), nullable=False),
    sa.Column('provider_customer_id', sa.String(length=100), nullable=True),
    sa.Column('provider_subscription_id', sa.String(length=100), nullable=True),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('current_period_end', sa.DateTime(), nullable=True),
    sa.Column('cancel_at_period_end', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], name=op.f('fk_billing_subscriptions_tenant_id_tenants'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_billing_subscriptions')),
    sa.UniqueConstraint('provider_subscription_id', name=op.f('uq_billing_subscriptions_provider_subscription_id')),
    sa.UniqueConstraint('tenant_id', name=op.f('uq_billing_subscriptions_tenant_id'))
    )

    if op.get_bind().dialect.name == "postgresql":
        for table in ("billing_subscriptions", "billing_invoices"):
            op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
            op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
            op.execute(f"CREATE POLICY tenant_isolation ON {table} USING {_TENANT_MATCH} WITH CHECK {_TENANT_MATCH}")


def downgrade() -> None:
    op.drop_table('billing_subscriptions')
    with op.batch_alter_table('billing_invoices', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_billing_invoices_tenant_id'))
        batch_op.drop_index(batch_op.f('ix_billing_invoices_created_at'))

    op.drop_table('billing_invoices')
    op.drop_table('billing_events')
