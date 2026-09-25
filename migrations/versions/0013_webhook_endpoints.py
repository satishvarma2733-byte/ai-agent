"""webhook endpoints

One inbound lead webhook per workspace, and the secret that signs outbound webhooks.

Revision ID: 0013
Revises: 0012
Create Date: 2026-09-25
"""
from alembic import op
import sqlalchemy as sa


revision = '0013'
down_revision = '0012'
branch_labels = None
depends_on = None

_TENANT_MATCH = (
    "(NULLIF(current_setting('app.tenant_id', true), '') IS NULL "
    "OR tenant_id = current_setting('app.tenant_id', true))"
)


def upgrade() -> None:
    op.create_table(
        'webhook_endpoints',
        sa.Column('id', sa.String(length=50), nullable=False),
        sa.Column('tenant_id', sa.String(length=50), nullable=False),
        sa.Column('token_hash', sa.String(length=64), nullable=False),
        sa.Column('signing_secret', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('last_used_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], name=op.f('fk_webhook_endpoints_tenant_id_tenants'), ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_webhook_endpoints')),
        sa.UniqueConstraint('tenant_id', name=op.f('uq_webhook_endpoints_tenant_id')),
        sa.UniqueConstraint('token_hash', name=op.f('uq_webhook_endpoints_token_hash')),
    )
    if op.get_bind().dialect.name == "postgresql":
        # The public hook looks the token up before any tenant is known (no app.tenant_id, which the policy allows).
        op.execute("ALTER TABLE webhook_endpoints ENABLE ROW LEVEL SECURITY")
        op.execute("ALTER TABLE webhook_endpoints FORCE ROW LEVEL SECURITY")
        op.execute(f"CREATE POLICY tenant_isolation ON webhook_endpoints USING {_TENANT_MATCH} WITH CHECK {_TENANT_MATCH}")


def downgrade() -> None:
    op.drop_table('webhook_endpoints')
