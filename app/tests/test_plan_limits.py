"""Plan limits: call minutes, AI agents and team members, from the plans file."""
import asyncio
import json
import os
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.core.database import Base, SessionLocal, engine
from app.main import app
from app.models.call import CallLog
from app.models.campaign import Campaign
from app.models.notification import Notification
from app.models.tenant import Tenant
from app.services import campaign_worker, plan_limits
from app.services.workflow_engine import workflow_engine
from app.tests.test_consolidation import _TenantClient

PLANS = {"plans": [
    {"id": "free", "name": "Free", "minutes_included": 5, "limits": {"minutes_per_month": 5, "agents": 1, "members": 2}},
    {"id": "growth", "name": "Growth", "minutes_included": 100, "limits": {"minutes_per_month": 100, "agents": 3},
     "prices": {"stripe": {"price_id": "price_G", "amount": 59, "currency": "USD"}}},
]}
AGENT = {"name": "Aria", "voice": "Aoede", "model": "gemini-2.0-flash-live-001", "instructions": "x", "language": "en"}


class PlanLimitsTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        Base.metadata.create_all(bind=engine)
        cls.client = TestClient(app)

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        plans = Path(tmp.name, "plans.json")
        plans.write_text(json.dumps(PLANS), encoding="utf-8")
        p = patch.dict(os.environ, {"BILLING_PLANS_FILE": str(plans)})
        p.start()
        self.addCleanup(p.stop)
        self.owner = _TenantClient(self.client)

    def use_minutes(self, minutes: float) -> None:
        db = SessionLocal()
        try:
            db.add(CallLog(tenant_id=self.owner.tenant_id, phone_number="+919000000070", direction="inbound",
                           duration_seconds=int(minutes * 60), call_room_id=f"room-{uuid.uuid4().hex[:8]}"))
            db.commit()
        finally:
            db.close()

    def set_plan(self, name: str) -> None:
        db = SessionLocal()
        try:
            db.get(Tenant, self.owner.tenant_id).plan = name
            db.commit()
        finally:
            db.close()


class TestLimits(PlanLimitsTestCase):
    def test_no_plans_file_means_unlimited(self):
        with patch.dict(os.environ, {"BILLING_PLANS_FILE": "does-not-exist.json"}):
            for _ in range(3):
                self.assertEqual(self.owner.post("/api/agents", json=AGENT).status_code, 201)
            usage = self.owner.get("/api/billing").json()["usage"]
            self.assertEqual((usage["minutes_limit"], usage["agents_limit"], usage["outbound_blocked"]), (None, None, False))

    def test_agents(self):
        self.assertEqual(self.owner.post("/api/agents", json=AGENT).status_code, 201)
        res = self.owner.post("/api/agents", json=AGENT)
        self.assertEqual(res.status_code, 402)
        self.assertIn("allows 1 AI agent", res.json()["detail"])
        self.set_plan("Growth")  # a paid plan's limits apply instead
        self.assertEqual(self.owner.post("/api/agents", json=AGENT).status_code, 201)

    def test_members_count_pending_invitations(self):
        with patch("app.routers.team.deliver", return_value="logged"):
            first = self.owner.post("/api/team/invitations", json={"email": "one@example.com", "role": "Agent"})
            self.assertEqual(first.status_code, 201, first.text)
            res = self.owner.post("/api/team/invitations", json={"email": "two@example.com", "role": "Agent"})
            self.assertEqual(res.status_code, 402)
            self.assertIn("allows 2 team members", res.json()["detail"])
            # Sending the same person a fresh invitation doesn't use another seat.
            self.assertEqual(self.owner.post("/api/team/invitations", json={"email": "one@example.com", "role": "Agent"}).status_code, 201)

    def test_minutes_stop_outbound_calls_but_show_usage(self):
        self.use_minutes(4.2)
        usage = self.owner.get("/api/billing").json()["usage"]
        self.assertEqual((usage["minutes_used"], usage["minutes_limit"], usage["outbound_blocked"]), (5, 5, True))
        self.assertNotIn("free", [p["id"] for p in self.owner.get("/api/billing").json()["plans"]])
        with patch("app.routers.calls.dispatch_outbound_call", AsyncMock(return_value={"room": "r"})) as dial:
            res = self.owner.post("/api/call/single", json={"phone": "+919000000071"})
            self.assertEqual(res.status_code, 402)
            self.assertIn("Inbound calls are still answered", res.json()["detail"])
            self.assertEqual(self.owner.post("/api/call/bulk", json={"numbers": ["+919000000072"]}).status_code, 402)
            dial.assert_not_called()
        camp = self.owner.post("/api/crm/campaigns", json={"name": "C", "leads": [{"phone": "9000000073"}]}).json()
        self.assertEqual(self.owner.post(f"/api/crm/campaigns/{camp['id']}/start").status_code, 402)

    def test_running_campaign_pauses_at_the_limit(self):
        camp = self.owner.post("/api/crm/campaigns", json={"name": "Spring", "leads": [{"phone": "9000000074"}]}).json()
        self.assertEqual(self.owner.post(f"/api/crm/campaigns/{camp['id']}/start").status_code, 200)
        self.use_minutes(5)
        jobs = campaign_worker._claim_batch()
        self.assertEqual([j for j in jobs if j["campaign_id"] == camp["id"]], [])
        db = SessionLocal()
        try:
            self.assertEqual(db.get(Campaign, camp["id"]).status, "paused")
            titles = [n.title for n in db.query(Notification).filter(Notification.tenant_id == self.owner.tenant_id,
                                                                    Notification.kind == "campaign_paused")]
        finally:
            db.close()
        self.assertTrue(titles and "Spring" in titles[0])

    def test_workflow_call_step_fails_with_the_reason(self):
        wf = self.owner.post("/api/crm/workflows", json={"name": "Call back", "trigger_event": "lead_created",
                                                        "actions": [{"type": "ai_call", "config": {}}]}).json()
        self.use_minutes(6)
        lead = self.owner.post("/api/crm/leads", json={"name": "L", "phone": "+9190000" + str(uuid.uuid4().int)[:5]}).json()
        with patch("app.services.workflow_engine.dispatch_outbound_call", AsyncMock()) as dial:
            asyncio.run(workflow_engine._execute_workflows("lead_created", lead["id"], self.owner.tenant_id))
            dial.assert_not_called()
        run = self.owner.get(f"/api/crm/workflows/{wf['id']}/runs").json()[0]
        self.assertEqual(run["status"], "failed")
        self.assertIn("call minutes", run["message"])


class TestAlerts(PlanLimitsTestCase):
    def kinds(self) -> list[str]:
        db = SessionLocal()
        try:
            return [n.kind for n in db.query(Notification).filter(Notification.tenant_id == self.owner.tenant_id,
                                                                  Notification.kind.like("usage_%"))]
        finally:
            db.close()

    def test_warning_then_limit_once_each(self):
        sent: list[tuple[str, str]] = []
        with patch("app.services.mailer.deliver", side_effect=lambda to, subject, body: sent.append((to, subject)) or "sent"):
            self.use_minutes(3)
            plan_limits.check_alerts()
            self.assertEqual(self.kinds(), [])
            self.use_minutes(1)  # 4 of 5 = 80%
            plan_limits.check_alerts()
            plan_limits.check_alerts()
            self.assertEqual(self.kinds(), ["usage_warning"])
            self.use_minutes(1)
            plan_limits.check_alerts()
            plan_limits.check_alerts()
            self.assertEqual(sorted(self.kinds()), ["usage_limit", "usage_warning"])
        mine = [subject for to, subject in sent if to == self.owner.get("/api/auth/me").json()["email"]]
        self.assertEqual(mine, ["aVn: 4 of 5 call minutes used this month", "aVn: All 5 call minutes for this month are used"])


if __name__ == "__main__":
    unittest.main()
