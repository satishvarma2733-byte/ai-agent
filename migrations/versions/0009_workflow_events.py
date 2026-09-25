"""workflow events queue

Durable queue of workflow triggers shared by the API and the voice worker.

Revision ID: 0009
Revises: 0008
Create Date: 2026-09-25
"""
from alembic import op
import sqlalchemy as sa


revision = '0009'
down_revision = '0008'
branch_labels = None
depends_on = None

_TENANT_MATCH = (
    "(NULLIF(current_setting('app.tenant_id', true), '') IS NULL "
    "OR tenant_id = current_setting('app.tenant_id', true))"
)


def upgrade() -> None:
    op.create_table(
        'workflow_events',
        sa.Column('id', sa.String(length=50), nullable=False),
        sa.Column('tenant_id', sa.String(length=50), nullable=False),
        sa.Column('event_type', sa.String(length=100), nullable=False),
        sa.Column('lead_id', sa.String(length=50), nullable=True),
        sa.Column('phone', sa.String(length=50), nullable=True),
        sa.Column('ref', sa.String(length=150), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('claimed_at', sa.DateTime(), nullable=True),
        sa.Column('processed_at', sa.DateTime(), nullable=True),
        sa.Column('attempts', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('last_error', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], name=op.f('fk_workflow_events_tenant_id_tenants'), ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_workflow_events')),
        sa.UniqueConstraint('tenant_id', 'event_type', 'ref', name=op.f('uq_workflow_events_tenant_id')),
    )
    op.create_index(op.f('ix_workflow_events_tenant_id'), 'workflow_events', ['tenant_id'], unique=False)
    op.create_index(op.f('ix_workflow_events_processed_at'), 'workflow_events', ['processed_at'], unique=False)
    if op.get_bind().dialect.name == "postgresql":
        op.execute("ALTER TABLE workflow_events ENABLE ROW LEVEL SECURITY")
        op.execute("ALTER TABLE workflow_events FORCE ROW LEVEL SECURITY")
        op.execute(f"CREATE POLICY tenant_isolation ON workflow_events USING {_TENANT_MATCH} WITH CHECK {_TENANT_MATCH}")


def downgrade() -> None:
    op.drop_index(op.f('ix_workflow_events_processed_at'), table_name='workflow_events')
    op.drop_index(op.f('ix_workflow_events_tenant_id'), table_name='workflow_events')
    op.drop_table('workflow_events')
