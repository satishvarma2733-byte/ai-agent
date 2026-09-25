import unittest
from unittest.mock import patch
import uuid

from fastapi.testclient import TestClient

from app.main import app
from app.core.database import SessionLocal, Base, engine
from app.models.tenant import Tenant
from app.models.user import User


def _email() -> str:
    return f"user-{uuid.uuid4().hex[:10]}@example.com"


class TestAuthSecurity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        Base.metadata.create_all(bind=engine)
        cls.client = TestClient(app)

    def _signup(self, **overrides):
        payload = {"email": _email(), "password": "correct-horse-1", "name": "Tester", "company_name": "Acme"}
        payload.update(overrides)
        return payload, self.client.post("/api/auth/signup", json=payload)

    def _login(self, email, password="correct-horse-1"):
        res = self.client.post("/api/auth/login", json={"email": email, "password": password})
        self.assertEqual(res.status_code, 200, res.text)
        return {**res.json(), "refresh_token": res.cookies.get("avn_refresh")}

    def _me(self, email):
        token = self._login(email)["access_token"]
        return self.client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"}).json()

    def test_signup_ignores_client_supplied_tenant_and_role(self):
        victim_payload, _ = self._signup(company_name="Victim Co")
        victim_tenant = self._me(victim_payload["email"])["tenant_id"]

        attacker_payload, attacker = self._signup(tenant_id=victim_tenant, role="Owner", company_name="Attacker Co")
        self.assertEqual(attacker.status_code, 202, attacker.text)
        me = self._me(attacker_payload["email"])
        self.assertNotEqual(me["tenant_id"], victim_tenant)
        self.assertEqual(me["role"], "Owner")

    def test_signup_without_company_creates_tenant(self):
        payload, res = self._signup(company_name=None)
        self.assertEqual(res.status_code, 202, res.text)
        tenant_id = self._me(payload["email"])["tenant_id"]
        self.assertIsNotNone(tenant_id)
        db = SessionLocal()
        try:
            self.assertIsNotNone(db.query(Tenant).filter(Tenant.id == tenant_id).first())
        finally:
            db.close()

    def test_signup_does_not_reveal_registered_emails(self):
        payload, first = self._signup()
        with patch("app.routers.auth.deliver", return_value="logged") as mail:
            again = self.client.post("/api/auth/signup", json={**payload, "password": "different-pass-9"})
        self.assertEqual((again.status_code, again.json()), (first.status_code, first.json()))
        self.assertEqual(mail.call_args.args[0], payload["email"], "the existing owner is told instead")
        self._login(payload["email"])  # original password still works; nothing was overwritten

    def test_signup_is_rate_limited_per_ip(self):
        from app.core import ratelimit
        from app.core.settings import settings
        ratelimit.reset("signup:testclient")
        with patch.object(type(settings), "signup_limit", property(lambda self: 2)):
            codes = [self._signup()[1].status_code for _ in range(3)]
        ratelimit.reset("signup:testclient")
        self.assertEqual(codes, [202, 202, 429])

    def test_signup_rejects_short_password(self):
        _, res = self._signup(password="short")
        self.assertEqual(res.status_code, 422)

    def test_refresh_token_is_not_accepted_as_access_token(self):
        payload, _ = self._signup()
        tokens = self._login(payload["email"])

        ok = self.client.get("/api/auth/me", headers={"Authorization": f"Bearer {tokens['access_token']}"})
        self.assertEqual(ok.status_code, 200)

        misuse = self.client.get("/api/auth/me", headers={"Authorization": f"Bearer {tokens['refresh_token']}"})
        self.assertEqual(misuse.status_code, 401)

    def test_no_users_without_a_tenant(self):
        db = SessionLocal()
        try:
            orphans = db.query(User).filter(User.tenant_id.is_(None)).count()
            self.assertEqual(orphans, 0)
        finally:
            db.close()


if __name__ == "__main__":
    unittest.main()
