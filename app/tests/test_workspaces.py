"""One account in several workspaces (RBAC-04): joining with an existing account, switching per device,
roles and status per workspace, removal, and new workspaces."""
import unittest
import uuid
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.core.database import Base, SessionLocal, engine
from app.core.security import get_password_hash
from app.main import app
from app.models.lead import Lead
from app.models.membership import Membership
from app.models.tenant import Tenant
from app.models.user import User

PASSWORD = "correct-horse-1"


def _phone() -> str:
    return "+9198" + str(uuid.uuid4().int)[:8]


class Person:
    """An account signed in on one device (its own TestClient, so refresh cookies don't mix)."""
    def __init__(self, email: str | None = None, *, signup: bool = True):
        self.client = TestClient(app)
        self.email = email or f"ws-{uuid.uuid4().hex[:10]}@example.com"
        if signup:
            res = self.client.post("/api/auth/signup", json={"email": self.email, "password": PASSWORD, "name": "Asha Rao", "company_name": f"Co {uuid.uuid4().hex[:4]}"})
            assert res.status_code == 202, res.text
        self.login()

    def login(self):
        res = self.client.post("/api/auth/login", json={"email": self.email, "password": PASSWORD})
        assert res.status_code == 200, res.text
        self.use(res.json()["access_token"])

    def use(self, token):
        self.headers = {"Authorization": f"Bearer {token}"}

    def me(self):
        return self.client.get("/api/auth/me", headers=self.headers).json()

    def __getattr__(self, method):
        fn = getattr(self.client, method)
        return lambda url, **kw: fn(url, headers=self.headers, **kw)


def invite(owner: Person, email: str, role: str) -> str:
    with patch("app.routers.team.deliver", return_value="logged"):
        res = owner.post("/api/team/invitations", json={"email": email, "role": role})
    assert res.status_code == 201, res.text
    return res.json()["accept_url"].split("token=")[1]


class WorkspacesTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        Base.metadata.create_all(bind=engine)

    def setUp(self):
        self.a = Person()                 # owns workspace A
        self.b = Person()                 # owns workspace B
        self.tenant_a, self.tenant_b = self.a.me()["tenant_id"], self.b.me()["tenant_id"]

    def join_a(self, role="Agent", password=PASSWORD):
        token = invite(self.a, self.b.email, role)
        return self.b.client.post("/api/auth/invitations/accept", json={"token": token, "password": password})


class TestJoining(WorkspacesTestCase):
    def test_existing_account_joins_with_its_password(self):
        token = invite(self.a, self.b.email, "Manager")
        preview = self.b.client.get(f"/api/auth/invitations/{token}").json()
        self.assertTrue(preview["existing_account"])
        wrong = self.b.client.post("/api/auth/invitations/accept", json={"token": token, "password": "not-the-password"})
        self.assertEqual(wrong.status_code, 401)
        ok = self.b.client.post("/api/auth/invitations/accept", json={"token": token, "password": PASSWORD})
        self.assertEqual(ok.status_code, 200, ok.text)
        self.b.use(ok.json()["access_token"])
        me = self.b.me()
        self.assertEqual((me["tenant_id"], me["role"]), (self.tenant_a, "Manager"))
        spaces = {w["id"]: w for w in self.b.get("/api/auth/workspaces").json()}
        self.assertEqual({k: (v["role"], v["current"]) for k, v in spaces.items()},
                         {self.tenant_a: ("Manager", True), self.tenant_b: ("Owner", False)})
        reused = self.b.client.post("/api/auth/invitations/accept", json={"token": token, "password": PASSWORD})
        self.assertEqual(reused.status_code, 404)  # the invitation was used
        with patch("app.routers.team.deliver", return_value="logged"):
            dup = self.a.post("/api/team/invitations", json={"email": self.b.email, "role": "Agent"})
        self.assertEqual(dup.status_code, 409)

    def test_new_accounts_still_need_a_name_and_long_password(self):
        email = f"new-{uuid.uuid4().hex[:8]}@example.com"
        token = invite(self.a, email, "Agent")
        c = TestClient(app)
        self.assertFalse(c.get(f"/api/auth/invitations/{token}").json()["existing_account"])
        self.assertEqual(c.post("/api/auth/invitations/accept", json={"token": token, "password": PASSWORD}).status_code, 422)
        self.assertEqual(c.post("/api/auth/invitations/accept", json={"token": token, "name": "Ravi", "password": "short"}).status_code, 422)
        self.assertEqual(c.post("/api/auth/invitations/accept", json={"token": token, "name": "Ravi", "password": PASSWORD}).status_code, 200)


class TestSwitching(WorkspacesTestCase):
    def setUp(self):
        super().setUp()
        self.assertEqual(self.join_a("Agent").status_code, 200)
        self.b.login()  # signs in to the workspace used last: A

    def test_data_and_role_follow_the_current_workspace(self):
        self.assertEqual(self.b.me()["tenant_id"], self.tenant_a)
        self.a.post("/api/crm/leads", json={"name": "Lead in A", "phone": _phone()})
        names = lambda p: {lead["name"] for lead in p.get("/api/crm/leads").json()}  # noqa: E731
        self.assertIn("Lead in A", names(self.b))
        self.assertEqual(self.b.get("/api/team/invitations").status_code, 403)  # an Agent in A
        res = self.b.post("/api/auth/workspaces/switch", json={"tenant_id": self.tenant_b})
        self.assertEqual(res.status_code, 200, res.text)
        self.b.use(res.json()["access_token"])
        self.assertEqual((self.b.me()["tenant_id"], self.b.me()["role"]), (self.tenant_b, "Owner"))
        self.assertNotIn("Lead in A", names(self.b))
        self.assertEqual(self.b.get("/api/team/invitations").status_code, 200)  # Owner in B

    def test_each_device_keeps_its_own_workspace(self):
        phone = Person(self.b.email, signup=False)  # a second device, also in A
        res = self.b.post("/api/auth/workspaces/switch", json={"tenant_id": self.tenant_b})
        self.b.use(res.json()["access_token"])
        self.assertEqual(phone.me()["tenant_id"], self.tenant_a)
        self.assertEqual(self.b.me()["tenant_id"], self.tenant_b)
        refreshed = self.b.client.post("/api/auth/refresh")
        self.assertEqual(refreshed.status_code, 200)
        self.b.use(refreshed.json()["access_token"])
        self.assertEqual(self.b.me()["tenant_id"], self.tenant_b)
        # the next sign-in starts where the person was last
        third = Person(self.b.email, signup=False)
        self.assertEqual(third.me()["tenant_id"], self.tenant_b)

    def test_cannot_switch_into_a_workspace_you_are_not_in(self):
        stranger = Person()
        self.assertEqual(self.b.post("/api/auth/workspaces/switch", json={"tenant_id": stranger.me()["tenant_id"]}).status_code, 404)

    def test_team_lists_show_the_role_in_that_workspace(self):
        in_a = {m["email"]: m["role"] for m in self.a.get("/api/team/members").json()}
        in_b = {m["email"]: m["role"] for m in self.b.get("/api/team/members").json()}  # b is in A right now
        self.assertEqual(in_a, in_b)
        self.assertEqual(in_a[self.b.email], "Agent")
        res = self.b.post("/api/auth/workspaces/switch", json={"tenant_id": self.tenant_b})
        self.b.use(res.json()["access_token"])
        self.assertEqual({m["email"]: m["role"] for m in self.b.get("/api/team/members").json()}, {self.b.email: "Owner"})


class TestStatusAndRemoval(WorkspacesTestCase):
    def setUp(self):
        super().setUp()
        self.assertEqual(self.join_a("Agent").status_code, 200)
        self.b.login()
        self.b_id = self.b.me()["id"]

    def test_deactivating_in_one_workspace_leaves_the_other(self):
        res = self.a.patch(f"/api/team/members/{self.b_id}", json={"status": "inactive"})
        self.assertEqual(res.json()["status"], "inactive")
        self.assertEqual(self.b.client.get("/api/auth/me", headers=self.b.headers).status_code, 401)  # signed out of A
        self.b.login()
        self.assertEqual(self.b.me()["tenant_id"], self.tenant_b)
        self.assertEqual([w["id"] for w in self.b.get("/api/auth/workspaces").json()], [self.tenant_b])
        self.assertEqual(self.b.post("/api/auth/workspaces/switch", json={"tenant_id": self.tenant_a}).status_code, 404)
        self.a.patch(f"/api/team/members/{self.b_id}", json={"status": "active"})
        self.assertEqual(self.b.post("/api/auth/workspaces/switch", json={"tenant_id": self.tenant_a}).status_code, 200)

    def test_role_change_signs_out_only_that_workspace(self):
        other_device = Person(self.b.email, signup=False)
        res = other_device.post("/api/auth/workspaces/switch", json={"tenant_id": self.tenant_b})
        other_device.use(res.json()["access_token"])
        self.a.patch(f"/api/team/members/{self.b_id}", json={"role": "Manager"})
        self.assertEqual(self.b.client.get("/api/auth/me", headers=self.b.headers).status_code, 401)
        self.assertEqual(other_device.client.get("/api/auth/me", headers=other_device.headers).status_code, 200)

    def test_removal_keeps_an_account_with_other_workspaces(self):
        lead = self.a.post("/api/crm/leads", json={"name": "Assigned", "phone": _phone(), "assigned_user_id": self.b_id}).json()
        self.assertEqual(self.a.delete(f"/api/team/members/{self.b_id}").status_code, 204)
        db = SessionLocal()
        try:
            self.assertIsNotNone(db.get(User, self.b_id))
            self.assertIsNone(db.get(Lead, lead["id"]).assigned_user_id)
            self.assertEqual({m.tenant_id for m in db.query(Membership).filter(Membership.user_id == self.b_id)}, {self.tenant_b})
        finally:
            db.close()
        self.b.login()
        self.assertEqual(self.b.me()["tenant_id"], self.tenant_b)
        self.assertNotIn(self.b.email, {m["email"] for m in self.a.get("/api/team/members").json()})


class TestNewWorkspace(WorkspacesTestCase):
    def test_create_and_switch(self):
        res = self.a.post("/api/auth/workspaces", json={"name": "Second clinic"})
        self.assertEqual(res.status_code, 201, res.text)
        self.a.use(res.json()["access_token"])
        me = self.a.me()
        self.assertNotEqual(me["tenant_id"], self.tenant_a)
        self.assertEqual(me["role"], "Owner")
        names = {w["name"]: w["current"] for w in self.a.get("/api/auth/workspaces").json()}
        self.assertTrue(names["Second clinic"])
        self.assertEqual(len(names), 2)
        self.assertEqual(self.a.get("/api/crm/leads").json(), [])


class TestLegacyAccounts(unittest.TestCase):
    def test_account_without_memberships_gets_one_at_sign_in(self):
        db = SessionLocal()
        email = f"legacy-{uuid.uuid4().hex[:8]}@example.com"
        try:
            tenant = Tenant(name="Old workspace")
            db.add(tenant)
            db.flush()
            db.add(User(email=email, name="Old", hashed_password=get_password_hash(PASSWORD), role="Admin",
                        status="active", tenant_id=tenant.id))
            db.commit()
            tenant_id = tenant.id
        finally:
            db.close()
        person = Person(email, signup=False)
        me = person.me()
        self.assertEqual((me["tenant_id"], me["role"]), (tenant_id, "Admin"))
        self.assertEqual(person.get("/api/team/members").json()[0]["role"], "Admin")
