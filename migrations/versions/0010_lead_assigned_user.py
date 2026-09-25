"""lead assigned user

Leads are assigned to a workspace member, not just a free-text name.

Revision ID: 0010
Revises: 0009
Create Date: 2026-09-25
"""
from alembic import op
import sqlalchemy as sa


revision = '0010'
down_revision = '0009'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('leads', schema=None) as batch_op:
        batch_op.add_column(sa.Column('assigned_user_id', sa.String(length=50), nullable=True))
        batch_op.create_index(batch_op.f('ix_leads_assigned_user_id'), ['assigned_user_id'], unique=False)
        batch_op.create_foreign_key(batch_op.f('fk_leads_assigned_user_id_users'), 'users', ['assigned_user_id'], ['id'], ondelete='SET NULL')


def downgrade() -> None:
    with op.batch_alter_table('leads', schema=None) as batch_op:
        batch_op.drop_constraint(batch_op.f('fk_leads_assigned_user_id_users'), type_='foreignkey')
        batch_op.drop_index(batch_op.f('ix_leads_assigned_user_id'))
        batch_op.drop_column('assigned_user_id')
