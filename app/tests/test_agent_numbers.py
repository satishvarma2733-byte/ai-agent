"""Per-agent business numbers and call routing."""
import unittest
import uuid

from fastapi.testclient import TestClient

from app.core.database import Base, engine
from app.main import app
from app.services.agent_runtime import resolve_for_call, runtime_overrides
from app.tests.test_consolidation import _TenantClient


def _number() -> str:
    return "+9140" + str(uuid.uuid4().int)[:8]


class TestAgentNumbers(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        Base.metadata.create_all(bind=engine)
        cls.client = TestClient(app)

    def _agent(self, owner, promote=True, **fields):
        payload = {"name": "Aria", "voice": "Aoede", "model": "gemini-2.0-flash-live-001", "instructions": "Be kind.",
                   "language": "te", "greeting": "నమస్కారం", "temperature": 0.6, **fields}
        agent = owner.post("/api/agents", json=payload).json()
        if promote:
            for action in ("submit", "evaluate", "approve", "activate"):
                res = owner.post(f"/api/agents/{agent['id']}/versions/1/{action}", json={})
                assert res.status_code == 200, res.text
        return agent

    def test_numbers_are_managed_and_unique(self):
        owner, other = _TenantClient(self.client), _TenantClient(self.client)
        agent = self._agent(owner, promote=False)
        number = _number()
        res = owner.post(f"/api/agents/{agent['id']}/numbers", json={"phone_number": f"{number[:3]} {number[3:8]} {number[8:]}"})
        self.assertEqual(res.status_code, 201, res.text)
        self.assertEqual(res.json()["phone_number"], number)
        self.assertEqual(owner.post(f"/api/agents/{agent['id']}/numbers", json={"phone_number": "12"}).status_code, 422)
        # Nobody else can take the number, and the reply doesn't say whose it is.
        theirs = self._agent(other, promote=False)
        clash = other.post(f"/api/agents/{theirs['id']}/numbers", json={"phone_number": number})
        self.assertEqual(clash.status_code, 409)
        self.assertNotIn(owner.tenant_id, clash.text)
        self.assertEqual(other.get(f"/api/agents/{agent['id']}/numbers").status_code, 404)
        listed = owner.get(f"/api/agents/{agent['id']}/numbers").json()
        self.assertEqual([n["phone_number"] for n in listed], [number])
        self.assertEqual(owner.delete(f"/api/agents/{agent['id']}/numbers/{listed[0]['id']}").status_code, 204)
        self.assertEqual(owner.get(f"/api/agents/{agent['id']}/numbers").json(), [])

    def test_inbound_call_routes_to_the_agents_production_version(self):
        owner = _TenantClient(self.client)
        agent = self._agent(owner)
        number = _number()
        owner.post(f"/api/agents/{agent['id']}/numbers", json={"phone_number": number})
        # SIP reports the dialed number without "+" or with spaces.
        routing = resolve_for_call(number.lstrip("+"))
        self.assertIsNotNone(routing)
        self.assertEqual((routing["tenant_id"], routing["agent_id"], routing["version"]), (owner.tenant_id, agent["id"], 1))
        o = routing["overrides"]
        self.assertEqual((o["gemini_live_voice"], o["gemini_live_language"], o["first_line"], o["lang_preset"]),
                         ("Aoede", "te", "నమస్కారం", "multilingual"))
        self.assertIsNone(resolve_for_call(_number()))
        # Outbound dispatches name the agent directly.
        self.assertEqual(resolve_for_call(None, agent["id"])["agent_id"], agent["id"])

    def test_agents_that_cannot_take_calls_fall_back(self):
        owner = _TenantClient(self.client)
        draft_only = self._agent(owner, promote=False)
        number = _number()
        owner.post(f"/api/agents/{draft_only['id']}/numbers", json={"phone_number": number})
        self.assertIsNone(resolve_for_call(number))
        live = self._agent(owner)
        other_number = _number()
        owner.post(f"/api/agents/{live['id']}/numbers", json={"phone_number": other_number})
        self.assertEqual(owner.post(f"/api/agents/{live['id']}/disable", json={}).status_code, 200)
        self.assertIsNone(resolve_for_call(other_number))

    def test_deleting_an_agent_frees_its_numbers(self):
        owner = _TenantClient(self.client)
        agent = self._agent(owner, promote=False)
        number = _number()
        owner.post(f"/api/agents/{agent['id']}/numbers", json={"phone_number": number})
        self.assertEqual(owner.delete(f"/api/agents/{agent['id']}").status_code, 200)
        again = self._agent(owner, promote=False)
        self.assertEqual(owner.post(f"/api/agents/{again['id']}/numbers", json={"phone_number": number}).status_code, 201)

    def test_runtime_overrides_mapping(self):
        o = runtime_overrides({"instructions": "Line one\nLine two", "languages": {"default": "en", "supported": ["en"]},
                               "limits": {"max_call_seconds": 600}, "llm": {"temperature": 0.3}})
        self.assertEqual((o["first_line"], o["lang_preset"], o["max_turns"], o["gemini_live_temperature"]), ("Line one", "en", 30, 0.3))


if __name__ == "__main__":
    unittest.main()
