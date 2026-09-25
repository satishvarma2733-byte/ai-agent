"""Postgres row-level security on tenant data tables.

A request that authenticated as a user tags each transaction with `app.tenant_id`; rows of other
tenants are then invisible and cannot be written, even if a query forgets its tenant filter.
Without a tag (background workers, migrations, auth lookups) access is unrestricted.
Superusers always bypass RLS, so production must connect as a regular role.

Revision ID: 0005
Revises: 0004
"""
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None

# Identity tables (users, auth_sessions, auth_tokens, invitations, tenants, audit_logs) are read
# before a tenant is known, so they rely on application checks only.
RLS_TABLES = (
    "agents", "appointments", "call_logs", "call_turn_metrics", "campaign_leads", "campaigns",
    "cms_faqs", "cms_media", "cms_pages", "cms_prompts", "lead_activities", "leads",
    "workflow_logs", "workflows",
)
_TENANT_MATCH = (
    "(NULLIF(current_setting('app.tenant_id', true), '') IS NULL "
    "OR tenant_id = current_setting('app.tenant_id', true))"
)


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    for table in RLS_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(f"CREATE POLICY tenant_isolation ON {table} USING {_TENANT_MATCH} WITH CHECK {_TENANT_MATCH}")


def downgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    for table in RLS_TABLES:
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table}")
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
