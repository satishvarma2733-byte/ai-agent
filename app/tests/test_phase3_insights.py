"""Phase 3: per-language analytics, profitability, business settings, tasks, @mentions and new knowledge-base formats."""
import io
import unittest
import uuid
import zipfile
from datetime import date, timedelta
from unittest.mock import patch

from fastapi.testclient import TestClient

import kb
from app.core.database import Base, SessionLocal, engine
from app.main import app
from app.models.call import CallLog
from app.models.campaign import CampaignLead
from app.models.notification import Notification
from app.services import call_language
from app.tests.test_consolidation import _TenantClient
from app.tests.test_regression_matrix import _Member


def _phone() -> str:
    return "+9193" + str(uuid.uuid4().int)[:8]


def _docx(paragraphs: list[str], table: list[list[str]]) -> bytes:
    w = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    para = "".join(f"<w:p><w:r><w:t>{p}</w:t></w:r></w:p>" for p in paragraphs)
    rows = "".join("<w:tr>" + "".join(f"<w:tc><w:p><w:r><w:t>{c}</w:t></w:r></w:p></w:tc>" for c in r) + "</w:tr>" for r in table)
    xml = f'<?xml version="1.0" encoding="UTF-8"?><w:document xmlns:w="{w}"><w:body>{para}<w:tbl>{rows}</w:tbl></w:body></w:document>'
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("word/document.xml", xml)
    return buffer.getvalue()


class TestLanguages(unittest.TestCase):
    def test_detection(self):
        self.assertEqual(call_language.detect("[USER] నమస్కారం, అపాయింట్‌మెంట్ కావాలి\n[ASSISTANT] Sure"), "te")
        self.assertEqual(call_language.detect("[USER] मुझे कल का समय चाहिए\n[ASSISTANT] ठीक है"), "hi")
        self.assertEqual(call_language.detect("[USER] I need an appointment tomorrow"), "en")
        self.assertEqual(call_language.detect("[USER] naaku appointment kavali, రేపు ఉదయం please book"), "mixed")
        # Only the caller's lines count: an English-speaking agent doesn't make a Telugu call English.
        self.assertEqual(call_language.detect("[ASSISTANT] Hello, how can I help?\n[USER] రేపు ఉదయం"), "te")
        self.assertEqual(call_language.detect(""), "unknown")


class InsightsTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        Base.metadata.create_all(bind=engine)
        cls.client = TestClient(app)

    def setUp(self):
        self.owner = _TenantClient(self.client)

    def call(self, *, transcript="[USER] hello there", seconds=120, booked=False, cost=0.5, agent_id=None, room=None):
        db = SessionLocal()
        try:
            db.add(CallLog(tenant_id=self.owner.tenant_id, phone_number=_phone(), direction="inbound", transcript=transcript,
                           duration_seconds=seconds, was_booked=booked, estimated_cost_usd=cost, agent_id=agent_id,
                           call_room_id=room or f"room-{uuid.uuid4().hex[:8]}"))
            db.commit()
        finally:
            db.close()


class TestAnalytics(InsightsTestCase):
    def test_overview_by_language(self):
        self.call(transcript="[USER] రేపు ఉదయం అపాయింట్‌మెంట్", booked=True)
        self.call(transcript="[USER] రేపు సాయంత్రం")
        self.call(transcript="[USER] I'd like to book")
        langs = {row["language"]: row for row in self.owner.get("/api/stats/overview?tz=UTC&days=7").json()["languages"]}
        self.assertEqual((langs["te"]["calls"], langs["te"]["bookings"], langs["te"]["name"]), (2, 1, "Telugu"))
        self.assertEqual(langs["en"]["calls"], 1)

    def test_profitability_per_agent_and_campaign(self):
        agent = self.owner.post("/api/agents", json={"name": "Aria", "voice": "Aoede", "model": "gemini-2.0-flash-live-001",
                                                    "instructions": "x", "language": "en"}).json()
        self.call(agent_id=agent["id"], booked=True, cost=0.4)
        self.call(agent_id=agent["id"], cost=0.2)
        camp = self.owner.post("/api/crm/campaigns", json={"name": "Spring", "leads": [{"phone": "9000000081"}, {"phone": "9000000082"}]}).json()
        room = f"room-{uuid.uuid4().hex[:8]}"
        self.call(room=room, booked=True, cost=0.3)
        db = SessionLocal()
        try:
            lead = db.query(CampaignLead).filter(CampaignLead.campaign_id == camp["id"]).first()
            lead.call_room_id, lead.outcome, lead.status = room, "booked", "completed"
            db.commit()
        finally:
            db.close()
        body = self.owner.get("/api/stats/profitability?days=30").json()
        self.assertIsNone(body["booking_value"])
        aria = next(r for r in body["agents"] if r["id"] == agent["id"])
        self.assertEqual((aria["calls"], aria["bookings"], aria["conversion_rate"], aria["cost_usd"], aria["cost_per_booking_usd"], aria["revenue"]),
                         (2, 1, 50, 0.6, 0.6, None))
        spring = next(r for r in body["campaigns"] if r["id"] == camp["id"])
        self.assertEqual((spring["leads"], spring["reached"], spring["bookings"], spring["cost_usd"]), (2, 1, 1, 0.3))
        self.assertEqual(self.owner.put("/api/workspace/business", json={"booking_value": 1500, "currency": "INR"}).status_code, 200)
        body = self.owner.get("/api/stats/profitability?days=30").json()
        self.assertEqual((body["booking_value"], body["currency"], body["totals"]["revenue"]), (1500, "INR", 3000.0))

    def test_business_settings_are_validated_and_admin_only(self):
        self.assertEqual(self.owner.put("/api/workspace/business", json={"booking_value": 100, "currency": "XYZ"}).status_code, 422)
        self.assertEqual(self.owner.put("/api/workspace/business", json={"booking_value": -5}).status_code, 422)
        manager = _Member(self.client, self.owner, "Manager")
        self.assertEqual(manager.put("/api/workspace/business", json={"booking_value": 100}).status_code, 403)
        self.assertEqual(manager.get("/api/workspace/business").json()["currency"], "INR")
        other = _TenantClient(self.client)
        self.owner.put("/api/workspace/business", json={"booking_value": 999, "currency": "USD"})
        self.assertIsNone(other.get("/api/workspace/business").json()["booking_value"])


class TestTasksAndMentions(InsightsTestCase):
    def notifications(self, member_id: str, kind: str) -> list[str]:
        db = SessionLocal()
        try:
            return [n.title for n in db.query(Notification).filter(Notification.user_id == member_id, Notification.kind == kind)]
        finally:
            db.close()

    def test_tasks(self):
        agent = _Member(self.client, self.owner, "Agent")
        agent_id = agent.get("/api/auth/me").json()["id"]
        lead = self.owner.post("/api/crm/leads", json={"name": "Asha", "phone": _phone()}).json()
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        res = self.owner.post("/api/tasks", json={"title": "Call back about pricing", "due_date": yesterday,
                                                  "assigned_user_id": agent_id, "lead_id": lead["id"]})
        self.assertEqual(res.status_code, 201, res.text)
        task = res.json()
        self.assertEqual((task["lead_name"], task["overdue"], task["status"]), ("Asha", True, "open"))
        self.assertEqual(len(self.notifications(agent_id, "task_assigned")), 1)
        mine = agent.get("/api/tasks?mine=true").json()
        self.assertEqual([t["id"] for t in mine], [task["id"]])
        done = agent.patch(f"/api/tasks/{task['id']}", json={"status": "done"}).json()
        self.assertEqual((done["status"], done["overdue"]), ("done", False))
        self.assertEqual(agent.get("/api/tasks?mine=true").json(), [])
        self.assertEqual(len(agent.get("/api/tasks?mine=true&status=done").json()), 1)
        # Other workspaces and viewers.
        other = _TenantClient(self.client)
        self.assertEqual(other.patch(f"/api/tasks/{task['id']}", json={"status": "open"}).status_code, 404)
        self.assertEqual(self.owner.post("/api/tasks", json={"title": "x", "assigned_user_id": other.get("/api/auth/me").json()["id"]}).status_code, 422)
        viewer = _Member(self.client, self.owner, "Viewer")
        self.assertEqual(viewer.post("/api/tasks", json={"title": "x"}).status_code, 403)
        self.assertEqual(self.owner.delete(f"/api/tasks/{task['id']}").status_code, 204)

    def test_mentions_in_lead_notes(self):
        asha = _Member(self.client, self.owner, "Agent")
        asha_id = asha.get("/api/auth/me").json()["id"]
        lead = self.owner.post("/api/crm/leads", json={"name": "Ravi", "phone": _phone()}).json()
        # Members are invited with their role as name ("Agent"); mention by that first name.
        res = self.owner.post(f"/api/crm/leads/{lead['id']}/timeline",
                              json={"activity_type": "note", "title": "Note", "description": "@Agent please call him back today"})
        self.assertEqual(res.status_code, 201, res.text)
        self.assertEqual(len(self.notifications(asha_id, "mention")), 1)
        _Member(self.client, self.owner, "Agent")  # now "@Agent" is ambiguous
        self.owner.post(f"/api/crm/leads/{lead['id']}/timeline", json={"activity_type": "note", "title": "Note", "description": "@Agent again"})
        self.assertEqual(len(self.notifications(asha_id, "mention")), 1)


class TestKnowledgeFormats(InsightsTestCase):
    def test_docx_and_csv_text(self):
        text = kb._extract_docx_text(_docx(["Sunrise Dental", "Open 9am to 6pm"], [["Service", "Price"], ["Cleaning", "1500"]]))
        self.assertEqual(text, "Sunrise Dental\nOpen 9am to 6pm\nService | Price\nCleaning | 1500")
        csv_text = kb._extract_csv_text("﻿Service,Price,Notes\nCleaning,1500,\nWhitening,6000,Two visits\n".encode())
        self.assertEqual(csv_text, "Service: Cleaning; Price: 1500\nService: Whitening; Price: 6000; Notes: Two visits")

    def test_scanned_pdf_falls_back_to_ocr(self):
        source = {"id": 1, "source_type": "pdf_upload", "title": "scan.pdf", "mime_type": "application/pdf", "source_url": None}
        with patch.object(kb, "_download_source_bytes", return_value=b"%PDF-1.4 scanned"), \
             patch.object(kb, "_extract_pdf_text_from_bytes", return_value=""), \
             patch.object(kb, "_ocr_pdf", return_value="Clinic timings 9am to 6pm") as ocr:
            [doc] = kb._extract_documents(source, config={})
        ocr.assert_called_once()
        self.assertEqual((doc["body_text"], doc["metadata"]["ocr"]), ("Clinic timings 9am to 6pm", True))
        with patch.object(kb, "_download_source_bytes", return_value=b"%PDF-1.4"), \
             patch.object(kb, "_extract_pdf_text_from_bytes", return_value="x" * 200), \
             patch.object(kb, "_ocr_pdf") as ocr:
            kb._extract_documents(source, config={})
        ocr.assert_not_called()

    def test_upload_accepts_word_and_csv_only_when_real(self):
        with patch("kb.save_uploaded_file", return_value={"source_url": None, "storage_bucket": None, "storage_path": "x", "metadata": {}}), \
             patch("kb.create_source", return_value={"id": 1}), patch("app.routers.kb._process_soon"):
            ok = self.owner.post("/api/kb/upload", files={"file": ("prices.docx", io.BytesIO(_docx(["a"], [])), "application/octet-stream")})
            self.assertEqual(ok.status_code, 200, ok.text)
            fake = self.owner.post("/api/kb/upload", files={"file": ("prices.docx", io.BytesIO(b"not a zip"), "application/octet-stream")})
            self.assertEqual(fake.status_code, 400)
            self.assertEqual(self.owner.post("/api/kb/upload", files={"file": ("rates.csv", io.BytesIO(b"a,b\n1,2\n"), "text/csv")}).status_code, 200)


if __name__ == "__main__":
    unittest.main()
