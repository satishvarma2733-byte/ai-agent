"""calendar sync

Revision ID: 0015
Revises: 0014
Create Date: 2026-09-25
"""
from alembic import op
import sqlalchemy as sa


revision = '0015'
down_revision = '0014'
branch_labels = None
depends_on = None

_TENANT_MATCH = (
    "(NULLIF(current_setting('app.tenant_id', true), '') IS NULL "
    "OR tenant_id = current_setting('app.tenant_id', true))"
)


def upgrade() -> None:
    op.create_table('calendar_connections',
    sa.Column('id', sa.String(length=50), nullable=False),
    sa.Column('tenant_id', sa.String(length=50), nullable=False),
    sa.Column('provider', sa.String(length=20), nullable=False),
    sa.Column('account_email', sa.String(length=200), nullable=True),
    sa.Column('calendar_id', sa.String(length=200), nullable=False),
    sa.Column('accounts_url', sa.String(length=200), nullable=True),
    sa.Column('refresh_token', sa.Text(), nullable=False),
    sa.Column('access_token', sa.Text(), nullable=True),
    sa.Column('access_expires_at', sa.DateTime(), nullable=True),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('last_error', sa.Text(), nullable=True),
    sa.Column('last_synced_at', sa.DateTime(), nullable=True),
    sa.Column('connected_by', sa.String(length=50), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['connected_by'], ['users.id'], name=op.f('fk_calendar_connections_connected_by_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], name=op.f('fk_calendar_connections_tenant_id_tenants'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_calendar_connections')),
    sa.UniqueConstraint('tenant_id', 'provider', name=op.f('uq_calendar_connections_tenant_id'))
    )
    with op.batch_alter_table('calendar_connections', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_calendar_connections_tenant_id'), ['tenant_id'], unique=False)

    op.create_table('appointment_calendar_events',
    sa.Column('id', sa.String(length=50), nullable=False),
    sa.Column('tenant_id', sa.String(length=50), nullable=False),
    sa.Column('appointment_id', sa.String(length=50), nullable=False),
    sa.Column('connection_id', sa.String(length=50), nullable=False),
    sa.Column('external_id', sa.String(length=300), nullable=True),
    sa.Column('etag', sa.String(length=300), nullable=True),
    sa.Column('synced_start', sa.String(length=100), nullable=True),
    sa.Column('synced_end', sa.String(length=100), nullable=True),
    sa.Column('state', sa.String(length=20), nullable=False),
    sa.Column('attempts', sa.Integer(), nullable=False),
    sa.Column('next_attempt_at', sa.DateTime(), nullable=True),
    sa.Column('last_error', sa.Text(), nullable=True),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['appointment_id'], ['appointments.id'], name=op.f('fk_appointment_calendar_events_appointment_id_appointments'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['connection_id'], ['calendar_connections.id'], name=op.f('fk_appointment_calendar_events_connection_id_calendar_connections'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], name=op.f('fk_appointment_calendar_events_tenant_id_tenants'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_appointment_calendar_events')),
    sa.UniqueConstraint('appointment_id', 'connection_id', name=op.f('uq_appointment_calendar_events_appointment_id'))
    )
    with op.batch_alter_table('appointment_calendar_events', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_appointment_calendar_events_appointment_id'), ['appointment_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_appointment_calendar_events_connection_id'), ['connection_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_appointment_calendar_events_state'), ['state'], unique=False)
        batch_op.create_index(batch_op.f('ix_appointment_calendar_events_tenant_id'), ['tenant_id'], unique=False)

    if op.get_bind().dialect.name == "postgresql":
        for table in ("calendar_connections", "appointment_calendar_events"):
            op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
            op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
            op.execute(f"CREATE POLICY tenant_isolation ON {table} USING {_TENANT_MATCH} WITH CHECK {_TENANT_MATCH}")


def downgrade() -> None:
    with op.batch_alter_table('appointment_calendar_events', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_appointment_calendar_events_tenant_id'))
        batch_op.drop_index(batch_op.f('ix_appointment_calendar_events_state'))
        batch_op.drop_index(batch_op.f('ix_appointment_calendar_events_connection_id'))
        batch_op.drop_index(batch_op.f('ix_appointment_calendar_events_appointment_id'))

    op.drop_table('appointment_calendar_events')
    with op.batch_alter_table('calendar_connections', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_calendar_connections_tenant_id'))

    op.drop_table('calendar_connections')
