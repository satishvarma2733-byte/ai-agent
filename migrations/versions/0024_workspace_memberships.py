"""workspace memberships: one account in several workspaces

Revision ID: 0024
Revises: 0023
Create Date: 2026-09-27
"""
import uuid
from datetime import datetime, timezone

from alembic import op
import sqlalchemy as sa


revision = '0024'
down_revision = '0023'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('workspace_memberships',
    sa.Column('id', sa.String(length=50), nullable=False),
    sa.Column('user_id', sa.String(length=50), nullable=False),
    sa.Column('tenant_id', sa.String(length=50), nullable=False),
    sa.Column('role', sa.String(length=50), nullable=False),
    sa.Column('status', sa.String(length=50), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], name=op.f('fk_workspace_memberships_tenant_id_tenants'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_workspace_memberships_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_workspace_memberships')),
    sa.UniqueConstraint('user_id', 'tenant_id', name='uq_workspace_memberships_user_tenant')
    )
    with op.batch_alter_table('workspace_memberships', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_workspace_memberships_tenant_id'), ['tenant_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_workspace_memberships_user_id'), ['user_id'], unique=False)

    # Every existing account becomes a member of its workspace. Deactivating a teammate used to set
    # users.status; that status moves to the membership and the account itself stays usable.
    bind = op.get_bind()
    users = bind.execute(sa.text("SELECT id, tenant_id, role, status, created_at FROM users")).fetchall()
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    rows = [{"id": str(uuid.uuid4()), "user_id": u.id, "tenant_id": u.tenant_id, "role": u.role or "Agent",
             "status": "active" if u.status == "active" else "inactive", "created_at": u.created_at or now} for u in users]
    if rows:
        memberships = sa.table('workspace_memberships', sa.column('id'), sa.column('user_id'), sa.column('tenant_id'),
                               sa.column('role'), sa.column('status'), sa.column('created_at'))
        op.bulk_insert(memberships, rows)
    bind.execute(sa.text("UPDATE users SET status = 'active' WHERE status <> 'active'"))


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(sa.text(
        "UPDATE users SET status = 'inactive' WHERE id IN (SELECT user_id FROM workspace_memberships m "
        "WHERE m.tenant_id = users.tenant_id AND m.status <> 'active')"))
    with op.batch_alter_table('workspace_memberships', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_workspace_memberships_user_id'))
        batch_op.drop_index(batch_op.f('ix_workspace_memberships_tenant_id'))

    op.drop_table('workspace_memberships')
