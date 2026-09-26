"""Agent Studio: text tests, regression test cases gating evaluation, and browser voice tests."""
import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import jwt
from fastapi.testclient import TestClient

from app.core.database import Base, engine
from app.main import app
from app.services import agent_testing
from app.services.agent_runtime import resolve_for_call
from app.tests.test_consolidation import _TenantClient
from app.tests.test_regression_matrix import _Member

AGENT = {"name": "Aria", "voice": "Aoede", "model": "gemini-2.0-flash-live-001", "language": "en",
         "instructions": "You are the front desk of Sunrise Dental. Clinic hours are 9am to 6pm."}
CONFIG = {"google_api_key": "test-key", "livekit_url": "wss://lk.example.com", "livekit_api_key": "APIkey",
          "livekit_api_secret": "secret-for-tests-long-enough-32b"}


class FakeModel:
    """Stands in for Gemini: answers from a script and remembers what it was asked."""
    def __init__(self, answers=None):
        self.calls = []
        self.answers = answers or {}

    def __call__(self, client_kwargs, model, system, turns):
        self.calls.append({"kwargs": client_kwargs, "model": model, "system": system, "turns": turns})
        last = turns[-1]["text"].lower()
        return next((a for q, a in self.answers.items() if q in last), "Happy to help!")


class StudioTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        Base.metadata.create_all(bind=engine)
        cls.client = TestClient(app)

    def setUp(self):
        self.model = FakeModel({"hours": "We're open 9am to 6pm, Monday to Saturday.", "price": "A cleaning costs 1,500 rupees."})
        for p in (patch.object(agent_testing, "generate", self.model),
                  patch("app.core.runtime_config.load_runtime_config", return_value=dict(CONFIG))):
            p.start()
            self.addCleanup(p.stop)
        self.owner = _TenantClient(self.client)
        self.agent = self.owner.post("/api/agents", json=AGENT).json()
        self.base = f"/api/agents/{self.agent['id']}"

    def add_case(self, **overrides):
        body = {"name": "Hours", "caller_turns": ["What are your hours?"], "must_include": ["9am"], "must_not_include": ["24 hours"], **overrides}
        res = self.owner.post(f"{self.base}/tests", json=body)
        self.assertEqual(res.status_code, 201, res.text)
        return res.json()


class TestTextChat(StudioTestCase):
    def test_reply_uses_the_versions_brief(self):
        res = self.owner.post(f"{self.base}/versions/1/test/chat", json={"turns": [{"role": "caller", "text": "What are your hours?"}]})
        self.assertEqual(res.status_code, 200, res.text)
        self.assertEqual(res.json()["reply"], "We're open 9am to 6pm, Monday to Saturday.")
        call = self.model.calls[-1]
        self.assertIn("Sunrise Dental", call["system"])
        self.assertEqual(call["kwargs"], {"api_key": "test-key"})
        self.assertEqual(call["model"], agent_testing.DEFAULT_TEXT_MODEL)

    def test_validation_roles_and_isolation(self):
        bad = self.owner.post(f"{self.base}/versions/1/test/chat", json={"turns": [{"role": "agent", "text": "Hello"}]})
        self.assertEqual(bad.status_code, 422)
        self.assertEqual(self.owner.post(f"{self.base}/versions/9/test/chat", json={"turns": [{"role": "caller", "text": "hi"}]}).status_code, 404)
        agent_member = _Member(self.client, self.owner, "Agent")
        self.assertEqual(agent_member.post(f"{self.base}/versions/1/test/chat", json={"turns": [{"role": "caller", "text": "hi"}]}).status_code, 403)
        other = _TenantClient(self.client)
        self.assertEqual(other.post(f"{self.base}/versions/1/test/chat", json={"turns": [{"role": "caller", "text": "hi"}]}).status_code, 404)
        with patch("app.core.runtime_config.load_runtime_config", return_value={}):
            self.assertEqual(self.owner.post(f"{self.base}/versions/1/test/chat", json={"turns": [{"role": "caller", "text": "hi"}]}).status_code, 503)

    def test_model_failure_is_reported(self):
        with patch.object(agent_testing, "generate", side_effect=RuntimeError("quota")):
            res = self.owner.post(f"{self.base}/versions/1/test/chat", json={"turns": [{"role": "caller", "text": "hi"}]})
        self.assertEqual(res.status_code, 502)
        self.assertIn("quota", res.json()["detail"])


class TestRegressionTests(StudioTestCase):
    def test_cases_are_validated(self):
        for body in ({"name": "x", "caller_turns": [], "must_include": ["a"]},
                     {"name": "x", "caller_turns": ["hi"]},
                     {"name": "x", "caller_turns": ["hi"] * 11, "must_include": ["a"]}):
            self.assertEqual(self.owner.post(f"{self.base}/tests", json=body).status_code, 422, body)
        case = self.add_case()
        self.assertEqual([c["id"] for c in self.owner.get(f"{self.base}/tests").json()], [case["id"]])
        self.assertEqual(self.owner.delete(f"{self.base}/tests/{case['id']}").status_code, 204)
        self.assertEqual(self.owner.delete(f"{self.base}/tests/{case['id']}").status_code, 404)

    def test_run_reports_each_case(self):
        self.add_case()
        self.add_case(name="No discounts", caller_turns=["What's the price of cleaning?"], must_include=["discount"], must_not_include=[])
        run = self.owner.post(f"{self.base}/versions/1/test/run").json()
        self.assertEqual((run["passed"], run["total"]), (1, 2))
        failed = next(r for r in run["results"] if not r["passed"])
        self.assertEqual((failed["name"], failed["missing"]), ("No discounts", ["discount"]))
        self.assertEqual(failed["transcript"][-1], {"role": "agent", "text": "A cleaning costs 1,500 rupees."})
        self.assertEqual(len(self.owner.get(f"{self.base}/versions/1/test/runs").json()), 1)

    def test_evaluation_waits_for_a_passing_run(self):
        self.owner.post(f"{self.base}/versions/1/submit", json={})
        self.add_case()
        blocked = self.owner.post(f"{self.base}/versions/1/evaluate", json={})
        self.assertEqual(blocked.status_code, 409)
        self.assertIn("Run this version's 1 test case", blocked.json()["detail"])
        self.add_case(name="Price", caller_turns=["price?"], must_include=["free"], must_not_include=[])
        self.owner.post(f"{self.base}/versions/1/test/run")
        self.assertIn("passed 1 of 2", self.owner.post(f"{self.base}/versions/1/evaluate", json={}).json()["detail"])
        price = next(c for c in self.owner.get(f"{self.base}/tests").json() if c["name"] == "Price")
        self.owner.delete(f"{self.base}/tests/{price['id']}")
        self.owner.post(f"{self.base}/versions/1/test/run")
        self.assertEqual(self.owner.post(f"{self.base}/versions/1/evaluate", json={}).status_code, 200)

    def test_agents_without_tests_are_not_gated(self):
        self.owner.post(f"{self.base}/versions/1/submit", json={})
        self.assertEqual(self.owner.post(f"{self.base}/versions/1/evaluate", json={}).status_code, 200)


class FakeLiveKitAPI:
    dispatches = []

    def __init__(self, url, api_key, api_secret):
        class Dispatch:
            async def create_dispatch(self, req):
                FakeLiveKitAPI.dispatches.append(req)
                return SimpleNamespace(id="d1")

        self.agent_dispatch = Dispatch()

    async def aclose(self):
        pass


class TestVoiceTest(StudioTestCase):
    def test_sandbox_room_with_a_microphone_pass(self):
        FakeLiveKitAPI.dispatches = []
        settings = {"url": "wss://lk.example.com", "api_key": "APIkey", "api_secret": CONFIG["livekit_api_secret"], "sip_trunk_id": ""}
        with patch("livekit.api.LiveKitAPI", FakeLiveKitAPI), patch("outbound_calls.get_livekit_settings", return_value=settings):
            res = self.owner.post(f"{self.base}/versions/1/test/voice")
        self.assertEqual(res.status_code, 200, res.text)
        body = res.json()
        [dispatch] = FakeLiveKitAPI.dispatches
        meta = json.loads(dispatch.metadata)
        self.assertEqual((dispatch.room, meta["agent_id"], meta["test_version"], meta["tenant_id"]),
                         (body["room"], self.agent["id"], 1, self.owner.tenant_id))
        self.assertNotIn("phone_number", meta)  # nothing is dialled
        video = jwt.decode(body["token"], CONFIG["livekit_api_secret"], algorithms=["HS256"], options={"verify_aud": False})["video"]
        self.assertEqual((video["room"], video["canPublish"], video["canSubscribe"], video["canPublishData"]), (body["room"], True, True, False))
        with patch("outbound_calls.get_livekit_settings", return_value={"url": "", "api_key": "", "api_secret": ""}):
            self.assertEqual(self.owner.post(f"{self.base}/versions/1/test/voice").status_code, 503)

    def test_worker_runs_the_requested_version(self):
        routing = resolve_for_call(None, self.agent["id"], 1)
        self.assertEqual((routing["version"], routing["tenant_id"]), (1, self.owner.tenant_id))
        self.assertIn("Sunrise Dental", routing["overrides"]["agent_instructions"])
        self.assertIsNone(resolve_for_call(None, self.agent["id"], 7))
        # Without a test version, a draft-only agent still isn't routed.
        self.assertIsNone(resolve_for_call(None, self.agent["id"]))


if __name__ == "__main__":
    unittest.main()
