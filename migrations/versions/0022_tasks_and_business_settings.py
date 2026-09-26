"""tasks and business settings

Revision ID: 0022
Revises: 0021
Create Date: 2026-09-26
"""
from alembic import op
import sqlalchemy as sa


revision = '0022'
down_revision = '0021'
branch_labels = None
depends_on = None

_TENANT_MATCH = (
    "(NULLIF(current_setting('app.tenant_id', true), '') IS NULL "
    "OR tenant_id = current_setting('app.tenant_id', true))"
)


def upgrade() -> None:
    op.create_table('tasks',
    sa.Column('id', sa.String(length=50), nullable=False),
    sa.Column('tenant_id', sa.String(length=50), nullable=False),
    sa.Column('lead_id', sa.String(length=50), nullable=True),
    sa.Column('title', sa.String(length=200), nullable=False),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('due_date', sa.String(length=10), nullable=True),
    sa.Column('assigned_user_id', sa.String(length=50), nullable=True),
    sa.Column('status', sa.String(length=10), nullable=False),
    sa.Column('created_by', sa.String(length=50), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('completed_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['assigned_user_id'], ['users.id'], name=op.f('fk_tasks_assigned_user_id_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], name=op.f('fk_tasks_created_by_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['lead_id'], ['leads.id'], name=op.f('fk_tasks_lead_id_leads'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], name=op.f('fk_tasks_tenant_id_tenants'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_tasks'))
    )
    with op.batch_alter_table('tasks', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_tasks_assigned_user_id'), ['assigned_user_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_tasks_lead_id'), ['lead_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_tasks_tenant_id'), ['tenant_id'], unique=False)

    with op.batch_alter_table('tenants', schema=None) as batch_op:
        batch_op.add_column(sa.Column('business_settings', sa.Text(), nullable=True))

    if op.get_bind().dialect.name == "postgresql":
        for table in ("tasks",):
            op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
            op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
            op.execute(f"CREATE POLICY tenant_isolation ON {table} USING {_TENANT_MATCH} WITH CHECK {_TENANT_MATCH}")


def downgrade() -> None:
    with op.batch_alter_table('tenants', schema=None) as batch_op:
        batch_op.drop_column('business_settings')

    with op.batch_alter_table('tasks', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_tasks_tenant_id'))
        batch_op.drop_index(batch_op.f('ix_tasks_lead_id'))
        batch_op.drop_index(batch_op.f('ix_tasks_assigned_user_id'))

    op.drop_table('tasks')
