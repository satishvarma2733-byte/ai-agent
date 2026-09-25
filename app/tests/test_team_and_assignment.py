"""Member removal, ownership transfer, and lead assignment."""
import asyncio
import unittest
import uuid
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.core.database import Base, engine
from app.main import app
from app.tests.test_consolidation import _TenantClient

PASSWORD = "correct-horse-1"


def _phone() -> str:
    return "+9196" + str(uuid.uuid4().int)[:8]


class TestTeamAndAssignment(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        Base.metadata.create_all(bind=engine)
        cls.client = TestClient(app)

    def _member(self, owner: _TenantClient, role: str, name: str = "Member") -> tuple[str, dict]:
        email = f"m-{uuid.uuid4().hex[:8]}@example.com"
        with patch("app.routers.team.deliver", return_value="logged"):
            token = owner.post("/api/team/invitations", json={"email": email, "role": role}).json()["accept_url"].split("token=")[1]
        access = self.client.post("/api/auth/invitations/accept", json={"token": token, "name": name, "password": PASSWORD}).json()["access_token"]
        headers = {"Authorization": f"Bearer {access}"}
        user_id = self.client.get("/api/auth/me", headers=headers).json()["id"]
        return user_id, headers

    def test_remove_member(self):
        owner = _TenantClient(self.client)
        admin_id, admin = self._member(owner, "Admin")
        agent_id, agent = self._member(owner, "Agent", "Asha")
        lead = owner.post("/api/crm/leads", json={"name": "L", "phone": _phone(), "assigned_user_id": agent_id}).json()
        # Admins can't remove the owner or themselves; other tenants can't remove anyone here.
        owner_id = owner.get("/api/auth/me").json()["id"]
        self.assertEqual(self.client.delete(f"/api/team/members/{owner_id}", headers=admin).status_code, 403)
        self.assertEqual(self.client.delete(f"/api/team/members/{admin_id}", headers=admin).status_code, 400)
        self.assertEqual(_TenantClient(self.client).delete(f"/api/team/members/{agent_id}").status_code, 404)
        self.assertEqual(self.client.delete(f"/api/team/members/{admin_id}", headers=agent).status_code, 403)
        self.assertEqual(self.client.delete(f"/api/team/members/{agent_id}", headers=admin).status_code, 204)
        self.assertEqual(self.client.get("/api/auth/me", headers=agent).status_code, 401)
        self.assertNotIn(agent_id, [m["id"] for m in owner.get("/api/team/members").json()])
        refreshed = next(l for l in owner.get("/api/crm/leads").json() if l["id"] == lead["id"])
        self.assertIsNone(refreshed["assigned_user_id"])

    def test_transfer_ownership(self):
        owner = _TenantClient(self.client)
        admin_id, admin = self._member(owner, "Admin")
        self.assertEqual(self.client.post("/api/team/transfer-ownership", json={"user_id": admin_id}, headers=admin).status_code, 403)
        res = owner.post("/api/team/transfer-ownership", json={"user_id": admin_id})
        self.assertEqual(res.status_code, 200, res.text)
        roles = {m["id"]: m["role"] for m in owner.get("/api/team/members").json()}
        self.assertEqual(roles[admin_id], "Owner")
        self.assertEqual(roles[owner.get("/api/auth/me").json()["id"]], "Admin")
        # The previous owner can no longer transfer.
        self.assertEqual(owner.post("/api/team/transfer-ownership", json={"user_id": admin_id}).status_code, 403)

    def test_assign_leads_and_my_leads(self):
        owner = _TenantClient(self.client)
        agent_id, agent = self._member(owner, "Agent", "Ravi")
        mine = owner.post("/api/crm/leads", json={"name": "Mine", "phone": _phone()}).json()
        other = owner.post("/api/crm/leads", json={"name": "Other", "phone": _phone()}).json()
        res = owner.put(f"/api/crm/leads/{mine['id']}", json={"assigned_user_id": agent_id})
        self.assertEqual(res.status_code, 200, res.text)
        self.assertEqual(res.json()["assigned_agent"], "Ravi")
        my = self.client.get("/api/crm/leads?assigned_to=me", headers=agent).json()
        self.assertEqual([l["id"] for l in my], [mine["id"]])
        unassigned = owner.get("/api/crm/leads?assigned_to=unassigned").json()
        self.assertEqual([l["id"] for l in unassigned], [other["id"]])
        timeline = owner.get(f"/api/crm/leads/{mine['id']}/timeline").json()
        self.assertIn("Lead assigned", [a["title"] for a in timeline])
        # Someone from another workspace can't be the assignee.
        stranger_id = _TenantClient(self.client).get("/api/auth/me").json()["id"]
        self.assertEqual(owner.put(f"/api/crm/leads/{other['id']}", json={"assigned_user_id": stranger_id}).status_code, 422)

    def test_form_blanks_are_accepted(self):
        owner = _TenantClient(self.client)
        # The CRM form sends "" for untouched optional fields.
        res = owner.post("/api/crm/leads", json={"name": "Blank", "phone": _phone(), "email": "", "company": "", "assigned_user_id": ""})
        self.assertEqual(res.status_code, 201, res.text)
        self.assertIsNone(res.json()["email"])
        self.assertEqual(owner.put(f"/api/crm/leads/{res.json()['id']}", json={"email": ""}).status_code, 200)

    def test_workflow_assigns_to_real_member(self):
        from app.services.workflow_engine import workflow_engine
        owner = _TenantClient(self.client)
        agent_id, _ = self._member(owner, "Agent", "Meera")
        owner.post("/api/crm/workflows", json={"name": "Assign", "trigger_event": "lead_created",
                                                "actions": [{"type": "assign_lead", "config": {"agent": "meera"}}]})
        lead = owner.post("/api/crm/leads", json={"name": "Auto", "phone": _phone()}).json()
        asyncio.run(workflow_engine._execute_workflows("lead_created", lead["id"], owner.tenant_id))
        refreshed = next(l for l in owner.get("/api/crm/leads").json() if l["id"] == lead["id"])
        self.assertEqual(refreshed["assigned_user_id"], agent_id)


if __name__ == "__main__":
    unittest.main()
