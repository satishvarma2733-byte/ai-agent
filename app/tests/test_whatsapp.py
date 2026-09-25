"""WhatsApp through Meta's Cloud API and Twilio: connecting, sending, webhooks and the workflow step.
The app's code runs for real against in-memory fakes of both providers."""
import asyncio
import base64
import hashlib
import hmac
import json
import os
import unittest
import uuid
from unittest.mock import patch
from urllib.parse import parse_qs

import httpx
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

import config_crypto
from app.core.database import Base, SessionLocal, engine
from app.main import app
from app.models.lead import LeadActivity
from app.models.notification import Notification
from app.models.whatsapp import WhatsAppAccount
from app.services import whatsapp
from app.services.workflow_engine import workflow_engine
from app.tests.test_consolidation import _TenantClient
from app.tests.test_regression_matrix import _Member

META = {"provider": "meta", "phone_number_id": "1055", "access_token": "meta-token", "app_secret": "meta-app-secret"}
TWILIO = {"provider": "twilio", "account_sid": "AC123", "auth_token": "twilio-token", "from_number": "+1 415 555 0100"}


def _phone() -> str:
    return "+9197" + str(uuid.uuid4().int)[:8]


class FakeProviders:
    def __init__(self):
        self.sent: list[httpx.Request] = []
        self.meta_error: dict | None = None

    def __call__(self, request: httpx.Request) -> httpx.Response:
        url = request.url
        if url.host == "graph.facebook.com":
            if request.headers.get("authorization") != "Bearer meta-token":
                return httpx.Response(401, json={"error": {"message": "Invalid OAuth access token.", "code": 190}})
            if request.method == "GET":
                return httpx.Response(200, json={"display_phone_number": "+91 40 1234 5678", "verified_name": "Co"})
            self.sent.append(request)
            if self.meta_error:
                return httpx.Response(400, json={"error": self.meta_error})
            return httpx.Response(200, json={"messages": [{"id": f"wamid.{uuid.uuid4().hex}"}]})
        if url.host == "api.twilio.com":
            expected = "Basic " + base64.b64encode(b"AC123:twilio-token").decode()
            if request.headers.get("authorization") != expected:
                return httpx.Response(401, json={"code": 20003, "message": "Authenticate"})
            if request.method == "GET":
                return httpx.Response(200, json={"status": "active"})
            self.sent.append(request)
            return httpx.Response(201, json={"sid": f"SM{uuid.uuid4().hex}"})
        return httpx.Response(404)


class WhatsAppTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        Base.metadata.create_all(bind=engine)
        cls.client = TestClient(app)

    def setUp(self):
        self.fake = FakeProviders()
        for p in (patch.object(whatsapp, "http", lambda: httpx.Client(transport=httpx.MockTransport(self.fake))),
                  patch.dict(os.environ, {"SECRETS_ENCRYPTION_KEY": Fernet.generate_key().decode()})):
            p.start()
            self.addCleanup(p.stop)

    def lead(self, owner, **fields) -> dict:
        res = owner.post("/api/crm/leads", json={"name": "Asha Rao", "phone": _phone(), **fields})
        self.assertEqual(res.status_code, 201, res.text)
        return res.json()


class TestConnecting(WhatsAppTestCase):
    def test_admin_connects_meta_and_credentials_are_encrypted(self):
        owner = _TenantClient(self.client)
        agent = _Member(self.client, owner, "Agent")
        self.assertEqual(agent.put("/api/integrations/whatsapp", json=META).status_code, 403)
        bad = owner.put("/api/integrations/whatsapp", json=dict(META, access_token="wrong"))
        self.assertEqual(bad.status_code, 400)
        self.assertIn("Invalid OAuth access token", bad.json()["detail"])
        self.assertIn("app_secret", owner.put("/api/integrations/whatsapp", json=dict(META, app_secret="")).json()["detail"])

        res = owner.put("/api/integrations/whatsapp", json=META)
        self.assertEqual(res.status_code, 200, res.text)
        body = res.json()
        self.assertEqual((body["provider"], body["sender"]), ("meta", "+91 40 1234 5678"))
        self.assertIn("/api/whatsapp/webhook/meta/", body["webhook_url"])
        self.assertTrue(body["verify_token"])
        self.assertNotIn("meta-token", json.dumps(body))
        # Teammates see the sender but not the webhook secrets.
        seen = agent.get("/api/integrations/whatsapp").json()
        self.assertEqual((seen["connected"], seen["webhook_url"], seen["verify_token"]), (True, None, None))
        db = SessionLocal()
        try:
            stored = db.query(WhatsAppAccount).filter(WhatsAppAccount.tenant_id == owner.tenant_id).one()
            self.assertTrue(config_crypto.is_encrypted(stored.credentials))
            self.assertNotIn("meta-token", stored.credentials)
        finally:
            db.close()
        self.assertEqual(owner.delete("/api/integrations/whatsapp").status_code, 204)
        self.assertFalse(owner.get("/api/integrations/whatsapp").json()["connected"])

    def test_nothing_is_sent_without_a_connection(self):
        owner = _TenantClient(self.client)
        res = owner.post("/api/crm/whatsapp", json={"phone": "+919000000001", "text": "hi"})
        self.assertEqual(res.status_code, 501)
        self.assertEqual(self.fake.sent, [])


class TestMeta(WhatsAppTestCase):
    def setUp(self):
        super().setUp()
        self.owner = _TenantClient(self.client)
        self.account = self.owner.put("/api/integrations/whatsapp", json=META).json()
        self.token = self.account["webhook_url"].rsplit("/", 1)[1]

    def hook(self, payload: dict, secret: str = "meta-app-secret", token: str | None = None):
        raw = json.dumps(payload).encode()
        sig = "sha256=" + hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
        return self.client.post(f"/api/whatsapp/webhook/meta/{token or self.token}", content=raw,
                                headers={"X-Hub-Signature-256": sig, "Content-Type": "application/json"})

    def test_text_and_template_messages(self):
        lead = self.lead(self.owner)
        res = self.owner.post("/api/crm/whatsapp", json={"lead_id": lead["id"], "text": "Your visit is confirmed."})
        self.assertEqual(res.status_code, 200, res.text)
        self.assertEqual((res.json()["status"], res.json()["direction"]), ("sent", "out"))
        sent = json.loads(self.fake.sent[-1].content)
        self.assertEqual(self.fake.sent[-1].url.path, "/v21.0/1055/messages")
        self.assertEqual((sent["to"], sent["type"], sent["text"]["body"]), (lead["phone"].lstrip("+"), "text", "Your visit is confirmed."))

        tpl = {"name": "appointment_reminder", "language": "en_US", "params": ["Asha", "Mon 10 AM"]}
        self.assertEqual(self.owner.post("/api/crm/whatsapp", json={"lead_id": lead["id"], "template": tpl}).status_code, 200)
        sent = json.loads(self.fake.sent[-1].content)["template"]
        self.assertEqual((sent["name"], sent["language"]["code"]), ("appointment_reminder", "en_US"))
        self.assertEqual([p["text"] for p in sent["components"][0]["parameters"]], ["Asha", "Mon 10 AM"])

        log = self.owner.get(f"/api/whatsapp/messages?lead_id={lead['id']}").json()
        self.assertEqual(len(log), 2)
        db = SessionLocal()
        try:
            titles = [a.title for a in db.query(LeadActivity).filter(LeadActivity.lead_id == lead["id"])]
        finally:
            db.close()
        self.assertEqual(titles.count("WhatsApp sent"), 2)

    def test_closed_24_hour_window_is_explained(self):
        self.fake.meta_error = {"message": "Re-engagement message", "code": 131047}
        res = self.owner.post("/api/crm/whatsapp", json={"phone": _phone(), "text": "hello"})
        self.assertEqual(res.status_code, 502)
        self.assertIn("approved template", res.json()["detail"])
        self.assertEqual(self.owner.get("/api/whatsapp/messages").json()[0]["status"], "failed")

    def test_webhook_verification_and_signatures(self):
        ok = self.client.get(f"/api/whatsapp/webhook/meta/{self.token}",
                             params={"hub.mode": "subscribe", "hub.verify_token": self.token, "hub.challenge": "12345"})
        self.assertEqual((ok.status_code, ok.text), (200, "12345"))
        wrong = self.client.get(f"/api/whatsapp/webhook/meta/{self.token}",
                                params={"hub.mode": "subscribe", "hub.verify_token": "nope", "hub.challenge": "1"})
        self.assertEqual(wrong.status_code, 403)
        self.assertEqual(self.hook({}, secret="forged").status_code, 401)
        self.assertEqual(self.hook({}, token="unknown-token").status_code, 404)
        self.assertEqual(self.hook({"entry": []}).status_code, 200)

    def test_delivery_status_and_replies(self):
        lead = self.lead(self.owner)
        msg = self.owner.post("/api/crm/whatsapp", json={"lead_id": lead["id"], "text": "hi"}).json()
        db = SessionLocal()
        try:
            from app.models.whatsapp import WhatsAppMessage
            provider_id = db.get(WhatsAppMessage, msg["id"]).provider_message_id
        finally:
            db.close()

        def status(value):
            return {"entry": [{"changes": [{"value": {"statuses": [{"id": provider_id, "status": value}]}}]}]}

        for value in ("delivered", "read", "delivered"):  # the late "delivered" must not undo "read"
            self.assertEqual(self.hook(status(value)).status_code, 200)
        self.assertEqual(self.owner.get("/api/whatsapp/messages").json()[0]["status"], "read")

        reply = {"entry": [{"changes": [{"value": {
            "contacts": [{"wa_id": lead["phone"].lstrip("+"), "profile": {"name": "Asha"}}],
            "messages": [{"from": lead["phone"].lstrip("+"), "id": "wamid.in1", "type": "text", "text": {"body": "Can we move it to 4pm?"}}],
        }}]}]}
        self.hook(reply)
        self.hook(reply)  # Meta retries: logged once
        inbound = [m for m in self.owner.get(f"/api/whatsapp/messages?lead_id={lead['id']}").json() if m["direction"] == "in"]
        self.assertEqual([m["body"] for m in inbound], ["Can we move it to 4pm?"])

        stranger = _phone()
        self.hook({"entry": [{"changes": [{"value": {
            "contacts": [{"wa_id": stranger.lstrip("+"), "profile": {"name": "Ravi"}}],
            "messages": [{"from": stranger.lstrip("+"), "id": "wamid.in2", "type": "image"}]}}]}]})
        leads = {lead_row["phone"]: lead_row for lead_row in self.owner.get(f"/api/crm/leads?search={stranger[-8:]}").json()}
        self.assertEqual(leads[stranger]["name"], "Ravi")
        db = SessionLocal()
        try:
            kinds = [n.kind for n in db.query(Notification).filter(Notification.tenant_id == self.owner.tenant_id)]
        finally:
            db.close()
        self.assertEqual(kinds.count("whatsapp_received"), 2)

    def test_another_workspace_cannot_touch_these_messages(self):
        other = _TenantClient(self.client)
        other_hook = other.put("/api/integrations/whatsapp", json=META).json()["webhook_url"].rsplit("/", 1)[1]
        self.owner.post("/api/crm/whatsapp", json={"phone": _phone(), "text": "hi"})
        db = SessionLocal()
        try:
            from app.models.whatsapp import WhatsAppMessage
            provider_id = db.query(WhatsAppMessage).filter(WhatsAppMessage.tenant_id == self.owner.tenant_id).first().provider_message_id
        finally:
            db.close()
        self.hook({"entry": [{"changes": [{"value": {"statuses": [{"id": provider_id, "status": "read"}]}}]}]}, token=other_hook)
        self.assertEqual(self.owner.get("/api/whatsapp/messages").json()[0]["status"], "sent")
        self.assertEqual(other.get("/api/whatsapp/messages").json(), [])

    def test_workflow_step_fills_placeholders(self):
        wf = self.owner.post("/api/crm/workflows", json={
            "name": "Welcome", "trigger_event": "lead_created",
            "actions": [{"type": "send_whatsapp", "config": {"message": "Hi {{lead.first_name}}, thanks for contacting {{workspace.name}}."}},
                        {"type": "send_whatsapp", "config": {"template": "welcome", "language": "en", "params": "{{lead.name}}\n{{custom.city}}"}}]})
        self.assertEqual(wf.status_code, 201, wf.text)
        lead = self.lead(self.owner)
        asyncio.run(workflow_engine._execute_workflows("lead_created", lead["id"], self.owner.tenant_id))
        bodies = [json.loads(r.content) for r in self.fake.sent[-2:]]
        self.assertEqual(bodies[0]["text"]["body"], "Hi Asha, thanks for contacting Co.")
        # Template values are positional, so an empty one keeps its place.
        self.assertEqual([p["text"] for p in bodies[1]["template"]["components"][0]["parameters"]], ["Asha Rao", ""])
        runs = self.owner.get(f"/api/crm/workflows/{wf.json()['id']}/runs").json()
        self.assertEqual(runs[0]["status"], "success", runs[0])

    def test_failed_workflow_step_fails_the_run(self):
        self.fake.meta_error = {"message": "Re-engagement message", "code": 131047}
        wf = self.owner.post("/api/crm/workflows", json={"name": "Nudge", "trigger_event": "lead_created",
                                                        "actions": [{"type": "send_whatsapp", "config": {"message": "hi"}}]}).json()
        lead = self.lead(self.owner)
        asyncio.run(workflow_engine._execute_workflows("lead_created", lead["id"], self.owner.tenant_id))
        run = self.owner.get(f"/api/crm/workflows/{wf['id']}/runs").json()[0]
        self.assertEqual(run["status"], "failed")
        self.assertIn("approved template", run["message"])


def _twilio_signature(token: str, url: str, params: dict) -> str:
    """Twilio's documented algorithm, written independently of the app's version."""
    s = url
    for key in sorted(params):
        s += key + params[key]
    return base64.b64encode(hmac.new(token.encode(), s.encode(), hashlib.sha1).digest()).decode()


class TestTwilio(WhatsAppTestCase):
    def test_send_status_and_reply(self):
        owner = _TenantClient(self.client)
        with patch("app.core.settings.settings.public_api_url", "https://api.example.com"):
            account = owner.put("/api/integrations/whatsapp", json=TWILIO)
            self.assertEqual(account.status_code, 200, account.text)
            self.assertEqual(account.json()["sender"], "+14155550100")
            hook_url = account.json()["webhook_url"]
            self.assertTrue(hook_url.startswith("https://api.example.com/api/whatsapp/webhook/twilio/"))
            lead = self.lead(owner)
            tpl = {"name": "HX0123456789abcdef", "params": ["Asha", "Mon"]}
            self.assertEqual(owner.post("/api/crm/whatsapp", json={"lead_id": lead["id"], "template": tpl}).status_code, 200)
            form = {k: v[0] for k, v in parse_qs(self.fake.sent[-1].content.decode()).items()}
            self.assertEqual((form["From"], form["To"]), ("whatsapp:+14155550100", f"whatsapp:{lead['phone']}"))
            self.assertEqual((form["ContentSid"], json.loads(form["ContentVariables"])), ("HX0123456789abcdef", {"1": "Asha", "2": "Mon"}))
            self.assertEqual(form["StatusCallback"], hook_url)
            sid = owner.get("/api/whatsapp/messages").json()[0]
            db = SessionLocal()
            try:
                from app.models.whatsapp import WhatsAppMessage
                message_sid = db.get(WhatsAppMessage, sid["id"]).provider_message_id
            finally:
                db.close()

            path = "/api/whatsapp/webhook/twilio/" + hook_url.rsplit("/", 1)[1]

            def post(params, token="twilio-token"):
                return self.client.post(path, data=params, headers={"X-Twilio-Signature": _twilio_signature(token, hook_url, params)})

            self.assertEqual(post({"MessageSid": message_sid, "MessageStatus": "delivered"}, token="forged").status_code, 401)
            self.assertEqual(post({"MessageSid": message_sid, "MessageStatus": "delivered"}).status_code, 200)
            self.assertEqual(owner.get("/api/whatsapp/messages").json()[0]["status"], "delivered")
            res = post({"MessageSid": "SMin1", "From": f"whatsapp:{lead['phone']}", "Body": "Yes, see you then", "ProfileName": "Asha"})
            self.assertEqual(res.status_code, 200)
            self.assertIn("<Response></Response>", res.text)
            inbound = [m for m in owner.get(f"/api/whatsapp/messages?lead_id={lead['id']}").json() if m["direction"] == "in"]
            self.assertEqual([m["body"] for m in inbound], ["Yes, see you then"])


if __name__ == "__main__":
    unittest.main()
