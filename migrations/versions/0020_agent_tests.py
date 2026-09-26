"""agent tests

Revision ID: 0020
Revises: 0019
Create Date: 2026-09-26
"""
from alembic import op
import sqlalchemy as sa


revision = '0020'
down_revision = '0019'
branch_labels = None
depends_on = None

_TENANT_MATCH = (
    "(NULLIF(current_setting('app.tenant_id', true), '') IS NULL "
    "OR tenant_id = current_setting('app.tenant_id', true))"
)


def upgrade() -> None:
    op.create_table('agent_test_cases',
    sa.Column('id', sa.String(length=50), nullable=False),
    sa.Column('tenant_id', sa.String(length=50), nullable=False),
    sa.Column('agent_id', sa.String(length=50), nullable=False),
    sa.Column('name', sa.String(length=150), nullable=False),
    sa.Column('caller_turns', sa.JSON(), nullable=False),
    sa.Column('must_include', sa.JSON(), nullable=False),
    sa.Column('must_not_include', sa.JSON(), nullable=False),
    sa.Column('created_by', sa.String(length=50), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['agent_id'], ['agents.id'], name=op.f('fk_agent_test_cases_agent_id_agents'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], name=op.f('fk_agent_test_cases_created_by_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], name=op.f('fk_agent_test_cases_tenant_id_tenants'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_agent_test_cases'))
    )
    with op.batch_alter_table('agent_test_cases', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_agent_test_cases_agent_id'), ['agent_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_agent_test_cases_tenant_id'), ['tenant_id'], unique=False)

    op.create_table('agent_test_runs',
    sa.Column('id', sa.String(length=50), nullable=False),
    sa.Column('tenant_id', sa.String(length=50), nullable=False),
    sa.Column('agent_id', sa.String(length=50), nullable=False),
    sa.Column('version_id', sa.String(length=50), nullable=False),
    sa.Column('passed', sa.Integer(), nullable=False),
    sa.Column('total', sa.Integer(), nullable=False),
    sa.Column('results', sa.JSON(), nullable=False),
    sa.Column('created_by', sa.String(length=50), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['agent_id'], ['agents.id'], name=op.f('fk_agent_test_runs_agent_id_agents'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], name=op.f('fk_agent_test_runs_created_by_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], name=op.f('fk_agent_test_runs_tenant_id_tenants'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['version_id'], ['agent_versions.id'], name=op.f('fk_agent_test_runs_version_id_agent_versions'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_agent_test_runs'))
    )
    with op.batch_alter_table('agent_test_runs', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_agent_test_runs_agent_id'), ['agent_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_agent_test_runs_created_at'), ['created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_agent_test_runs_tenant_id'), ['tenant_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_agent_test_runs_version_id'), ['version_id'], unique=False)

    if op.get_bind().dialect.name == "postgresql":
        for table in ("agent_test_cases", "agent_test_runs"):
            op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
            op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
            op.execute(f"CREATE POLICY tenant_isolation ON {table} USING {_TENANT_MATCH} WITH CHECK {_TENANT_MATCH}")


def downgrade() -> None:
    with op.batch_alter_table('agent_test_runs', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_agent_test_runs_version_id'))
        batch_op.drop_index(batch_op.f('ix_agent_test_runs_tenant_id'))
        batch_op.drop_index(batch_op.f('ix_agent_test_runs_created_at'))
        batch_op.drop_index(batch_op.f('ix_agent_test_runs_agent_id'))

    op.drop_table('agent_test_runs')
    with op.batch_alter_table('agent_test_cases', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_agent_test_cases_tenant_id'))
        batch_op.drop_index(batch_op.f('ix_agent_test_cases_agent_id'))

    op.drop_table('agent_test_cases')
