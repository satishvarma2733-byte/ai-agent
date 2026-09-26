"""Live call operations from the dashboard: transfer, voicemail drop and listening in, against a fake LiveKit."""
import json
import os
import unittest
import uuid
from types import SimpleNamespace
from unittest.mock import patch

import jwt
from fastapi.testclient import TestClient
from livekit import api

from app.core.database import Base, SessionLocal, engine
from app.main import app
from app.models.audit import AuditLog
from app.models.call import CallLog
from app.services import call_control
from app.tests.test_consolidation import _TenantClient
from app.tests.test_regression_matrix import _Member

LIVEKIT = {"livekit_url": "wss://lk.example.com", "livekit_api_key": "APIkey", "livekit_api_secret": "secret-for-tests-long-enough-32b"}


class FakeLiveKit:
    def __init__(self, participants=None, missing_room=False):
        self.sent, self.transfers = [], []
        self.participants = participants if participants is not None else [
            SimpleNamespace(identity="agent-1", kind=api.ParticipantInfo.Kind.AGENT),
            SimpleNamespace(identity="sip_919000000080", kind=api.ParticipantInfo.Kind.SIP),
        ]
        self.missing_room = missing_room
        outer = self

        class Room:
            async def list_participants(self, req):
                if outer.missing_room:
                    raise api.TwirpError("not_found", "room not found", status=404)
                return SimpleNamespace(participants=outer.participants)

            async def send_data(self, req):
                if outer.missing_room:
                    raise api.TwirpError("not_found", "room not found", status=404)
                outer.sent.append(req)

        class Sip:
            async def transfer_sip_participant(self, req):
                outer.transfers.append(req)

        self.room, self.sip = Room(), Sip()

    async def aclose(self):
        pass


class TestCallOperations(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        Base.metadata.create_all(bind=engine)
        cls.client = TestClient(app)

    def setUp(self):
        self.owner = _TenantClient(self.client)
        self.room = f"call-{uuid.uuid4().hex[:8]}"
        db = SessionLocal()
        try:
            db.add(CallLog(tenant_id=self.owner.tenant_id, phone_number="+919000000080", call_room_id=self.room, direction="inbound"))
            db.commit()
        finally:
            db.close()
        self.fake = FakeLiveKit()
        for p in (patch.object(call_control, "_client", lambda config: self.fake),
                  patch("app.core.runtime_config.load_runtime_config", return_value=dict(LIVEKIT)),
                  patch.dict(os.environ, {"DEFAULT_TRANSFER_NUMBER": "", "VOBIZ_SIP_DOMAIN": ""})):
            p.start()
            self.addCleanup(p.stop)

    def test_transfer_hands_the_phone_leg_to_a_number(self):
        res = self.owner.post("/api/inbound/transfer", json={"id": self.room, "to": "+91 98765 43210"})
        self.assertEqual(res.status_code, 200, res.text)
        [req] = self.fake.transfers
        self.assertEqual((req.room_name, req.participant_identity, req.transfer_to), (self.room, "sip_919000000080", "tel:+919876543210"))
        with patch.dict(os.environ, {"VOBIZ_SIP_DOMAIN": "acme.sip.vobiz.ai"}):
            self.owner.post("/api/outbound/transfer", json={"id": self.room, "to": "+919876543210"})
        self.assertEqual(self.fake.transfers[-1].transfer_to, "sip:+919876543210@acme.sip.vobiz.ai")
        db = SessionLocal()
        try:
            self.assertTrue(db.query(AuditLog).filter(AuditLog.tenant_id == self.owner.tenant_id, AuditLog.action == "call_transferred").count())
        finally:
            db.close()

    def test_transfer_needs_a_number_and_a_caller(self):
        self.assertEqual(self.owner.post("/api/inbound/transfer", json={"id": self.room}).status_code, 422)
        self.assertEqual(self.owner.post("/api/inbound/transfer", json={"id": self.room, "to": "12"}).status_code, 422)
        with patch.dict(os.environ, {"DEFAULT_TRANSFER_NUMBER": "+919999900000"}):
            self.assertEqual(self.owner.post("/api/inbound/transfer", json={"id": self.room}).status_code, 200)
        self.fake.participants = [SimpleNamespace(identity="agent-1", kind=api.ParticipantInfo.Kind.AGENT)]
        self.assertEqual(self.owner.post("/api/inbound/transfer", json={"id": self.room, "to": "+919876543210"}).status_code, 409)
        self.fake.missing_room = True
        self.assertEqual(self.owner.post("/api/inbound/transfer", json={"id": self.room, "to": "+919876543210"}).status_code, 409)

    def test_voicemail_sends_a_command_to_the_agent(self):
        res = self.owner.post("/api/outbound/voicemail", json={"id": self.room, "message": "Hi, please call us back."})
        self.assertEqual(res.status_code, 200, res.text)
        [req] = self.fake.sent
        self.assertEqual((req.room, req.topic), (self.room, call_control.CONTROL_TOPIC))
        self.assertEqual(json.loads(req.data), {"action": "voicemail", "message": "Hi, please call us back."})
        self.owner.post("/api/inbound/voicemail", json={"id": self.room})
        self.assertEqual(json.loads(self.fake.sent[-1].data)["message"], call_control.DEFAULT_VOICEMAIL)
        self.assertEqual(self.owner.post("/api/inbound/voicemail", json={"id": self.room, "message": "x" * 700}).status_code, 422)

    def test_listening_in_is_receive_only_hidden_and_for_managers(self):
        agent = _Member(self.client, self.owner, "Agent")
        self.assertEqual(agent.post("/api/calls/listen", json={"id": self.room}).status_code, 403)
        res = self.owner.post("/api/calls/listen", json={"id": self.room})
        self.assertEqual(res.status_code, 200, res.text)
        body = res.json()
        self.assertEqual((body["url"], body["room"]), ("wss://lk.example.com", self.room))
        claims = jwt.decode(body["token"], LIVEKIT["livekit_api_secret"], algorithms=["HS256"], options={"verify_aud": False})
        video = claims["video"]
        self.assertEqual((video["room"], video["roomJoin"], video["canSubscribe"], video["canPublish"], video["canPublishData"], video["hidden"]),
                         (self.room, True, True, False, False, True))
        self.assertTrue(claims["sub"].startswith("monitor-"))

    def test_other_workspaces_calls_are_out_of_reach(self):
        other = _TenantClient(self.client)
        for path, body in (("/api/inbound/transfer", {"to": "+919876543210"}), ("/api/outbound/voicemail", {}), ("/api/calls/listen", {})):
            self.assertEqual(other.post(path, json={"id": self.room, **body}).status_code, 404, path)
        self.assertEqual((self.fake.sent, self.fake.transfers), ([], []))

    def test_without_livekit(self):
        with patch.object(call_control, "_client", lambda config: None), \
             patch.object(call_control, "get_livekit_settings", return_value={"url": "", "api_key": "", "api_secret": ""}):
            # get_livekit_settings falls back to the machine's own .env, so it's blanked out explicitly.
            self.assertEqual(self.owner.post("/api/outbound/voicemail", json={"id": self.room}).status_code, 503)
            self.assertEqual(self.owner.post("/api/calls/listen", json={"id": self.room}).status_code, 503)


if __name__ == "__main__":
    unittest.main()
