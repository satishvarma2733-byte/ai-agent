"""Agent versions: drafts, change log, validation, lifecycle, rollback, permissions, isolation."""
import re
import unittest
import uuid
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app

PASSWORD = "correct-horse-1"


class AgentVersionTests(unittest.TestCase):
    def setUp(self):
        mail = patch("app.routers.team.deliver", return_value="logged")
        mail.start()
        self.addCleanup(mail.stop)
        patch("app.routers.auth.deliver", return_value="logged").start()
        self.addCleanup(patch.stopall)
        self.owner, self.owner_headers, self.tenant = self._signup()

    def _signup(self):
        client = TestClient(app)
        email = f"o-{uuid.uuid4().hex[:10]}@example.com"
        res = client.post("/api/auth/signup", json={"email": email, "password": PASSWORD, "name": "Owner", "company_name": "Co"})
        token = client.post("/api/auth/login", json={"email": email, "password": PASSWORD}).json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        return client, headers, client.get("/api/auth/me", headers=headers).json()["tenant_id"]

    def _member(self, role):
        body = self.owner.post("/api/team/invitations", json={"email": f"m-{uuid.uuid4().hex[:8]}@example.com", "role": role},
                               headers=self.owner_headers).json()
        token = re.search(r"token=(.+)$", body["accept_url"]).group(1)
        client = TestClient(app)
        access = client.post("/api/auth/invitations/accept", json={"token": token, "name": role, "password": PASSWORD}).json()["access_token"]
        return client, {"Authorization": f"Bearer {access}"}

    def create_agent(self, **fields):
        payload = {"name": "Aria", "voice": "Puck", "model": "gemini-2.0-flash-live-001", "instructions": "Be kind.",
                   "language": "te", "greeting": "నమస్కారం", "temperature": 0.6, **fields}
        res = self.owner.post("/api/agents", json=payload, headers=self.owner_headers)
        self.assertEqual(res.status_code, 201, res.text)
        return res.json()

    def act(self, agent_id, number, action, headers=None, expected=200):
        res = self.owner.post(f"/api/agents/{agent_id}/versions/{number}/{action}", json={}, headers=headers or self.owner_headers)
        self.assertEqual(res.status_code, expected, res.text)
        return res.json()

    def promote(self, agent_id, number):
        for action in ("submit", "evaluate", "approve", "activate"):
            self.act(agent_id, number, action)

    def test_create_stores_everything_in_a_draft(self):
        agent = self.create_agent()
        self.assertEqual(agent["lifecycle"], "draft")
        self.assertEqual(agent["draft_version"], 1)
        self.assertIsNone(agent["production_version"])
        self.assertEqual((agent["instructions"], agent["language"], agent["greeting"]), ("Be kind.", "te", "నమస్కారం"))
        v1 = self.owner.get(f"/api/agents/{agent['id']}/versions/1", headers=self.owner_headers).json()
        self.assertEqual(v1["config"]["languages"]["supported"], ["te", "en"])
        self.assertEqual(v1["config"]["greetings"], {"te": "నమస్కారం"})
        changes = self.owner.get(f"/api/agents/{agent['id']}/changes", headers=self.owner_headers).json()
        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0]["reason"], "Agent created")

    def test_agent_in_review_shows_its_own_settings(self):
        agent = self.create_agent(voice="Aoede")
        self.act(agent["id"], 1, "submit")
        detail = self.owner.get(f"/api/agents/{agent['id']}", headers=self.owner_headers).json()
        self.assertEqual((detail["lifecycle"], detail["voice"], detail["instructions"]), ("testing", "Aoede", "Be kind."))

    def test_invalid_config_is_rejected(self):
        res = self.owner.post("/api/agents", json={"name": "X", "temperature": 5}, headers=self.owner_headers)
        self.assertEqual(res.status_code, 422)
        self.assertIn("llm.temperature", res.json()["detail"])
        agent = self.create_agent()
        res = self.owner.patch(f"/api/agents/{agent['id']}/draft", json={"patch": {"languages": {"default": "xx"}}, "reason": "try"},
                               headers=self.owner_headers)
        self.assertEqual(res.status_code, 422)
        res = self.owner.patch(f"/api/agents/{agent['id']}/draft", json={"patch": {"unknown": 1}, "reason": "try"}, headers=self.owner_headers)
        self.assertEqual(res.status_code, 422)

    def test_edits_after_production_go_to_a_new_draft(self):
        agent = self.create_agent()
        self.promote(agent["id"], 1)
        res = self.owner.patch(f"/api/agents/{agent['id']}/draft",
                               json={"patch": {"instructions": "Be concise."}, "reason": "Shorter answers"}, headers=self.owner_headers)
        self.assertEqual(res.status_code, 200, res.text)
        body = res.json()
        self.assertEqual(body["version"]["number"], 2)
        self.assertEqual(body["changes"], [{"path": "instructions", "before": "Be kind.", "after": "Be concise."}])

        v1 = self.owner.get(f"/api/agents/{agent['id']}/versions/1", headers=self.owner_headers).json()
        self.assertEqual(v1["config"]["instructions"], "Be kind.", "production must not change")
        detail = self.owner.get(f"/api/agents/{agent['id']}", headers=self.owner_headers).json()
        self.assertEqual((detail["lifecycle"], detail["production_version"], detail["draft_version"]), ("production", 1, 2))

        # No-op edits don't create change records.
        again = self.owner.patch(f"/api/agents/{agent['id']}/draft",
                                 json={"patch": {"instructions": "Be concise."}, "reason": "same"}, headers=self.owner_headers).json()
        self.assertEqual(again["changes"], [])
        diff = self.owner.get(f"/api/agents/{agent['id']}/compare?from=1&to=2", headers=self.owner_headers).json()
        self.assertEqual([c["path"] for c in diff["changes"]], ["instructions"])

    def test_activate_supersedes_and_rollback_restores(self):
        agent = self.create_agent()
        self.promote(agent["id"], 1)
        self.owner.patch(f"/api/agents/{agent['id']}/draft", json={"patch": {"voice": {"voice": "Aoede"}}, "reason": "New voice"},
                         headers=self.owner_headers)
        self.promote(agent["id"], 2)
        versions = {v["number"]: v["status"] for v in self.owner.get(f"/api/agents/{agent['id']}/versions", headers=self.owner_headers).json()}
        self.assertEqual(versions, {1: "superseded", 2: "production"})
        self.assertEqual(self.owner.get(f"/api/agents/{agent['id']}", headers=self.owner_headers).json()["voice"], "Aoede")

        self.act(agent["id"], 1, "rollback")
        versions = {v["number"]: v["status"] for v in self.owner.get(f"/api/agents/{agent['id']}/versions", headers=self.owner_headers).json()}
        self.assertEqual(versions, {1: "production", 2: "superseded"})
        actions = [e["action"] for e in self.owner.get(f"/api/agents/{agent['id']}/events", headers=self.owner_headers).json()]
        self.assertIn("rollback", actions)

    def test_invalid_transitions(self):
        agent = self.create_agent()
        self.act(agent["id"], 1, "activate", expected=409)
        self.act(agent["id"], 1, "submit")
        self.act(agent["id"], 1, "reject")
        self.act(agent["id"], 1, "rollback", expected=409)
        self.act(agent["id"], 1, "fly", expected=404)
        # A rejected v1 means the next edit starts draft v2 from it.
        res = self.owner.patch(f"/api/agents/{agent['id']}/draft", json={"patch": {"instructions": "v2"}, "reason": "retry"},
                               headers=self.owner_headers)
        self.assertEqual(res.json()["version"]["number"], 2)

    def test_draft_discard_rules(self):
        agent = self.create_agent()
        self.assertEqual(self.owner.delete(f"/api/agents/{agent['id']}/draft", headers=self.owner_headers).status_code, 409)
        self.promote(agent["id"], 1)
        self.owner.patch(f"/api/agents/{agent['id']}/draft", json={"patch": {"instructions": "x"}, "reason": "try"}, headers=self.owner_headers)
        self.assertEqual(self.owner.delete(f"/api/agents/{agent['id']}/draft", headers=self.owner_headers).status_code, 204)
        detail = self.owner.get(f"/api/agents/{agent['id']}", headers=self.owner_headers).json()
        self.assertIsNone(detail["draft_version"])
        self.assertEqual(detail["instructions"], "Be kind.")

    def test_disabled_agent_cannot_change_or_activate(self):
        agent = self.create_agent()
        self.act(agent["id"], 1, "submit")
        self.act(agent["id"], 1, "evaluate")
        self.act(agent["id"], 1, "approve")
        self.assertEqual(self.owner.post(f"/api/agents/{agent['id']}/disable", json={}, headers=self.owner_headers).json()["lifecycle"], "disabled")
        self.act(agent["id"], 1, "activate", expected=409)
        res = self.owner.put(f"/api/agents/{agent['id']}", json={"instructions": "x"}, headers=self.owner_headers)
        self.assertEqual(res.status_code, 409)
        self.owner.post(f"/api/agents/{agent['id']}/enable", headers=self.owner_headers)
        self.act(agent["id"], 1, "activate")

    def test_role_requirements(self):
        agent = self.create_agent()
        manager, manager_headers = self._member("Manager")
        agent_role, agent_headers = self._member("Agent")
        self.assertEqual(agent_role.post("/api/agents", json={"name": "Nope"}, headers=agent_headers).status_code, 403)
        self.assertEqual(manager.put(f"/api/agents/{agent['id']}", json={"instructions": "m"}, headers=manager_headers).status_code, 200)
        for action in ("submit", "evaluate"):
            self.act(agent["id"], 1, action, headers=manager_headers)
        self.act(agent["id"], 1, "approve", headers=manager_headers, expected=403)
        self.act(agent["id"], 1, "approve")
        self.act(agent["id"], 1, "activate", headers=manager_headers, expected=403)
        self.assertEqual(manager.delete(f"/api/agents/{agent['id']}", headers=manager_headers).status_code, 403)

    def test_tenant_isolation_and_delete(self):
        agent = self.create_agent()
        other, other_headers, _ = self._signup()
        self.assertEqual(other.get(f"/api/agents/{agent['id']}", headers=other_headers).status_code, 404)
        self.assertEqual(other.get(f"/api/agents/{agent['id']}/versions", headers=other_headers).status_code, 404)
        self.assertEqual(other.get("/api/agents", headers=other_headers).json(), [])
        self.promote(agent["id"], 1)
        self.assertEqual(self.owner.delete(f"/api/agents/{agent['id']}", headers=self.owner_headers).status_code, 200)
        self.assertEqual(self.owner.get(f"/api/agents/{agent['id']}", headers=self.owner_headers).status_code, 404)


if __name__ == "__main__":
    unittest.main()
