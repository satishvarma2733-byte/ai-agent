"""website chat widgets, API keys, chat sessions; expected language on agent test cases

Revision ID: 0023
Revises: 0022
Create Date: 2026-09-26
"""
from alembic import op
import sqlalchemy as sa


revision = '0023'
down_revision = '0022'
branch_labels = None
depends_on = None

_TENANT_MATCH = (
    "(NULLIF(current_setting('app.tenant_id', true), '') IS NULL "
    "OR tenant_id = current_setting('app.tenant_id', true))"
)


def upgrade() -> None:
    op.create_table('api_keys',
    sa.Column('id', sa.String(length=50), nullable=False),
    sa.Column('tenant_id', sa.String(length=50), nullable=False),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.Column('prefix', sa.String(length=16), nullable=False),
    sa.Column('key_hash', sa.String(length=64), nullable=False),
    sa.Column('created_by', sa.String(length=50), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('last_used_at', sa.DateTime(), nullable=True),
    sa.Column('revoked_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], name=op.f('fk_api_keys_created_by_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], name=op.f('fk_api_keys_tenant_id_tenants'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_api_keys')),
    sa.UniqueConstraint('key_hash', name=op.f('uq_api_keys_key_hash'))
    )
    with op.batch_alter_table('api_keys', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_api_keys_tenant_id'), ['tenant_id'], unique=False)

    op.create_table('chat_widgets',
    sa.Column('id', sa.String(length=50), nullable=False),
    sa.Column('tenant_id', sa.String(length=50), nullable=False),
    sa.Column('agent_id', sa.String(length=50), nullable=False),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.Column('public_key', sa.String(length=64), nullable=False),
    sa.Column('allowed_origins', sa.JSON(), nullable=False),
    sa.Column('greeting', sa.Text(), nullable=True),
    sa.Column('color', sa.String(length=7), nullable=False),
    sa.Column('voice_enabled', sa.Boolean(), nullable=False),
    sa.Column('lead_capture', sa.Boolean(), nullable=False),
    sa.Column('enabled', sa.Boolean(), nullable=False),
    sa.Column('created_by', sa.String(length=50), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['agent_id'], ['agents.id'], name=op.f('fk_chat_widgets_agent_id_agents'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], name=op.f('fk_chat_widgets_created_by_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], name=op.f('fk_chat_widgets_tenant_id_tenants'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_chat_widgets')),
    sa.UniqueConstraint('public_key', name=op.f('uq_chat_widgets_public_key'))
    )
    with op.batch_alter_table('chat_widgets', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_chat_widgets_agent_id'), ['agent_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_chat_widgets_tenant_id'), ['tenant_id'], unique=False)

    op.create_table('chat_sessions',
    sa.Column('id', sa.String(length=50), nullable=False),
    sa.Column('tenant_id', sa.String(length=50), nullable=False),
    sa.Column('agent_id', sa.String(length=50), nullable=False),
    sa.Column('widget_id', sa.String(length=50), nullable=True),
    sa.Column('api_key_id', sa.String(length=50), nullable=True),
    sa.Column('token_hash', sa.String(length=64), nullable=False),
    sa.Column('turns', sa.JSON(), nullable=False),
    sa.Column('origin', sa.String(length=200), nullable=True),
    sa.Column('lead_id', sa.String(length=50), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['agent_id'], ['agents.id'], name=op.f('fk_chat_sessions_agent_id_agents'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['api_key_id'], ['api_keys.id'], name=op.f('fk_chat_sessions_api_key_id_api_keys'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['lead_id'], ['leads.id'], name=op.f('fk_chat_sessions_lead_id_leads'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], name=op.f('fk_chat_sessions_tenant_id_tenants'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['widget_id'], ['chat_widgets.id'], name=op.f('fk_chat_sessions_widget_id_chat_widgets'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_chat_sessions')),
    sa.UniqueConstraint('token_hash', name=op.f('uq_chat_sessions_token_hash'))
    )
    with op.batch_alter_table('chat_sessions', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_chat_sessions_agent_id'), ['agent_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_chat_sessions_lead_id'), ['lead_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_chat_sessions_tenant_id'), ['tenant_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_chat_sessions_widget_id'), ['widget_id'], unique=False)

    with op.batch_alter_table('agent_test_cases', schema=None) as batch_op:
        batch_op.add_column(sa.Column('expected_language', sa.String(length=10), nullable=True))

    if op.get_bind().dialect.name == "postgresql":
        for table in ("api_keys", "chat_widgets", "chat_sessions"):
            op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
            op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
            op.execute(f"CREATE POLICY tenant_isolation ON {table} USING {_TENANT_MATCH} WITH CHECK {_TENANT_MATCH}")


def downgrade() -> None:
    with op.batch_alter_table('agent_test_cases', schema=None) as batch_op:
        batch_op.drop_column('expected_language')

    op.drop_table('chat_sessions')
    op.drop_table('chat_widgets')
    op.drop_table('api_keys')
