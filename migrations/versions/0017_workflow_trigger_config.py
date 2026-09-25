"""workflow trigger config

Revision ID: 0017
Revises: 0016
Create Date: 2026-09-25
"""
from alembic import op
import sqlalchemy as sa


revision = '0017'
down_revision = '0016'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('workflows', schema=None) as batch_op:
        batch_op.add_column(sa.Column('trigger_config', sa.Text(), nullable=True))



def downgrade() -> None:
    with op.batch_alter_table('workflows', schema=None) as batch_op:
        batch_op.drop_column('trigger_config')

