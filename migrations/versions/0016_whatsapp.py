"""whatsapp

Revision ID: 0016
Revises: 0015
Create Date: 2026-09-25
"""
from alembic import op
import sqlalchemy as sa


revision = '0016'
down_revision = '0015'
branch_labels = None
depends_on = None

_TENANT_MATCH = (
    "(NULLIF(current_setting('app.tenant_id', true), '') IS NULL "
    "OR tenant_id = current_setting('app.tenant_id', true))"
)


def upgrade() -> None:
    op.create_table('whatsapp_accounts',
    sa.Column('id', sa.String(length=50), nullable=False),
    sa.Column('tenant_id', sa.String(length=50), nullable=False),
    sa.Column('provider', sa.String(length=20), nullable=False),
    sa.Column('sender', sa.String(length=50), nullable=True),
    sa.Column('credentials', sa.Text(), nullable=False),
    sa.Column('webhook_token_hash', sa.String(length=64), nullable=False),
    sa.Column('webhook_token', sa.Text(), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('last_error', sa.Text(), nullable=True),
    sa.Column('connected_by', sa.String(length=50), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['connected_by'], ['users.id'], name=op.f('fk_whatsapp_accounts_connected_by_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], name=op.f('fk_whatsapp_accounts_tenant_id_tenants'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_whatsapp_accounts')),
    sa.UniqueConstraint('tenant_id', name=op.f('uq_whatsapp_accounts_tenant_id')),
    sa.UniqueConstraint('webhook_token_hash', name=op.f('uq_whatsapp_accounts_webhook_token_hash'))
    )
    op.create_table('whatsapp_messages',
    sa.Column('id', sa.String(length=50), nullable=False),
    sa.Column('tenant_id', sa.String(length=50), nullable=False),
    sa.Column('lead_id', sa.String(length=50), nullable=True),
    sa.Column('phone', sa.String(length=20), nullable=False),
    sa.Column('direction', sa.String(length=10), nullable=False),
    sa.Column('body', sa.Text(), nullable=True),
    sa.Column('template', sa.String(length=200), nullable=True),
    sa.Column('provider', sa.String(length=20), nullable=False),
    sa.Column('provider_message_id', sa.String(length=200), nullable=True),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('error', sa.Text(), nullable=True),
    sa.Column('source', sa.String(length=20), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['lead_id'], ['leads.id'], name=op.f('fk_whatsapp_messages_lead_id_leads'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], name=op.f('fk_whatsapp_messages_tenant_id_tenants'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_whatsapp_messages'))
    )
    with op.batch_alter_table('whatsapp_messages', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_whatsapp_messages_created_at'), ['created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_whatsapp_messages_lead_id'), ['lead_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_whatsapp_messages_provider_message_id'), ['provider_message_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_whatsapp_messages_tenant_id'), ['tenant_id'], unique=False)

    if op.get_bind().dialect.name == "postgresql":
        for table in ("whatsapp_accounts", "whatsapp_messages"):
            op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
            op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
            op.execute(f"CREATE POLICY tenant_isolation ON {table} USING {_TENANT_MATCH} WITH CHECK {_TENANT_MATCH}")


def downgrade() -> None:
    with op.batch_alter_table('whatsapp_messages', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_whatsapp_messages_tenant_id'))
        batch_op.drop_index(batch_op.f('ix_whatsapp_messages_provider_message_id'))
        batch_op.drop_index(batch_op.f('ix_whatsapp_messages_lead_id'))
        batch_op.drop_index(batch_op.f('ix_whatsapp_messages_created_at'))

    op.drop_table('whatsapp_messages')
    op.drop_table('whatsapp_accounts')
