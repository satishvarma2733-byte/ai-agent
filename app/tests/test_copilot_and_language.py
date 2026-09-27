"""Agent Copilot (plain-language edits previewed, then applied to the draft) and language checks in agent tests."""
import json
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.core.database import Base, engine
from app.main import app
from app.services import agent_copilot, agent_testing, call_language
from app.tests.test_agent_studio import AGENT, CONFIG, FakeModel
from app.tests.test_consolidation import _TenantClient
from app.tests.test_regression_matrix import _Member


class FakeCopilot:
    def __init__(self, answer):
        self.answer = answer
        self.prompts = []

    def __call__(self, client_kwargs, model, text):
        self.prompts.append(text)
        return self.answer if isinstance(self.answer, str) else json.dumps(self.answer)


class CopilotTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        Base.metadata.create_all(bind=engine)
        cls.client = TestClient(app)

    def setUp(self):
        p = patch("app.core.runtime_config.load_runtime_config", return_value=dict(CONFIG))
        p.start()
        self.addCleanup(p.stop)
        self.owner = _TenantClient(self.client)
        self.agent = self.owner.post("/api/agents", json=AGENT).json()
        self.base = f"/api/agents/{self.agent['id']}"

    def propose(self, answer, request="Speak Hindi by default and greet in Hindi"):
        fake = FakeCopilot(answer)
        with patch.object(agent_copilot, "generate_json", fake):
            return self.owner.post(f"{self.base}/copilot", json={"request": request}), fake


class TestCopilot(CopilotTestCase):
    def test_preview_then_apply(self):
        answer = {"summary": "Hindi is now the default, with a Hindi greeting.",
                  "patch": {"languages": {"default": "hi", "supported": ["hi", "en"]}, "greetings": {"hi": "नमस्ते! मैं कैसे मदद करूँ?"}}}
        res, fake = self.propose(answer)
        self.assertEqual(res.status_code, 200, res.text)
        body = res.json()
        self.assertEqual(body["summary"], answer["summary"])
        paths = {c["path"] for c in body["changes"]}
        self.assertIn("languages.default", paths)
        self.assertIn("greetings.hi", paths)
        self.assertIn("Sunrise Dental", fake.prompts[0])  # the model sees the current brief
        # nothing saved yet
        self.assertEqual(self.owner.get(self.base).json()["language"], "en")
        applied = self.owner.post(f"{self.base}/copilot/apply", json={"request": "Speak Hindi by default", "patch": body["patch"]})
        self.assertEqual(applied.status_code, 200, applied.text)
        self.assertEqual(self.owner.get(self.base).json()["language"], "hi")
        change = self.owner.get(f"{self.base}/changes").json()[0]
        self.assertEqual((change["source"], change["reason"]), ("copilot", "Copilot: Speak Hindi by default"))
        again = self.owner.post(f"{self.base}/copilot/apply", json={"request": "Speak Hindi by default", "patch": body["patch"]})
        self.assertEqual(again.status_code, 409)

    def test_restricted_fields_are_dropped(self):
        answer = {"summary": "x", "patch": {"llm": {"model": "some-other-model", "temperature": 0.3},
                                           "tools": [{"key": "refund", "enabled": True}], "workflow_id": "w1"}}
        body = self.propose(answer)[0].json()
        self.assertEqual(body["patch"], {"llm": {"temperature": 0.3}})
        self.assertEqual(sorted(body["ignored"]), ["llm.model", "tools", "workflow_id"])
        # apply re-checks on the server, whatever the browser sends
        applied = self.owner.post(f"{self.base}/copilot/apply", json={"request": "cooler", "patch": answer["patch"]})
        self.assertEqual(applied.status_code, 200, applied.text)
        version = applied.json()["version"]
        self.assertEqual(version["config"]["llm"]["temperature"], 0.3)
        self.assertNotEqual(version["config"]["llm"]["model"], "some-other-model")
        self.assertEqual(version["config"]["tools"], [])

    def test_invalid_or_unusable_answers(self):
        self.assertEqual(self.propose({"summary": "x", "patch": {"limits": {"max_call_seconds": 5}}})[0].status_code, 422)
        self.assertEqual(self.propose("not json")[0].status_code, 502)
        empty = self.propose({"summary": "Nothing to change.", "patch": {}})[0].json()
        self.assertEqual(empty["changes"], [])

    def test_permissions_and_isolation(self):
        agent_member = _Member(self.client, self.owner, "Agent")
        self.assertEqual(agent_member.post(f"{self.base}/copilot", json={"request": "be nicer"}).status_code, 403)
        other = _TenantClient(self.client)
        self.assertEqual(other.post(f"{self.base}/copilot", json={"request": "be nicer"}).status_code, 404)
        self.assertEqual(other.post(f"{self.base}/copilot/apply", json={"request": "be nicer", "patch": {}}).status_code, 404)


class TestLanguageChecks(CopilotTestCase):
    def setUp(self):
        super().setUp()
        self.model = FakeModel({"hours": "మేము ఉదయం 9 నుండి సాయంత్రం 6 వరకు తెరిచి ఉంటాము.", "price": "A cleaning costs 1,500 rupees."})
        p = patch.object(agent_testing, "generate", self.model)
        p.start()
        self.addCleanup(p.stop)

    def test_share(self):
        self.assertEqual(call_language.share("Hello there", "en"), 1.0)
        self.assertGreater(call_language.share("మీ appointment రేపు ఉంది", "te"), agent_testing.DEFAULT_LANGUAGE_SHARE)
        self.assertEqual(call_language.share("", "te"), 0.0)

    def test_run_checks_the_reply_language(self):
        ok = self.owner.post(f"{self.base}/tests", json={"name": "Telugu hours", "caller_turns": ["hours?"], "expected_language": "te"})
        self.assertEqual(ok.status_code, 201, ok.text)
        self.assertEqual(ok.json()["expected_language"], "te")
        self.owner.post(f"{self.base}/tests", json={"name": "Telugu price", "caller_turns": ["hours?", "price?"], "expected_language": "te"})
        run = self.owner.post(f"{self.base}/versions/1/test/run").json()
        results = {r["name"]: r for r in run["results"]}
        self.assertTrue(results["Telugu hours"]["passed"])
        self.assertFalse(results["Telugu price"]["passed"])
        self.assertEqual(results["Telugu price"]["wrong_language_replies"], [2])
        self.assertEqual((run["passed"], run["total"]), (1, 2))

    def test_validation(self):
        bad = self.owner.post(f"{self.base}/tests", json={"name": "x", "caller_turns": ["hi"], "expected_language": "fr"})
        self.assertEqual(bad.status_code, 422)
        nothing = self.owner.post(f"{self.base}/tests", json={"name": "x", "caller_turns": ["hi"]})
        self.assertEqual(nothing.status_code, 422)
