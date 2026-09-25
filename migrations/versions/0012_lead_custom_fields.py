"""lead custom fields

Workspaces define their own lead fields; values live in leads.custom_fields.

Revision ID: 0012
Revises: 0011
Create Date: 2026-09-25
"""
from alembic import op
import sqlalchemy as sa


revision = '0012'
down_revision = '0011'
branch_labels = None
depends_on = None

_TENANT_MATCH = (
    "(NULLIF(current_setting('app.tenant_id', true), '') IS NULL "
    "OR tenant_id = current_setting('app.tenant_id', true))"
)


def upgrade() -> None:
    op.create_table(
        'lead_fields',
        sa.Column('id', sa.String(length=50), nullable=False),
        sa.Column('tenant_id', sa.String(length=50), nullable=False),
        sa.Column('key', sa.String(length=60), nullable=False),
        sa.Column('label', sa.String(length=100), nullable=False),
        sa.Column('field_type', sa.String(length=20), nullable=False),
        sa.Column('options', sa.JSON(), nullable=True),
        sa.Column('position', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], name=op.f('fk_lead_fields_tenant_id_tenants'), ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_lead_fields')),
        sa.UniqueConstraint('tenant_id', 'key', name=op.f('uq_lead_fields_tenant_id')),
    )
    op.create_index(op.f('ix_lead_fields_tenant_id'), 'lead_fields', ['tenant_id'], unique=False)
    with op.batch_alter_table('leads', schema=None) as batch_op:
        batch_op.add_column(sa.Column('custom_fields', sa.JSON(), nullable=True))
    if op.get_bind().dialect.name == "postgresql":
        op.execute("ALTER TABLE lead_fields ENABLE ROW LEVEL SECURITY")
        op.execute("ALTER TABLE lead_fields FORCE ROW LEVEL SECURITY")
        op.execute(f"CREATE POLICY tenant_isolation ON lead_fields USING {_TENANT_MATCH} WITH CHECK {_TENANT_MATCH}")


def downgrade() -> None:
    with op.batch_alter_table('leads', schema=None) as batch_op:
        batch_op.drop_column('custom_fields')
    op.drop_index(op.f('ix_lead_fields_tenant_id'), table_name='lead_fields')
    op.drop_table('lead_fields')
