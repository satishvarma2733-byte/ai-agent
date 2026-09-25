"""Routes ported from the legacy backend_api.py and the voice-worker → app DB bridge."""
import io
import os
import re
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.main import app
from app.core.database import Base, SessionLocal, engine
from app.models.call import CallLog
from app.models.campaign import Campaign, CampaignLead

# Smallest valid PNG (1x1 transparent pixel).
PNG = bytes.fromhex("89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000d4944415478da63f8ffff3f0005fe02fea7d6a4560000000049454e44ae426082")
UI_API_DIR = Path(__file__).resolve().parents[2] / "web" / "src" / "api"


class _TenantClient:
    def __init__(self, client: TestClient):
        self.client = client
        email = f"u-{uuid.uuid4().hex[:10]}@example.com"
        signup = client.post("/api/auth/signup", json={"email": email, "password": "correct-horse-1", "name": "T", "company_name": "Co"})
        assert signup.status_code == 202, signup.text
        token = client.post("/api/auth/login", json={"email": email, "password": "correct-horse-1"}).json()["access_token"]
        self.headers = {"Authorization": f"Bearer {token}"}
        self.tenant_id = client.get("/api/auth/me", headers=self.headers).json()["tenant_id"]

    def __getattr__(self, method):
        fn = getattr(self.client, method)
        return lambda url, **kw: fn(url, headers=self.headers, **kw)


class TestConsolidation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        Base.metadata.create_all(bind=engine)
        cls.client = TestClient(app)

    def test_every_ui_endpoint_exists_in_app(self):
        """No UI call should 404 because a route was left behind in backend_api.py."""
        if not UI_API_DIR.is_dir():
            self.skipTest("web/ UI not present")
        routes = [(m, r.path) for r in app.routes for m in getattr(r, "methods", [])]

        def exists(method: str, ui_path: str) -> bool:
            for m, path in routes:
                pattern = "^" + re.sub(r"\{[^}]+\}", "[^/]+", path) + "$"
                if m == method and re.match(pattern, ui_path):
                    return True
            return False

        missing = []
        call = re.compile(r"api\.(get|post|put|patch|delete|upload)(?:<[^>]*>)?\(\s*[`'\"]([^`'\"]+)")
        for ts in UI_API_DIR.glob("*.ts"):
            for method, path in call.findall(ts.read_text(encoding="utf-8")):
                http = "POST" if method == "upload" else method.upper()
                # `${id}` → sample segment; drop query strings and conditional suffixes.
                probe = re.split(r"[?$]", re.sub(r"\$\{[^}]*\}", "x", path))[0]
                if not exists(http, probe):
                    missing.append(f"{http} {path} ({ts.name})")
        self.assertEqual(missing, [], "UI endpoints without an app/ route")

    def test_config_is_admin_only_and_masks_secrets(self):
        admin = _TenantClient(self.client)
        with patch("app.core.runtime_config.read_config", return_value={"google_api_key": "AIzaSECRETVALUE1234", "first_line": "Hi"}):
            res = admin.get("/api/config")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["google_api_key"], "••••1234")
        self.assertEqual(res.json()["first_line"], "Hi")
        self.assertEqual(self.client.get("/api/config").status_code, 401)

    def test_config_post_ignores_masked_secrets(self):
        admin = _TenantClient(self.client)
        with patch("app.core.runtime_config.write_config", side_effect=lambda d: d) as write, \
             patch("app.core.runtime_config.read_config", return_value={}), \
             patch("app.core.runtime_config.apply_config_env"):
            res = admin.post("/api/config", json={"google_api_key": "••••1234", "first_line": "Hello"})
        self.assertEqual(res.status_code, 200, res.text)
        write.assert_called_once_with({"first_line": "Hello"})

    def test_recording_missing_returns_404_not_sample(self):
        user = _TenantClient(self.client)
        self.assertEqual(user.get("/api/recordings/does-not-exist.wav").status_code, 404)

    def test_media_upload_cannot_escape_media_dir(self):
        user = _TenantClient(self.client)
        cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                res = user.post("/api/cms/media/upload", files={"file": ("../../evil.png", io.BytesIO(PNG), "image/png")})
                self.assertEqual(res.status_code, 201, res.text)
                body = res.json()
                self.assertEqual(body["filename"], "evil.png")
                self.assertTrue(body["url"].startswith(f"/data/media/{user.tenant_id}/"))
                self.assertNotIn("..", body["url"])
                self.assertTrue(Path(tmp, body["url"].lstrip("/")).is_file())
                self.assertFalse(Path(tmp).parent.joinpath("evil.png").exists())
            finally:
                os.chdir(cwd)

    def test_media_upload_accepts_only_passive_formats(self):
        user = _TenantClient(self.client)
        cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                html = b"<html><script>alert(1)</script></html>"
                for name, data, ctype in [("page.html", html, "text/html"), ("logo.png", html, "image/png"),
                                          ("icon.svg", b"<svg onload='alert(1)'/>", "image/svg+xml"), ("x.exe", b"MZ", "application/octet-stream")]:
                    res = user.post("/api/cms/media/upload", files={"file": (name, io.BytesIO(data), ctype)})
                    self.assertEqual(res.status_code, 415, f"{name}: {res.text}")

                # A real PNG is stored under the detected type and served inertly.
                res = user.post("/api/cms/media/upload", files={"file": ("photo.html", io.BytesIO(PNG), "text/html")})
                self.assertEqual(res.status_code, 201, res.text)
                media = res.json()
                self.assertTrue(media["url"].endswith(".png"))
                self.assertEqual(media["mime_type"], "image/png")
                served = self.client.get(media["url"])
                self.assertEqual(served.status_code, 200)
                self.assertEqual(served.headers["content-type"], "image/png")
                self.assertEqual(served.headers["x-content-type-options"], "nosniff")
                self.assertIn("sandbox", served.headers["content-security-policy"])

                # Anything that isn't a stored name of an allowed type is never served.
                folder = Path(tmp, "data", "media", user.tenant_id)
                (folder / "planted.html").write_bytes(html)
                self.assertEqual(self.client.get(f"/data/media/{user.tenant_id}/planted.html").status_code, 404)
                self.assertEqual(self.client.get(f"/data/media/{user.tenant_id}/..%2F..%2Fapp.db").status_code, 404)

                other = _TenantClient(self.client)
                self.assertEqual(other.delete(f"/api/cms/media/{media['id']}").status_code, 404)
                self.assertEqual(user.delete(f"/api/cms/media/{media['id']}").status_code, 200)
                self.assertEqual(self.client.get(media["url"]).status_code, 404)
            finally:
                os.chdir(cwd)

    def test_campaign_export_neutralises_spreadsheet_formulas(self):
        owner = _TenantClient(self.client)
        camp = owner.post("/api/crm/campaigns", json={"name": "CSV", "leads": [
            {"phone": "9000000011", "name": "=HYPERLINK(\"http://x\")"}, {"phone": "9000000012", "name": "@SUM(A1)"},
            {"phone": "9000000013", "name": "+1-555"}, {"phone": "9000000014", "name": "Plain Name"}]}).json()
        text = owner.get(f"/api/crm/campaigns/{camp['id']}/export").text
        for payload in ("=HYPERLINK", "@SUM", "+1-555"):
            self.assertIn(f"'{payload}", text)
            self.assertNotIn(f",{payload}", text)
        self.assertIn(",Plain Name,", text)

    def test_cms_slugs_are_unique_per_tenant(self):
        first, second = _TenantClient(self.client), _TenantClient(self.client)
        slug = f"pricing-{uuid.uuid4().hex[:6]}"
        self.assertEqual(first.post("/api/cms/pages", json={"title": "A", "slug": slug, "content": "a"}).status_code, 201)
        self.assertEqual(second.post("/api/cms/pages", json={"title": "B", "slug": slug, "content": "b"}).status_code, 201)
        dup = first.post("/api/cms/pages", json={"title": "A2", "slug": slug, "content": "a"})
        self.assertEqual(dup.status_code, 409, dup.text)

    def test_recordings_are_tenant_scoped(self):
        owner, other = _TenantClient(self.client), _TenantClient(self.client)
        room = f"room-{uuid.uuid4().hex[:8]}"
        db = SessionLocal()
        try:
            db.add(CallLog(tenant_id=owner.tenant_id, phone_number="+919000000020", call_room_id=room, direction="inbound"))
            db.commit()
        finally:
            db.close()
        from app.routers import system
        with tempfile.TemporaryDirectory() as tmp, patch.object(system, "RECORDINGS_DIR", Path(tmp)):
            Path(tmp, f"{room}.wav").write_bytes(b"RIFF0000WAVEfmt ")
            self.assertEqual(owner.get(f"/api/recordings/{room}.wav").status_code, 200)
            self.assertEqual(other.get(f"/api/recordings/{room}.wav").status_code, 404)

    def test_dialling_limits(self):
        owner = _TenantClient(self.client)
        agent_email = f"dial-{uuid.uuid4().hex[:6]}@example.com"
        with patch("app.routers.team.deliver", return_value="logged"):
            token = owner.post("/api/team/invitations", json={"email": agent_email, "role": "Agent"}).json()["accept_url"].split("token=")[1]
        access = self.client.post("/api/auth/invitations/accept", json={"token": token, "name": "A", "password": "correct-horse-1"}).json()["access_token"]
        headers = {"Authorization": f"Bearer {access}"}
        self.assertEqual(self.client.post("/api/call/bulk", json={"numbers": ["+919000000030"]}, headers=headers).status_code, 403)
        too_many = owner.post("/api/call/bulk", json={"numbers": [f"+9190000{i:05d}" for i in range(101)]})
        self.assertEqual(too_many.status_code, 422)
        from app.routers import calls
        new_room = AsyncMock(side_effect=lambda *a, **k: {"status": "ok", "room": f"dial-{uuid.uuid4().hex[:8]}"})
        with patch.object(calls, "SINGLE_CALLS_PER_HOUR", 2), \
             patch("app.routers.calls.dispatch_outbound_call", new_room), \
             patch("app.core.runtime_config.load_runtime_config", return_value={}):
            codes = [self.client.post("/api/call/single", json={"phone": "+919000000031"}, headers=headers).status_code for _ in range(3)]
        self.assertEqual(codes, [200, 200, 429])

    def test_api_docs_are_local_only(self):
        from app.core.settings import settings
        self.assertTrue(settings.is_local)
        self.assertEqual(self.client.get("/openapi.json").status_code, 200)

    def test_api_sends_security_headers(self):
        res = self.client.get("/health")
        for header, value in [("x-content-type-options", "nosniff"), ("x-frame-options", "DENY"),
                              ("referrer-policy", "strict-origin-when-cross-origin")]:
            self.assertEqual(res.headers.get(header), value)
        self.assertIn("default-src 'none'", res.headers.get("content-security-policy", ""))

    def test_campaign_lifecycle_and_tenant_isolation(self):
        owner, other = _TenantClient(self.client), _TenantClient(self.client)
        res = owner.post("/api/crm/campaigns", json={
            "name": "Spring",
            "leads": [{"phone": "9876543210", "name": "A"}, {"phone": "+919876543210", "name": "dup"}, {"phone": "9123456780"}],
        })
        self.assertEqual(res.status_code, 201, res.text)
        camp = res.json()
        self.assertEqual(camp["total_leads"], 2, "duplicate phone after normalisation must be skipped")

        listed = owner.get("/api/crm/campaigns").json()
        self.assertIsInstance(listed, list)
        self.assertEqual([c["id"] for c in listed], [camp["id"]])
        self.assertEqual(other.get("/api/crm/campaigns").json(), [])
        self.assertEqual(other.get(f"/api/crm/campaigns/{camp['id']}").status_code, 404)

        self.assertEqual(owner.post(f"/api/crm/campaigns/{camp['id']}/pause").status_code, 409)
        self.assertEqual(owner.post(f"/api/crm/campaigns/{camp['id']}/start").status_code, 200)
        detail = owner.get(f"/api/crm/campaigns/{camp['id']}").json()
        self.assertEqual(detail["status"], "running")
        self.assertEqual({l["phone"] for l in detail["leads"]}, {"+919876543210", "+919123456780"})

        csv_res = owner.get(f"/api/crm/campaigns/{camp['id']}/export")
        self.assertEqual(csv_res.status_code, 200)
        self.assertIn("+919876543210", csv_res.text)

        self.assertEqual(owner.delete(f"/api/crm/campaigns/{camp['id']}").status_code, 200)

    def test_campaign_worker_dispatches_with_tenant_and_marks_completion(self):
        from app.services import campaign_worker
        from app.services.call_store import finish_campaign_lead

        owner = _TenantClient(self.client)
        camp = owner.post("/api/crm/campaigns", json={"name": "W", "concurrency_limit": 1, "leads": [{"phone": "9000000001"}, {"phone": "9000000002"}]}).json()
        owner.post(f"/api/crm/campaigns/{camp['id']}/start")

        jobs = [j for j in campaign_worker._claim_batch() if j["campaign_id"] == camp["id"]]
        self.assertEqual(len(jobs), 1, "concurrency limit 1")
        self.assertEqual([j for j in campaign_worker._claim_batch() if j["campaign_id"] == camp["id"]], [], "slot still busy")

        room = f"room-{uuid.uuid4().hex[:8]}"
        dispatch = AsyncMock(return_value={"room": room})
        with patch.object(campaign_worker, "dispatch_outbound_call", dispatch), \
             patch.object(campaign_worker, "load_runtime_config", return_value={}):
            import asyncio
            asyncio.run(campaign_worker._dispatch(jobs[0]))
        meta = dispatch.call_args.kwargs["extra_metadata"]
        self.assertEqual(meta["tenant_id"], owner.tenant_id)
        self.assertEqual(meta["campaign_lead_id"], jobs[0]["campaign_lead_id"])

        db = SessionLocal()
        try:
            log = db.query(CallLog).filter(CallLog.call_room_id == room).first()
            self.assertEqual(log.tenant_id, owner.tenant_id)
        finally:
            db.close()

        finish_campaign_lead(jobs[0]["campaign_lead_id"], "booked")
        nxt = [j for j in campaign_worker._claim_batch() if j["campaign_id"] == camp["id"]]
        self.assertEqual(len(nxt), 1, "slot freed after completion")
        finish_campaign_lead(nxt[0]["campaign_lead_id"], "no_answer")
        campaign_worker._claim_batch()
        detail = owner.get(f"/api/crm/campaigns/{camp['id']}").json()
        self.assertEqual(detail["status"], "completed")
        self.assertEqual(detail["scheduled_leads"], 1)

    def test_failed_dispatch_is_retried_then_fails(self):
        from app.services import campaign_worker

        owner = _TenantClient(self.client)
        camp = owner.post("/api/crm/campaigns", json={"name": "R", "retry_limit": 1, "leads": [{"phone": "9000000003"}]}).json()
        owner.post(f"/api/crm/campaigns/{camp['id']}/start")
        failing = AsyncMock(side_effect=RuntimeError("SIP down"))
        import asyncio
        with patch.object(campaign_worker, "dispatch_outbound_call", failing), \
             patch.object(campaign_worker, "load_runtime_config", return_value={}):
            for expected in ("pending", "failed"):
                job = [j for j in campaign_worker._claim_batch() if j["campaign_id"] == camp["id"]][0]
                asyncio.run(campaign_worker._dispatch(job))
                lead = owner.get(f"/api/crm/campaigns/{camp['id']}").json()["leads"][0]
                self.assertEqual(lead["status"], expected)

    def test_voice_worker_call_log_gets_tenant_and_direction(self):
        import db_backend

        owner = _TenantClient(self.client)
        room = f"room-{uuid.uuid4().hex[:8]}"
        db_backend.save_call_log("+919999999999", 42, "hi", call_room_id=room, tenant_id=owner.tenant_id, direction="outbound")
        logs = owner.get("/api/logs").json()
        match = [l for l in logs if l["call_room_id"] == room]
        self.assertEqual(len(match), 1, "agent-saved call must be visible to its tenant")
        self.assertEqual(match[0]["direction"], "outbound")
        self.assertEqual(match[0]["duration_seconds"], 42)

    def test_single_call_does_not_crash_after_dispatch(self):
        owner = _TenantClient(self.client)
        with patch("app.routers.calls.dispatch_outbound_call", AsyncMock(return_value={"status": "ok", "room": "room-single"})), \
             patch("app.core.runtime_config.load_runtime_config", return_value={}):
            res = owner.post("/api/call/single", json={"phone": "+919999999998"})
        self.assertEqual(res.status_code, 200, res.text)


if __name__ == "__main__":
    unittest.main()
