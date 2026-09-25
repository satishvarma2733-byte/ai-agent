"""Owner role: give tenantless admins a workspace and make the earliest Admin of each workspace its Owner.

Revision ID: 0003
Revises: 0002
"""
import uuid
from datetime import datetime, timezone

from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    for (user_id,) in conn.execute(sa.text("SELECT id FROM users WHERE tenant_id IS NULL")).fetchall():
        tenant_id = str(uuid.uuid4())
        conn.execute(
            sa.text("INSERT INTO tenants (id, name, plan, status, created_at, updated_at) "
                    "VALUES (:id, 'Default Workspace', 'Free', 'active', :now, :now)"),
            {"id": tenant_id, "now": now},
        )
        conn.execute(sa.text("UPDATE users SET tenant_id = :t WHERE id = :u"), {"t": tenant_id, "u": user_id})

    tenants = conn.execute(sa.text(
        "SELECT DISTINCT tenant_id FROM users WHERE tenant_id IS NOT NULL AND tenant_id NOT IN "
        "(SELECT tenant_id FROM users WHERE role = 'Owner' AND tenant_id IS NOT NULL)"
    )).fetchall()
    for (tenant_id,) in tenants:
        first_admin = conn.execute(
            sa.text("SELECT id FROM users WHERE tenant_id = :t AND role = 'Admin' ORDER BY created_at LIMIT 1"),
            {"t": tenant_id},
        ).fetchone()
        if first_admin:
            conn.execute(sa.text("UPDATE users SET role = 'Owner' WHERE id = :u"), {"u": first_admin[0]})


def downgrade() -> None:
    op.execute("UPDATE users SET role = 'Admin' WHERE role = 'Owner'")
