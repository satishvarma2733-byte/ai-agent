"""agent phone numbers

Each business number is answered by one agent (and so one workspace).

Revision ID: 0011
Revises: 0010
Create Date: 2026-09-25
"""
from alembic import op
import sqlalchemy as sa


revision = '0011'
down_revision = '0010'
branch_labels = None
depends_on = None

_TENANT_MATCH = (
    "(NULLIF(current_setting('app.tenant_id', true), '') IS NULL "
    "OR tenant_id = current_setting('app.tenant_id', true))"
)


def upgrade() -> None:
    op.create_table(
        'agent_phone_numbers',
        sa.Column('id', sa.String(length=50), nullable=False),
        sa.Column('tenant_id', sa.String(length=50), nullable=False),
        sa.Column('agent_id', sa.String(length=50), nullable=False),
        sa.Column('phone_number', sa.String(length=20), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['agent_id'], ['agents.id'], name=op.f('fk_agent_phone_numbers_agent_id_agents'), ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], name=op.f('fk_agent_phone_numbers_tenant_id_tenants'), ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_agent_phone_numbers')),
        sa.UniqueConstraint('phone_number', name=op.f('uq_agent_phone_numbers_phone_number')),
    )
    op.create_index(op.f('ix_agent_phone_numbers_agent_id'), 'agent_phone_numbers', ['agent_id'], unique=False)
    op.create_index(op.f('ix_agent_phone_numbers_tenant_id'), 'agent_phone_numbers', ['tenant_id'], unique=False)
    if op.get_bind().dialect.name == "postgresql":
        # The worker resolves numbers before a tenant is known; it runs without app.tenant_id, which the policy allows.
        op.execute("ALTER TABLE agent_phone_numbers ENABLE ROW LEVEL SECURITY")
        op.execute("ALTER TABLE agent_phone_numbers FORCE ROW LEVEL SECURITY")
        op.execute(f"CREATE POLICY tenant_isolation ON agent_phone_numbers USING {_TENANT_MATCH} WITH CHECK {_TENANT_MATCH}")


def downgrade() -> None:
    op.drop_index(op.f('ix_agent_phone_numbers_tenant_id'), table_name='agent_phone_numbers')
    op.drop_index(op.f('ix_agent_phone_numbers_agent_id'), table_name='agent_phone_numbers')
    op.drop_table('agent_phone_numbers')
