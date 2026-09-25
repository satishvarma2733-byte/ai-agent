"""Postgres row-level security (migration 0005). Skipped on SQLite and for roles that bypass RLS."""
import unittest
import uuid

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

import app.main  # noqa: F401  (runs migrations)
from app.core.database import SessionLocal, engine
from app.core.tenancy import bind_session_to_tenant
from app.models.lead import Lead
from app.models.tenant import Tenant


def _rls_enforced() -> bool:
    if engine.dialect.name != "postgresql":
        return False
    with engine.connect() as conn:
        return not conn.execute(text("SELECT rolsuper OR rolbypassrls FROM pg_roles WHERE rolname = current_user")).scalar()


@unittest.skipUnless(_rls_enforced(), "needs Postgres with a role that does not bypass RLS")
class RowLevelSecurityTests(unittest.TestCase):
    def setUp(self):
        db = SessionLocal()
        self.tenant_a, self.tenant_b = str(uuid.uuid4()), str(uuid.uuid4())
        db.add_all([Tenant(id=self.tenant_a, name="A"), Tenant(id=self.tenant_b, name="B")])
        db.flush()
        db.add_all([
            Lead(tenant_id=self.tenant_a, name="Lead A", phone="+911000000001"),
            Lead(tenant_id=self.tenant_b, name="Lead B", phone="+911000000002"),
        ])
        db.commit()
        db.close()

    def test_unfiltered_query_only_sees_own_tenant(self):
        db = SessionLocal()
        try:
            bind_session_to_tenant(db, self.tenant_a)
            names = {lead.name for lead in db.query(Lead).filter(Lead.name.in_(["Lead A", "Lead B"])).all()}
            self.assertEqual(names, {"Lead A"})
            # Still enforced after a commit starts a new transaction.
            db.commit()
            self.assertEqual(db.execute(text("SELECT count(*) FROM leads WHERE name = 'Lead B'")).scalar(), 0)
        finally:
            db.close()

    def test_cannot_write_into_another_tenant(self):
        db = SessionLocal()
        try:
            bind_session_to_tenant(db, self.tenant_a)
            db.add(Lead(tenant_id=self.tenant_b, name="Smuggled", phone="+911000000003"))
            with self.assertRaises(DBAPIError):
                db.commit()
        finally:
            db.rollback()
            db.close()

    def test_unbound_sessions_are_unrestricted(self):
        db = SessionLocal()
        try:
            names = {lead.name for lead in db.query(Lead).filter(Lead.name.in_(["Lead A", "Lead B"])).all()}
            self.assertEqual(names, {"Lead A", "Lead B"})
        finally:
            db.close()


if __name__ == "__main__":
    unittest.main()
