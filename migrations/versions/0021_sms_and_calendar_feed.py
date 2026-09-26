"""sms and calendar feed

Revision ID: 0021
Revises: 0020
Create Date: 2026-09-26
"""
from alembic import op
import sqlalchemy as sa


revision = '0021'
down_revision = '0020'
branch_labels = None
depends_on = None

_TENANT_MATCH = (
    "(NULLIF(current_setting('app.tenant_id', true), '') IS NULL "
    "OR tenant_id = current_setting('app.tenant_id', true))"
)


def upgrade() -> None:
    op.create_table('calendar_feeds',
    sa.Column('id', sa.String(length=50), nullable=False),
    sa.Column('tenant_id', sa.String(length=50), nullable=False),
    sa.Column('token_hash', sa.String(length=64), nullable=False),
    sa.Column('token', sa.Text(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('last_fetched_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], name=op.f('fk_calendar_feeds_tenant_id_tenants'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_calendar_feeds')),
    sa.UniqueConstraint('tenant_id', name=op.f('uq_calendar_feeds_tenant_id')),
    sa.UniqueConstraint('token_hash', name=op.f('uq_calendar_feeds_token_hash'))
    )
    op.create_table('sms_accounts',
    sa.Column('id', sa.String(length=50), nullable=False),
    sa.Column('tenant_id', sa.String(length=50), nullable=False),
    sa.Column('provider', sa.String(length=20), nullable=False),
    sa.Column('sender', sa.String(length=20), nullable=False),
    sa.Column('credentials', sa.Text(), nullable=False),
    sa.Column('connected_by', sa.String(length=50), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['connected_by'], ['users.id'], name=op.f('fk_sms_accounts_connected_by_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], name=op.f('fk_sms_accounts_tenant_id_tenants'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_sms_accounts')),
    sa.UniqueConstraint('tenant_id', name=op.f('uq_sms_accounts_tenant_id'))
    )

    if op.get_bind().dialect.name == "postgresql":
        for table in ("sms_accounts", "calendar_feeds"):
            op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
            op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
            op.execute(f"CREATE POLICY tenant_isolation ON {table} USING {_TENANT_MATCH} WITH CHECK {_TENANT_MATCH}")


def downgrade() -> None:
    op.drop_table('sms_accounts')
    op.drop_table('calendar_feeds')
