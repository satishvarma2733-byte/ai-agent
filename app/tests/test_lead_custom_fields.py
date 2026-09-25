"""Workspace-defined lead fields."""
import asyncio
import unittest
import uuid

from fastapi.testclient import TestClient

from app.core.database import Base, engine
from app.main import app
from app.tests.test_consolidation import _TenantClient


def _phone() -> str:
    return "+9194" + str(uuid.uuid4().int)[:8]


class TestLeadCustomFields(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        Base.metadata.create_all(bind=engine)
        cls.client = TestClient(app)

    def _fields(self, owner):
        created = {}
        for body in ({"label": "Budget", "field_type": "number"},
                     {"label": "Property type", "field_type": "select", "options": ["Flat", "Villa", "flat", " "]},
                     {"label": "Site visit", "field_type": "date"},
                     {"label": "Loan needed", "field_type": "boolean"}):
            res = owner.post("/api/crm/fields", json=body)
            self.assertEqual(res.status_code, 201, res.text)
            created[res.json()["key"]] = res.json()
        return created

    def test_define_fields(self):
        owner = _TenantClient(self.client)
        fields = self._fields(owner)
        self.assertEqual(set(fields), {"budget", "property_type", "site_visit", "loan_needed"})
        self.assertEqual(fields["property_type"]["options"], ["Flat", "Villa"])
        self.assertEqual(owner.post("/api/crm/fields", json={"label": "Budget", "field_type": "text"}).status_code, 409)
        self.assertEqual(owner.post("/api/crm/fields", json={"label": "Empty", "field_type": "select", "options": []}).status_code, 422)
        # Another workspace has its own (empty) set.
        self.assertEqual(_TenantClient(self.client).get("/api/crm/fields").json(), [])
        renamed = owner.patch(f"/api/crm/fields/{fields['budget']['id']}", json={"label": "Budget (INR)"})
        self.assertEqual((renamed.json()["label"], renamed.json()["key"]), ("Budget (INR)", "budget"))

    def test_values_are_validated_and_merged(self):
        owner = _TenantClient(self.client)
        self._fields(owner)
        lead = owner.post("/api/crm/leads", json={"name": "C", "phone": _phone(), "custom_fields": {
            "budget": "7,500,000", "property_type": "villa", "site_visit": "2026-11-02", "loan_needed": "yes"}})
        self.assertEqual(lead.status_code, 201, lead.text)
        self.assertEqual(lead.json()["custom_fields"],
                         {"budget": 7500000, "property_type": "Villa", "site_visit": "2026-11-02", "loan_needed": True})
        lid = lead.json()["id"]
        for bad in ({"budget": "lots"}, {"property_type": "Castle"}, {"site_visit": "soon"}, {"unknown": 1}):
            self.assertEqual(owner.put(f"/api/crm/leads/{lid}", json={"custom_fields": bad}).status_code, 422, bad)
        merged = owner.put(f"/api/crm/leads/{lid}", json={"custom_fields": {"budget": "", "loan_needed": "no"}}).json()
        self.assertEqual(merged["custom_fields"], {"property_type": "Villa", "site_visit": "2026-11-02", "loan_needed": False})

    def test_deleting_a_field_removes_its_values(self):
        owner = _TenantClient(self.client)
        fields = self._fields(owner)
        lid = owner.post("/api/crm/leads", json={"name": "D", "phone": _phone(), "custom_fields": {"budget": 10, "loan_needed": True}}).json()["id"]
        self.assertEqual(owner.delete(f"/api/crm/fields/{fields['budget']['id']}").status_code, 204)
        lead = next(l for l in owner.get("/api/crm/leads").json() if l["id"] == lid)
        self.assertEqual(lead["custom_fields"], {"loan_needed": True})

    def test_import_and_workflow_use_custom_fields(self):
        from app.services.workflow_engine import workflow_engine
        owner = _TenantClient(self.client)
        self._fields(owner)
        p1, p2 = _phone(), _phone()
        csv_text = f"name,phone,Budget,Property type\nA,{p1},5000000,Flat\nB,{p2},cheap,Flat\n"
        res = owner.post("/api/crm/leads/import", files={"file": ("l.csv", csv_text.encode(), "text/csv")}).json()
        self.assertEqual(res["created"], 1)
        self.assertIn("Budget must be a number", res["skipped"][0]["reason"])
        lead = next(l for l in owner.get("/api/crm/leads").json() if l["phone"] == p1)
        self.assertEqual(lead["custom_fields"], {"budget": 5000000, "property_type": "Flat"})
        owner.post("/api/crm/workflows", json={"name": "Tag", "trigger_event": "lead_created", "actions": [
            {"type": "update_crm", "config": {"field": "custom.property_type", "value": "villa"}}]})
        asyncio.run(workflow_engine._execute_workflows("lead_created", lead["id"], owner.tenant_id))
        lead = next(l for l in owner.get("/api/crm/leads").json() if l["phone"] == p1)
        self.assertEqual(lead["custom_fields"]["property_type"], "Villa")

    def test_only_admins_define_fields(self):
        from unittest.mock import patch
        owner = _TenantClient(self.client)
        email = f"m-{uuid.uuid4().hex[:6]}@example.com"
        with patch("app.routers.team.deliver", return_value="logged"):
            token = owner.post("/api/team/invitations", json={"email": email, "role": "Manager"}).json()["accept_url"].split("token=")[1]
        access = self.client.post("/api/auth/invitations/accept", json={"token": token, "name": "M", "password": "correct-horse-1"}).json()["access_token"]
        headers = {"Authorization": f"Bearer {access}"}
        self.assertEqual(self.client.post("/api/crm/fields", json={"label": "X", "field_type": "text"}, headers=headers).status_code, 403)
        self.assertEqual(self.client.get("/api/crm/fields", headers=headers).status_code, 200)


if __name__ == "__main__":
    unittest.main()
