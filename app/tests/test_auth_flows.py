"""Sessions, email flows, invitations, team management, and the role hierarchy."""
import re
import unittest
import uuid
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app
from app.core.database import SessionLocal
from app.models.audit import AuditLog

PASSWORD = "correct-horse-1"


def _email() -> str:
    return f"u-{uuid.uuid4().hex[:10]}@example.com"


class Mailbox:
    """Captures emails sent by the auth and team routers."""
    def __init__(self):
        self.sent: list[tuple[str, str, str]] = []

    def __call__(self, to, subject, text):
        self.sent.append((to, subject, text))
        return "logged"

    def token_for(self, to: str) -> str:
        text = [t for (addr, _, t) in self.sent if addr == to][-1]
        return re.search(r"token=([A-Za-z0-9_\-]+)", text).group(1)


class AuthFlowTests(unittest.TestCase):
    def setUp(self):
        self.mail = Mailbox()
        patches = [patch("app.routers.auth.deliver", self.mail), patch("app.routers.team.deliver", self.mail)]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def client(self) -> TestClient:
        return TestClient(app)

    def signup(self, client=None, email=None):
        client = client or self.client()
        email = email or _email()
        res = client.post("/api/auth/signup", json={"email": email, "password": PASSWORD, "name": "Owner", "company_name": "Co"})
        self.assertEqual(res.status_code, 202, res.text)
        # Signup's reply is generic by design; read the new account through a separate session.
        probe = self.client()
        token = probe.post("/api/auth/login", json={"email": email, "password": PASSWORD}).json()["access_token"]
        me = probe.get("/api/auth/me", headers=self.bearer(token)).json()
        probe.post("/api/auth/logout", headers=self.bearer(token))
        return client, email, me

    def login(self, client, email, password=PASSWORD):
        res = client.post("/api/auth/login", json={"email": email, "password": password})
        self.assertEqual(res.status_code, 200, res.text)
        return res

    @staticmethod
    def bearer(token):
        return {"Authorization": f"Bearer {token}"}

    # ── Sessions ───────────────────────────────────────────────────
    def test_login_sets_httponly_refresh_cookie_and_no_body_token(self):
        client, email, _ = self.signup()
        res = self.login(client, email)
        self.assertNotIn("refresh_token", res.json())
        cookie = res.headers["set-cookie"]
        self.assertIn("avn_refresh=", cookie)
        self.assertIn("HttpOnly", cookie)
        self.assertIn("Path=/api/auth", cookie)

    def test_refresh_rotates_and_replay_revokes_every_session(self):
        client, email, _ = self.signup()
        access = self.login(client, email).json()["access_token"]
        old_refresh = client.cookies.get("avn_refresh")

        rotated = client.post("/api/auth/refresh")
        self.assertEqual(rotated.status_code, 200, rotated.text)
        self.assertNotEqual(client.cookies.get("avn_refresh"), old_refresh)
        new_access = rotated.json()["access_token"]
        self.assertEqual(client.get("/api/auth/me", headers=self.bearer(new_access)).status_code, 200)

        self._age_sessions(email, seconds=60)  # past the concurrent-refresh grace window
        attacker = self.client()
        attacker.cookies.set("avn_refresh", old_refresh, path="/api/auth")
        self.assertEqual(attacker.post("/api/auth/refresh").status_code, 401)
        # Replay detected: the legitimate session is revoked too.
        self.assertEqual(client.get("/api/auth/me", headers=self.bearer(new_access)).status_code, 401)
        self.assertEqual(client.get("/api/auth/me", headers=self.bearer(access)).status_code, 401)

    def test_simultaneous_refreshes_from_two_tabs_do_not_sign_out(self):
        client, email, _ = self.signup()
        self.login(client, email)
        cookie = client.cookies.get("avn_refresh")
        first, second = self.client(), self.client()
        for tab in (first, second):
            tab.cookies.set("avn_refresh", cookie, path="/api/auth")
        a = first.post("/api/auth/refresh")
        b = second.post("/api/auth/refresh")  # same cookie, a moment later
        self.assertEqual((a.status_code, b.status_code), (200, 200))
        self.assertEqual(second.get("/api/auth/me", headers=self.bearer(b.json()["access_token"])).status_code, 200)

    @staticmethod
    def _age_sessions(email, seconds):
        from datetime import timedelta
        from app.models.auth import AuthSession
        from app.models.user import User
        db = SessionLocal()
        try:
            user = db.query(User).filter(User.email == email).first()
            for s in db.query(AuthSession).filter(AuthSession.user_id == user.id).all():
                s.last_used_at = s.last_used_at - timedelta(seconds=seconds)
            db.commit()
        finally:
            db.close()

    def test_logout_revokes_access_token_immediately(self):
        client, email, _ = self.signup()
        access = self.login(client, email).json()["access_token"]
        self.assertEqual(client.post("/api/auth/logout", headers=self.bearer(access)).status_code, 204)
        self.assertEqual(client.get("/api/auth/me", headers=self.bearer(access)).status_code, 401)
        self.assertEqual(client.post("/api/auth/refresh").status_code, 401)

    def test_login_is_rate_limited_after_repeated_failures(self):
        client, email, _ = self.signup()
        for _ in range(10):
            self.assertEqual(client.post("/api/auth/login", json={"email": email, "password": "wrong-password"}).status_code, 401)
        self.assertEqual(client.post("/api/auth/login", json={"email": email, "password": PASSWORD}).status_code, 429)

    def test_failed_login_is_audited(self):
        client, email, _ = self.signup()
        client.post("/api/auth/login", json={"email": email, "password": "wrong-password"})
        db = SessionLocal()
        try:
            rows = db.query(AuditLog).filter(AuditLog.action == "login_failed", AuditLog.details.contains(email)).count()
            self.assertEqual(rows, 1)
        finally:
            db.close()

    # ── Email flows ────────────────────────────────────────────────
    def test_signup_sends_verification_and_link_verifies_once(self):
        client, email, user = self.signup()
        self.assertIsNone(user["email_verified_at"])
        token = self.mail.token_for(email)
        self.assertEqual(client.post("/api/auth/verify-email", json={"token": token}).status_code, 204)
        self.assertEqual(client.post("/api/auth/verify-email", json={"token": token}).status_code, 400)
        access = self.login(client, email).json()["access_token"]
        self.assertIsNotNone(client.get("/api/auth/me", headers=self.bearer(access)).json()["email_verified_at"])

    def test_forgot_password_does_not_reveal_accounts(self):
        client = self.client()
        res = client.post("/api/auth/password/forgot", json={"email": _email()})
        self.assertEqual(res.status_code, 202)
        self.assertEqual(self.mail.sent, [])

    def test_password_reset_changes_password_and_ends_sessions(self):
        client, email, _ = self.signup()
        access = self.login(client, email).json()["access_token"]
        self.assertEqual(client.post("/api/auth/password/forgot", json={"email": email}).status_code, 202)
        token = self.mail.token_for(email)

        self.assertEqual(client.post("/api/auth/password/reset", json={"token": token, "password": "short"}).status_code, 422)
        self.assertEqual(client.post("/api/auth/password/reset", json={"token": token, "password": "brand-new-pass-2"}).status_code, 204)
        self.assertEqual(client.get("/api/auth/me", headers=self.bearer(access)).status_code, 401)
        self.assertEqual(client.post("/api/auth/login", json={"email": email, "password": PASSWORD}).status_code, 401)
        self.login(client, email, "brand-new-pass-2")
        self.assertEqual(client.post("/api/auth/password/reset", json={"token": token, "password": "another-pass-33"}).status_code, 400)

    # ── Invitations & team ─────────────────────────────────────────
    def test_invitation_accept_joins_tenant_with_role(self):
        owner, owner_email, owner_user = self.signup()
        access = self.login(owner, owner_email).json()["access_token"]
        invitee = _email()
        res = owner.post("/api/team/invitations", json={"email": invitee, "role": "Manager"}, headers=self.bearer(access))
        self.assertEqual(res.status_code, 201, res.text)
        body = res.json()
        self.assertEqual(body["email_status"], "logged")
        token = re.search(r"token=(.+)$", body["accept_url"]).group(1)

        guest = self.client()
        preview = guest.get(f"/api/auth/invitations/{token}")
        self.assertEqual(preview.status_code, 200)
        self.assertEqual(preview.json()["role"], "Manager")
        self.assertEqual(preview.json()["tenant_name"], "Co")

        accepted = guest.post("/api/auth/invitations/accept", json={"token": token, "name": "New Person", "password": PASSWORD})
        self.assertEqual(accepted.status_code, 200, accepted.text)
        me = guest.get("/api/auth/me", headers=self.bearer(accepted.json()["access_token"])).json()
        self.assertEqual(me["tenant_id"], owner_user["tenant_id"])
        self.assertEqual(me["role"], "Manager")
        self.assertIsNotNone(me["email_verified_at"])

        self.assertEqual(guest.post("/api/auth/invitations/accept", json={"token": token, "name": "X", "password": PASSWORD}).status_code, 404)
        members = owner.get("/api/team/members", headers=self.bearer(access)).json()
        self.assertEqual({m["email"] for m in members}, {owner_email, invitee})

    def test_invitation_permissions(self):
        owner, owner_email, _ = self.signup()
        access = self.login(owner, owner_email).json()["access_token"]
        self.assertEqual(owner.post("/api/team/invitations", json={"email": _email(), "role": "Owner"}, headers=self.bearer(access)).status_code, 422)
        self.assertEqual(owner.post("/api/team/invitations", json={"email": owner_email, "role": "Agent"}, headers=self.bearer(access)).status_code, 409)

        agent_email = _email()
        token = re.search(r"token=(.+)$", owner.post("/api/team/invitations", json={"email": agent_email, "role": "Agent"},
                                                     headers=self.bearer(access)).json()["accept_url"]).group(1)
        agent = self.client()
        agent_access = agent.post("/api/auth/invitations/accept", json={"token": token, "name": "A", "password": PASSWORD}).json()["access_token"]
        self.assertEqual(agent.post("/api/team/invitations", json={"email": _email(), "role": "Viewer"}, headers=self.bearer(agent_access)).status_code, 403)
        self.assertEqual(agent.get("/api/team/members", headers=self.bearer(agent_access)).status_code, 200)
        self.assertEqual(agent.get("/api/config", headers=self.bearer(agent_access)).status_code, 403)

    def test_viewer_is_read_only_everywhere(self):
        owner, owner_email, _ = self.signup()
        access = self.login(owner, owner_email).json()["access_token"]
        token = re.search(r"token=(.+)$", owner.post("/api/team/invitations", json={"email": _email(), "role": "Viewer"},
                                                     headers=self.bearer(access)).json()["accept_url"]).group(1)
        viewer = self.client()
        viewer_access = viewer.post("/api/auth/invitations/accept", json={"token": token, "name": "V", "password": PASSWORD}).json()["access_token"]
        self.assertEqual(viewer.get("/api/crm/leads", headers=self.bearer(viewer_access)).status_code, 200)
        # /api/crm/leads POST has no role check of its own; the Viewer rule still applies.
        res = viewer.post("/api/crm/leads", json={"name": "X", "phone": "+919000000009"}, headers=self.bearer(viewer_access))
        self.assertEqual(res.status_code, 403)
        self.assertEqual(viewer.post("/api/auth/logout", headers=self.bearer(viewer_access)).status_code, 204)

    def test_revoked_invitation_cannot_be_accepted(self):
        owner, owner_email, _ = self.signup()
        access = self.login(owner, owner_email).json()["access_token"]
        body = owner.post("/api/team/invitations", json={"email": _email(), "role": "Agent"}, headers=self.bearer(access)).json()
        token = re.search(r"token=(.+)$", body["accept_url"]).group(1)
        self.assertEqual(owner.delete(f"/api/team/invitations/{body['invitation']['id']}", headers=self.bearer(access)).status_code, 204)
        self.assertEqual(self.client().get(f"/api/auth/invitations/{token}").status_code, 404)
        self.assertEqual(owner.get("/api/team/invitations", headers=self.bearer(access)).json(), [])

    def test_member_role_change_rules_and_session_revocation(self):
        owner, owner_email, owner_user = self.signup()
        access = self.login(owner, owner_email).json()["access_token"]
        member_email = _email()
        token = re.search(r"token=(.+)$", owner.post("/api/team/invitations", json={"email": member_email, "role": "Agent"},
                                                     headers=self.bearer(access)).json()["accept_url"]).group(1)
        member = self.client()
        member_access = member.post("/api/auth/invitations/accept", json={"token": token, "name": "M", "password": PASSWORD}).json()["access_token"]
        member_id = member.get("/api/auth/me", headers=self.bearer(member_access)).json()["id"]

        self.assertEqual(owner.patch(f"/api/team/members/{owner_user['id']}", json={"role": "Agent"}, headers=self.bearer(access)).status_code, 400)
        self.assertEqual(owner.patch(f"/api/team/members/{member_id}", json={"role": "Owner"}, headers=self.bearer(access)).status_code, 422)
        res = owner.patch(f"/api/team/members/{member_id}", json={"role": "Admin"}, headers=self.bearer(access))
        self.assertEqual(res.status_code, 200, res.text)
        self.assertEqual(res.json()["role"], "Admin")
        # Role changes end existing sessions so the old role can't be used.
        self.assertEqual(member.get("/api/auth/me", headers=self.bearer(member_access)).status_code, 401)

        new_access = self.login(member, member_email).json()["access_token"]
        self.assertEqual(member.patch(f"/api/team/members/{owner_user['id']}", json={"status": "inactive"},
                                      headers=self.bearer(new_access)).status_code, 403)

        other_owner, other_email, _ = self.signup()
        other_access = self.login(other_owner, other_email).json()["access_token"]
        self.assertEqual(other_owner.patch(f"/api/team/members/{member_id}", json={"status": "inactive"},
                                           headers=self.bearer(other_access)).status_code, 404)

        self.assertEqual(owner.patch(f"/api/team/members/{member_id}", json={"status": "inactive"}, headers=self.bearer(access)).status_code, 200)
        self.assertEqual(member.post("/api/auth/login", json={"email": member_email, "password": PASSWORD}).status_code, 403)


if __name__ == "__main__":
    unittest.main()
