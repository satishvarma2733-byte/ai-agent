"""Website chat widget and the public chat API: keys and origins, conversations, lead capture, voice, admin."""
import json
import unittest
from unittest.mock import patch

import jwt
from fastapi.testclient import TestClient

from app.core import ratelimit
from app.core.database import Base, SessionLocal, engine
from app.core.settings import settings
from app.main import app
from app.models.agent import Agent, AgentVersion
from app.models.lead import Lead, LeadActivity
from app.services import agent_testing, public_chat
from app.tests.test_agent_studio import AGENT, CONFIG, FakeLiveKitAPI, FakeModel
from app.tests.test_consolidation import _TenantClient
from app.tests.test_regression_matrix import _Member

SITE = "https://shop.example.com"
LK_SETTINGS = {"url": "wss://lk.example.com", "api_key": "APIkey", "api_secret": CONFIG["livekit_api_secret"], "sip_trunk_id": ""}


def _go_live(agent_id: str) -> None:
    db = SessionLocal()
    try:
        agent = db.get(Agent, agent_id)
        agent.production_version_id = db.query(AgentVersion).filter(AgentVersion.agent_id == agent_id).first().id
        db.commit()
    finally:
        db.close()


class WidgetTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        Base.metadata.create_all(bind=engine)
        cls.client = TestClient(app)

    def setUp(self):
        self.model = FakeModel({"hours": "We're open 9am to 6pm.", "price": "A cleaning costs 1,500 rupees."})
        for p in (patch.object(agent_testing, "generate", self.model),
                  patch("app.core.runtime_config.load_runtime_config", return_value=dict(CONFIG))):
            p.start()
            self.addCleanup(p.stop)
        self.owner = _TenantClient(self.client)
        self.agent = self.owner.post("/api/agents", json=AGENT).json()
        _go_live(self.agent["id"])
        self.widget = self.make_widget()

    def make_widget(self, **overrides):
        body = {"name": "Main site", "agent_id": self.agent["id"], "allowed_origins": [SITE + "/"], **overrides}
        res = self.owner.post("/api/widgets", json=body)
        self.assertEqual(res.status_code, 201, res.text)
        return res.json()

    def pub(self, method, path, key=None, origin=SITE, **kw):
        headers = {"X-Widget-Key": key or self.widget["public_key"]}
        if origin:
            headers["Origin"] = origin
        headers.update(kw.pop("headers", {}))
        return getattr(self.client, method)(path, headers=headers, **kw)

    def chat(self, message, session=None, **kw):
        return self.pub("post", "/api/public/chat", json={"message": message, "session": session}, **kw)


class TestWidgetAdmin(WidgetTestCase):
    def test_create_normalizes_origins_and_gives_embed_code(self):
        self.assertEqual(self.widget["allowed_origins"], [SITE])
        self.assertTrue(self.widget["public_key"].startswith("wk_"))
        self.assertIn(f'data-key="{self.widget["public_key"]}"', self.widget["embed_code"])
        self.assertIn("/widget.js", self.widget["embed_code"])
        self.assertTrue(self.widget["agent_live"])

    def test_validation(self):
        for origins in (["http://shop.example.com"], ["https://shop.example.com/path"], ["not a url"], []):
            res = self.owner.post("/api/widgets", json={"name": "x", "agent_id": self.agent["id"], "allowed_origins": origins})
            self.assertEqual(res.status_code, 422, origins)
        local = self.make_widget(allowed_origins=["http://localhost:3000"])
        self.assertEqual(local["allowed_origins"], ["http://localhost:3000"])
        bad_color = self.owner.post("/api/widgets", json={"name": "x", "agent_id": self.agent["id"], "allowed_origins": [SITE], "color": "red"})
        self.assertEqual(bad_color.status_code, 422)

    def test_admin_only_and_isolated(self):
        manager = _Member(self.client, self.owner, "Manager")
        self.assertEqual(manager.get("/api/widgets").status_code, 403)
        self.assertEqual(manager.post("/api/api-keys", json={"name": "x"}).status_code, 403)
        other = _TenantClient(self.client)
        self.assertEqual(other.get("/api/widgets").json(), [])
        self.assertEqual(other.patch(f"/api/widgets/{self.widget['id']}", json={"enabled": False}).status_code, 404)
        foreign = other.post("/api/widgets", json={"name": "x", "agent_id": self.agent["id"], "allowed_origins": [SITE]})
        self.assertEqual(foreign.status_code, 404)

    def test_rotate_key_cuts_the_old_embed(self):
        old = self.widget["public_key"]
        new = self.owner.post(f"/api/widgets/{self.widget['id']}/rotate-key").json()["public_key"]
        self.assertNotEqual(old, new)
        self.assertEqual(self.pub("get", "/api/public/widget", key=old).status_code, 404)
        self.assertEqual(self.pub("get", "/api/public/widget", key=new).status_code, 200)

    def test_script_is_served_cross_origin(self):
        res = self.client.get("/widget.js")
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.headers["content-type"].startswith("application/javascript"))
        self.assertEqual(res.headers["cross-origin-resource-policy"], "cross-origin")
        self.assertIn("X-Widget-Key", res.text)


class TestPublicWidget(WidgetTestCase):
    def test_config_only_for_listed_origins(self):
        ok = self.pub("get", "/api/public/widget")
        self.assertEqual(ok.status_code, 200, ok.text)
        self.assertEqual(ok.headers["access-control-allow-origin"], SITE)
        self.assertEqual(ok.json()["agent_name"], "Aria")
        for origin in ("https://evil.example.com", None):
            res = self.pub("get", "/api/public/widget", origin=origin)
            self.assertEqual(res.status_code, 403, origin)
            self.assertNotIn("access-control-allow-origin", res.headers)

    def test_preflight_and_dashboard_cors_unchanged(self):
        res = self.client.options("/api/public/chat", headers={"Origin": SITE, "Access-Control-Request-Method": "POST",
                                                                "Access-Control-Request-Headers": "content-type,x-widget-key"})
        self.assertEqual(res.status_code, 204)
        self.assertIn("X-Widget-Key", res.headers["access-control-allow-headers"])
        blocked = self.client.options("/api/auth/login", headers={"Origin": SITE, "Access-Control-Request-Method": "POST"})
        self.assertNotEqual(blocked.headers.get("access-control-allow-origin"), SITE)
        if settings.cors_origin_list:
            allowed = settings.cors_origin_list[0]
            res = self.client.options("/api/auth/login", headers={"Origin": allowed, "Access-Control-Request-Method": "POST"})
            self.assertEqual(res.headers.get("access-control-allow-origin"), allowed)

    def test_conversation_keeps_context(self):
        first = self.chat("What are your hours?")
        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(first.headers["access-control-allow-origin"], SITE)
        body = first.json()
        self.assertEqual(body["reply"], "We're open 9am to 6pm.")
        self.assertFalse(body["ask_for_contact"])
        session = body["session"]
        second = self.chat("And the price?", session).json()
        self.assertIsNone(second["session"])
        self.assertTrue(second["ask_for_contact"])
        turns = self.model.calls[-1]["turns"]
        self.assertEqual([t["role"] for t in turns], ["caller", "agent", "caller"])
        self.assertIn("Sunrise Dental", self.model.calls[-1]["system"])
        convo = self.owner.get("/api/chat-sessions").json()[0]
        self.assertEqual((convo["messages"], convo["source"], convo["origin"]), (2, "Main site", SITE))

    def test_sessions_belong_to_their_widget(self):
        session = self.chat("hello").json()["session"]
        other = self.make_widget(name="Second")
        self.assertEqual(self.chat("hi", session, key=other["public_key"]).status_code, 404)
        self.assertEqual(self.chat("hi", "made-up-token").status_code, 404)

    def test_errors_and_limits(self):
        self.assertEqual(self.chat("x" * (public_chat.MAX_MESSAGE_CHARS + 1)).status_code, 422)
        self.assertEqual(self.chat("   ").status_code, 422)
        self.owner.patch(f"/api/widgets/{self.widget['id']}", json={"enabled": False})
        self.assertEqual(self.chat("hi").status_code, 404)
        self.owner.patch(f"/api/widgets/{self.widget['id']}", json={"enabled": True})
        with patch.object(public_chat, "PER_IP_PER_MINUTE", 2):
            codes = [self.chat("hi", headers={"X-Forwarded-For": "203.0.113.9"}).status_code for _ in range(3)]
        self.assertEqual(codes, [200, 200, 429])
        ratelimit.reset(f"pub-chat:{self.widget['id']}:203.0.113.9")

    def test_agent_must_be_live(self):
        self.owner.post(f"/api/agents/{self.agent['id']}/disable", json={})
        db = SessionLocal()
        try:
            db.get(Agent, self.agent["id"]).production_version_id = None
            db.commit()
        finally:
            db.close()
        res = self.chat("hi")
        self.assertEqual(res.status_code, 503)
        self.assertEqual(res.headers["access-control-allow-origin"], SITE)  # the widget can show why

    def test_model_failure_is_a_friendly_error(self):
        with patch.object(agent_testing, "generate", side_effect=RuntimeError("quota")):
            res = self.chat("hi")
        self.assertEqual(res.status_code, 503)
        self.assertNotIn("quota", res.text)


class TestLeadCapture(WidgetTestCase):
    def test_contact_becomes_a_lead_with_the_transcript(self):
        session = self.chat("What are your hours?").json()["session"]
        res = self.pub("post", "/api/public/chat/contact", json={"session": session, "name": "Asha", "phone": "+91 98765 43210", "email": ""})
        self.assertEqual(res.status_code, 200, res.text)
        self.assertTrue(res.json()["created"])
        db = SessionLocal()
        try:
            lead = db.get(Lead, res.json()["lead_id"])
            self.assertEqual((lead.tenant_id, lead.name), (self.owner.tenant_id, "Asha"))
            activity = db.query(LeadActivity).filter(LeadActivity.lead_id == lead.id, LeadActivity.activity_type == "chat").one()
            self.assertIn("Visitor: What are your hours?", activity.description)
            self.assertIn("Assistant: We're open 9am to 6pm.", activity.description)
        finally:
            db.close()
        self.assertFalse(self.chat("thanks", session).json()["ask_for_contact"])
        self.assertEqual(self.owner.get("/api/chat-sessions").json()[0]["lead_name"], "Asha")
        again = self.pub("post", "/api/public/chat/contact", json={"session": self.chat("hi").json()["session"], "name": "A", "phone": "+919876543210"})
        self.assertEqual((again.json()["lead_id"], again.json()["created"]), (res.json()["lead_id"], False))

    def test_bad_contact_details(self):
        session = self.chat("hi").json()["session"]
        res = self.pub("post", "/api/public/chat/contact", json={"session": session, "name": "Asha", "phone": "call me"})
        self.assertEqual(res.status_code, 422)
        self.assertEqual(res.headers["access-control-allow-origin"], SITE)


class TestApiKeys(WidgetTestCase):
    def api(self, key, body, origin=None):
        headers = {"Authorization": f"Bearer {key}"}
        if origin:
            headers["Origin"] = origin
        return self.client.post("/api/public/chat", headers=headers, json=body)

    def test_server_to_server_chat(self):
        created = self.owner.post("/api/api-keys", json={"name": "CRM sync"}).json()
        key = created["key"]
        self.assertTrue(key.startswith("avn_sk_"))
        self.assertNotIn("key", self.owner.get("/api/api-keys").json()[0])
        self.assertEqual(self.api(key, {"message": "hi"}).status_code, 422)  # which agent?
        res = self.api(key, {"message": "What are your hours?", "agent_id": self.agent["id"]}, origin=SITE)
        self.assertEqual(res.status_code, 200, res.text)
        self.assertNotIn("access-control-allow-origin", res.headers)  # secret keys are not for browsers
        session = res.json()["session"]
        self.assertEqual(self.api(key, {"message": "price?", "session": session}).status_code, 200)
        self.assertIsNotNone(self.owner.get("/api/api-keys").json()[0]["last_used_at"])
        other = _TenantClient(self.client)
        foreign = other.post("/api/agents", json=AGENT).json()
        self.assertEqual(self.api(key, {"message": "hi", "agent_id": foreign["id"]}).status_code, 404)
        self.owner.delete(f"/api/api-keys/{created['id']}")
        self.assertEqual(self.api(key, {"message": "hi", "session": session}).status_code, 401)
        self.assertEqual(self.api("avn_sk_nope", {"message": "hi"}).status_code, 401)

    def test_no_credentials(self):
        self.assertEqual(self.client.post("/api/public/chat", json={"message": "hi"}).status_code, 401)


class TestVoice(WidgetTestCase):
    def test_voice_needs_to_be_on(self):
        with patch("livekit.api.LiveKitAPI", FakeLiveKitAPI), patch("outbound_calls.get_livekit_settings", return_value=LK_SETTINGS):
            self.assertEqual(self.pub("post", "/api/public/voice", json={}).status_code, 403)

    def test_browser_call_with_the_production_agent(self):
        FakeLiveKitAPI.dispatches = []
        widget = self.make_widget(voice_enabled=True)
        with patch("livekit.api.LiveKitAPI", FakeLiveKitAPI), patch("outbound_calls.get_livekit_settings", return_value=LK_SETTINGS):
            res = self.pub("post", "/api/public/voice", key=widget["public_key"], json={})
        self.assertEqual(res.status_code, 200, res.text)
        body = res.json()
        [dispatch] = FakeLiveKitAPI.dispatches
        meta = json.loads(dispatch.metadata)
        self.assertEqual((meta["channel"], meta["agent_id"], meta["tenant_id"]), ("web", self.agent["id"], self.owner.tenant_id))
        self.assertNotIn("test_version", meta)
        video = jwt.decode(body["token"], CONFIG["livekit_api_secret"], algorithms=["HS256"], options={"verify_aud": False})["video"]
        self.assertEqual((video["room"], video["canPublish"], video["canPublishData"]), (body["room"], True, False))
        with patch("outbound_calls.get_livekit_settings", return_value={"url": "", "api_key": "", "api_secret": ""}):
            self.assertEqual(self.pub("post", "/api/public/voice", key=widget["public_key"], json={}).status_code, 503)


class TestConversationsList(WidgetTestCase):
    def test_managers_can_read_agents_cannot(self):
        self.chat("hello")
        self.assertEqual(len(_Member(self.client, self.owner, "Manager").get("/api/chat-sessions").json()), 1)
        self.assertEqual(_Member(self.client, self.owner, "Agent").get("/api/chat-sessions").status_code, 403)
        self.assertEqual(_TenantClient(self.client).get("/api/chat-sessions").json(), [])
