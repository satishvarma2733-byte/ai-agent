"""call summaries

Revision ID: 0019
Revises: 0018
Create Date: 2026-09-25
"""
from alembic import op
import sqlalchemy as sa


revision = '0019'
down_revision = '0018'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('call_logs', schema=None) as batch_op:
        batch_op.add_column(sa.Column('summary_sent_at', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('summary_email_status', sa.String(length=20), nullable=True))

    with op.batch_alter_table('tenants', schema=None) as batch_op:
        batch_op.add_column(sa.Column('call_summaries', sa.Text(), nullable=True))



def downgrade() -> None:
    with op.batch_alter_table('tenants', schema=None) as batch_op:
        batch_op.drop_column('call_summaries')

    with op.batch_alter_table('call_logs', schema=None) as batch_op:
        batch_op.drop_column('summary_email_status')
        batch_op.drop_column('summary_sent_at')

