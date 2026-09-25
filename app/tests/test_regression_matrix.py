"""Audit regression cases (RT-01 to RT-05, RT-09, RT-12): tenant isolation by id and in lists, the role x endpoint
matrix, forged tokens, recording links, and appointment overlaps. See the audit's sections 9 and 14."""
import base64
import io
import json
import re
import time
import unittest
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import jwt
from fastapi.testclient import TestClient

from app.core.database import Base, SessionLocal, engine
from app.core.security import ALGORITHM, SECRET_KEY
from app.main import app
from app.models.call import CallLog
from app.services import signed_urls
from app.tests.test_consolidation import PNG, _TenantClient

PASSWORD = "correct-horse-1"
ROLES = ("Viewer", "Agent", "Manager", "Admin", "Owner")


def _phone() -> str:
    return "+9198" + str(uuid.uuid4().int)[:8]


def _slot(days: int) -> dict:
    start = datetime.now(timezone.utc).replace(second=0, microsecond=0) + timedelta(days=days)
    return {"contact_name": "P", "contact_phone": _phone(), "timezone": "UTC",
            "scheduled_start": start.strftime("%Y-%m-%dT%H:%M"),
            "scheduled_end": (start + timedelta(minutes=30)).strftime("%Y-%m-%dT%H:%M")}


class _Member:
    """A teammate invited into `owner`'s workspace with `role`."""
    def __init__(self, client: TestClient, owner: _TenantClient, role: str):
        self.client = client
        email = f"rt-{uuid.uuid4().hex[:10]}@example.com"
        with patch("app.routers.team.deliver", return_value="logged"):
            invite = owner.post("/api/team/invitations", json={"email": email, "role": role})
        assert invite.status_code in (200, 201), invite.text
        token = invite.json()["accept_url"].split("token=")[1]
        access = client.post("/api/auth/invitations/accept", json={"token": token, "name": role, "password": PASSWORD}).json()["access_token"]
        self.headers = {"Authorization": f"Bearer {access}"}
        self.tenant_id = owner.tenant_id

    def __getattr__(self, method):
        fn = getattr(self.client, method)
        return lambda url, **kw: fn(url, headers=self.headers, **kw)


class TestRegressionMatrix(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        Base.metadata.create_all(bind=engine)
        cls.client = TestClient(app)

    def _resources(self, owner: _TenantClient) -> dict:
        """One of every tenant-owned resource type, created by the owner."""
        def ok(res):
            self.assertIn(res.status_code, (200, 201), res.text)
            return res.json()

        agent = ok(owner.post("/api/agents", json={"name": "Aria", "voice": "Aoede", "model": "gemini-2.0-flash-live-001",
                                                  "instructions": "Be kind.", "language": "en"}))
        return {
            "lead": ok(owner.post("/api/crm/leads", json={"name": "Owner lead", "phone": _phone()}))["id"],
            "appointment": ok(owner.post("/api/appointments", json=_slot(40)))["id"],
            "workflow": ok(owner.post("/api/crm/workflows", json={
                "name": "RT", "trigger_event": "lead_created", "is_active": False,
                "actions": [{"type": "create_reminder", "config": {"text": "call back"}}]}))["id"],
            "kb": ok(owner.post("/api/kb/sources", json={"source_type": "text", "title": "Prices", "raw_text": "Rooms cost 100."}))["source"]["id"],
            "page": ok(owner.post("/api/cms/pages", json={"title": "A", "slug": f"rt-{uuid.uuid4().hex[:8]}", "content": "a"}))["id"],
            "prompt": ok(owner.post("/api/cms/agent-prompts", json={"name": "Greeting", "content": "Hello"}))["id"],
            "faq": ok(owner.post("/api/cms/faqs", json={"question": "Q?", "answer": "A."}))["id"],
            "media": ok(owner.post("/api/cms/media/upload", files={"file": ("p.png", io.BytesIO(PNG), "image/png")}))["id"],
            "agent": agent["id"],
            "campaign": ok(owner.post("/api/crm/campaigns", json={"name": "RT", "leads": [{"phone": "9000000041", "name": "A"}]}))["id"],
        }

    # RT-01
    def test_other_tenant_gets_404_on_every_resource_by_id(self):
        owner, other = _TenantClient(self.client), _TenantClient(self.client)
        r = self._resources(owner)
        activity = {"activity_type": "note", "title": "x", "description": "x"}
        workflow = {"name": "x", "trigger_event": "lead_created", "actions": [{"type": "create_reminder", "config": {"text": "x"}}]}
        probes = [
            ("put", f"/api/crm/leads/{r['lead']}", {"name": "hijack"}),
            ("get", f"/api/crm/leads/{r['lead']}/timeline", None),
            ("post", f"/api/crm/leads/{r['lead']}/timeline", activity),
            ("delete", f"/api/crm/leads/{r['lead']}", None),
            ("patch", f"/api/appointments/{r['appointment']}", {"status": "cancelled"}),
            ("post", f"/api/appointments/{r['appointment']}/cancel", {}),
            ("put", f"/api/crm/workflows/{r['workflow']}", workflow),
            ("get", f"/api/crm/workflows/{r['workflow']}/runs", None),
            ("delete", f"/api/crm/workflows/{r['workflow']}", None),
            ("patch", f"/api/kb/sources/{r['kb']}", {"title": "hijack"}),
            ("post", f"/api/kb/sources/{r['kb']}/sync", {}),
            ("delete", f"/api/kb/sources/{r['kb']}", None),
            ("patch", f"/api/cms/pages/{r['page']}", {"title": "hijack"}),
            ("delete", f"/api/cms/pages/{r['page']}", None),
            ("patch", f"/api/cms/agent-prompts/{r['prompt']}", {"content": "hijack"}),
            ("delete", f"/api/cms/agent-prompts/{r['prompt']}", None),
            ("patch", f"/api/cms/faqs/{r['faq']}", {"answer": "hijack"}),
            ("delete", f"/api/cms/faqs/{r['faq']}", None),
            ("delete", f"/api/cms/media/{r['media']}", None),
            ("get", f"/api/agents/{r['agent']}", None),
            ("put", f"/api/agents/{r['agent']}", {"name": "hijack"}),
            ("get", f"/api/agents/{r['agent']}/versions", None),
            ("delete", f"/api/agents/{r['agent']}", None),
            ("get", f"/api/crm/campaigns/{r['campaign']}", None),
            ("get", f"/api/crm/campaigns/{r['campaign']}/export", None),
            ("post", f"/api/crm/campaigns/{r['campaign']}/start", None),
            ("post", f"/api/crm/campaigns/{r['campaign']}/pause", None),
            ("delete", f"/api/crm/campaigns/{r['campaign']}", None),
        ]
        # A mistyped URL would also answer 404, so every probe must hit a real route.
        routes = [(m.lower(), "^" + re.sub(r"\{[^}]+\}", "[^/]+", r.path) + "$") for r in app.routes for m in getattr(r, "methods", [])]
        missing = [f"{m} {u}" for m, u, _ in probes if not any(m == rm and re.match(rp, u) for rm, rp in routes)]
        self.assertEqual(missing, [], "probes without a route")
        wrong = []
        for method, url, body in probes:
            kw = {} if body is None else {"json": body}
            res = getattr(other, method)(url, **kw)
            if res.status_code != 404:
                wrong.append(f"{method.upper()} {url} -> {res.status_code}")
        self.assertEqual(wrong, [], "cross-tenant requests that were not refused with 404")
        # Nothing the other tenant tried changed or removed the owner's data.
        self.assertEqual(owner.get(f"/api/crm/leads/{r['lead']}/timeline").status_code, 200)
        self.assertEqual(owner.get(f"/api/agents/{r['agent']}").json()["name"], "Aria")
        self.assertEqual(owner.get(f"/api/crm/campaigns/{r['campaign']}").status_code, 200)
        self.assertIn(r["page"], [p["id"] for p in owner.get("/api/cms/pages").json()])

    # RT-02
    def test_lists_and_search_never_show_another_tenant(self):
        owner, other = _TenantClient(self.client), _TenantClient(self.client)
        r = self._resources(owner)
        owned = set(r.values())
        lists = {
            "/api/crm/leads": lambda b: b,
            "/api/appointments": lambda b: b,
            "/api/crm/workflows": lambda b: b,
            "/api/kb/sources": lambda b: b["items"],
            "/api/cms/pages": lambda b: b,
            "/api/cms/agent-prompts": lambda b: b,
            "/api/cms/faqs": lambda b: b,
            "/api/cms/media": lambda b: b,
            "/api/agents": lambda b: b,
            "/api/crm/campaigns": lambda b: b,
            "/api/logs": lambda b: b,
        }
        leaked = []
        for url, items in lists.items():
            res = other.get(url)
            self.assertEqual(res.status_code, 200, f"{url}: {res.text}")
            leaked += [f"{url}: {row['id']}" for row in items(res.json()) if row.get("id") in owned]
        self.assertEqual(leaked, [])
        search = other.post("/api/kb/search", json={"query": "Rooms cost"})
        self.assertNotIn("Rooms cost 100", search.text)

    # RT-03 and RT-04
    def test_role_matrix(self):
        owner = _TenantClient(self.client)
        members = {role: _Member(self.client, owner, role) for role in ROLES if role != "Owner"}
        members["Owner"] = owner
        lead_for_edit = owner.post("/api/crm/leads", json={"name": "Shared", "phone": _phone()}).json()["id"]
        counter = iter(range(100, 10_000))

        def evaluated_agent():
            agent = owner.post("/api/agents", json={"name": "M", "voice": "Aoede", "model": "gemini-2.0-flash-live-001",
                                                   "instructions": "x", "language": "en"}).json()
            for action in ("submit", "evaluate"):
                assert owner.post(f"/api/agents/{agent['id']}/versions/1/{action}", json={}).status_code == 200
            return agent["id"]

        # (name, lowest role allowed, request builder) — builders run once per role so writes don't collide.
        matrix = [
            ("read leads", "Viewer", lambda: ("get", "/api/crm/leads", None)),
            ("read call logs", "Viewer", lambda: ("get", "/api/logs", None)),
            ("create lead", "Agent", lambda: ("post", "/api/crm/leads", {"name": "N", "phone": _phone()})),
            ("edit lead", "Agent", lambda: ("put", f"/api/crm/leads/{lead_for_edit}", {"notes": "edited"})),
            ("delete lead", "Admin", lambda: ("delete", "/api/crm/leads/"
                                              + owner.post("/api/crm/leads", json={"name": "D", "phone": _phone()}).json()["id"], None)),
            ("book appointment", "Agent", lambda: ("post", "/api/appointments", _slot(next(counter)))),
            ("add knowledge", "Agent", lambda: ("post", "/api/kb/sources", {"source_type": "text", "title": "T", "raw_text": "t"})),
            ("create CMS page", "Agent", lambda: ("post", "/api/cms/pages", {"title": "P", "slug": f"m-{uuid.uuid4().hex[:8]}", "content": "c"})),
            ("create workflow", "Manager", lambda: ("post", "/api/crm/workflows", {
                "name": "W", "trigger_event": "lead_created", "is_active": False,
                "actions": [{"type": "create_reminder", "config": {"text": "x"}}]})),
            ("create campaign", "Manager", lambda: ("post", "/api/crm/campaigns", {"name": "C", "leads": [{"phone": "9000000042"}]})),
            ("create agent", "Manager", lambda: ("post", "/api/agents", {"name": "A", "voice": "Aoede", "model": "gemini-2.0-flash-live-001",
                                                                        "instructions": "x", "language": "en"})),
            ("approve version", "Admin", lambda: ("post", f"/api/agents/{evaluated_agent()}/versions/1/approve", {})),
            ("read runtime config", "Admin", lambda: ("get", "/api/config", None)),
            ("invite teammate", "Admin", lambda: ("post", "/api/team/invitations", {"email": f"x-{uuid.uuid4().hex[:8]}@example.com", "role": "Viewer"})),
        ]
        wrong = []
        with patch("app.routers.team.deliver", return_value="logged"):
            for name, lowest, build in matrix:
                for role in ROLES:
                    method, url, body = build()
                    kw = {} if body is None else {"json": body}
                    code = getattr(members[role], method)(url, **kw).status_code
                    allowed = ROLES.index(role) >= ROLES.index(lowest)
                    if (allowed and not 200 <= code < 300) or (not allowed and code != 403):
                        wrong.append(f"{name} as {role}: {code} (expected {'2xx' if allowed else 403})")
        self.assertEqual(wrong, [])

    # RT-05
    def test_forged_and_unsigned_tokens_are_rejected(self):
        owner = _TenantClient(self.client)
        claims = jwt.decode(owner.headers["Authorization"].split()[1], SECRET_KEY, algorithms=[ALGORITHM])

        def b64(part: dict) -> str:
            return base64.urlsafe_b64encode(json.dumps(part).encode()).rstrip(b"=").decode()

        forged = jwt.encode(claims, "not-the-server-secret-but-long-enough-for-hs256", algorithm=ALGORITHM)
        unsigned = f"{b64({'alg': 'none', 'typ': 'JWT'})}.{b64(claims)}."
        expired = jwt.encode(dict(claims, exp=int(time.time()) - 60), SECRET_KEY, algorithm=ALGORITHM)
        for token in (forged, unsigned, expired, "garbage"):
            res = self.client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
            self.assertEqual(res.status_code, 401, token[:20])
        self.assertEqual(owner.get("/api/auth/me").status_code, 200)

    # RT-09 (recordings; CMS media links are unguessable capability URLs by design)
    def test_recording_links_are_signed_short_lived_and_tenant_bound(self):
        owner, other = _TenantClient(self.client), _TenantClient(self.client)
        room = f"call-{uuid.uuid4().hex[:8]}"
        db = SessionLocal()
        try:
            db.add(CallLog(tenant_id=owner.tenant_id, phone_number="+919000000050", call_room_id=room, direction="inbound",
                           recording_url=f"/api/recordings/{room}.wav"))
            db.commit()
        finally:
            db.close()
        from app.routers import system
        with TemporaryDirectory() as tmp, patch.object(system, "RECORDINGS_DIR", Path(tmp)):
            Path(tmp, f"{room}.wav").write_bytes(b"RIFF0000WAVEfmt ")
            link = next(c["recording_url"] for c in owner.get("/api/inbound").json() if c["call_room_id"] == room)
            self.assertIn("sig=", link)
            # The audio element sends no token: the signed link alone is enough.
            played = self.client.get(link)
            self.assertEqual(played.status_code, 200)
            self.assertIn("no-store", played.headers["cache-control"])
            # A link signed for another workspace, a tampered signature and an expired link all fail.
            self.assertEqual(self.client.get(link.replace(owner.tenant_id, other.tenant_id)).status_code, 401)
            self.assertEqual(self.client.get(link[:-4] + "0000").status_code, 401)
            with patch.object(signed_urls.time, "time", return_value=time.time() + signed_urls.RECORDING_LINK_TTL + 5):
                self.assertEqual(self.client.get(link).status_code, 401)
            other_link = signed_urls.recording_link(other.tenant_id, f"{room}.wav")
            self.assertEqual(self.client.get(other_link).status_code, 404)
            self.assertEqual(self.client.get(f"/api/recordings/{room}.wav").status_code, 401)

    def test_bucket_recordings_redirect_to_short_lived_storage_links(self):
        owner, other = _TenantClient(self.client), _TenantClient(self.client)
        new_room, old_room = f"call-{uuid.uuid4().hex[:8]}", f"call-{uuid.uuid4().hex[:8]}"
        db = SessionLocal()
        try:
            db.add(CallLog(tenant_id=owner.tenant_id, phone_number="+919000000051", call_room_id=new_room, direction="outbound",
                           recording_url=f"{signed_urls.STORAGE_PREFIX}recordings/{new_room}.ogg"))
            # Rows from before the bucket went private hold its public URL.
            db.add(CallLog(tenant_id=owner.tenant_id, phone_number="+919000000052", call_room_id=old_room, direction="outbound",
                           recording_url=f"https://x.supabase.co/storage/v1/object/public/call-recordings/recordings/{old_room}.ogg"))
            db.commit()
        finally:
            db.close()
        calls = {c["call_room_id"]: c["recording_url"] for c in owner.get("/api/outbound").json()}
        storage = "https://x.supabase.co/storage/v1/object/sign/call-recordings/recordings/x.ogg?token=t"
        with patch.object(signed_urls, "storage_download_url", return_value=storage) as sign:
            for room in (new_room, old_room):
                link = calls[room]
                self.assertTrue(link.startswith(f"/api/recordings/{room}.ogg?"), link)
                res = self.client.get(link, follow_redirects=False)
                self.assertEqual(res.status_code, 302)
                self.assertEqual(res.headers["location"], storage)
                self.assertEqual(sign.call_args.args[0], f"recordings/{room}.ogg")
            # Another workspace can't mint a link for these files, and no link means no redirect.
            self.assertEqual(self.client.get(signed_urls.recording_link(other.tenant_id, f"{new_room}.ogg")).status_code, 404)
            self.assertEqual(self.client.get(f"/api/recordings/{new_room}.ogg", follow_redirects=False).status_code, 401)
        with patch.object(signed_urls, "storage_download_url", return_value=None):
            self.assertEqual(self.client.get(calls[new_room], follow_redirects=False).status_code, 404)

    # RT-12
    def test_overlapping_appointments_conflict(self):
        owner = _TenantClient(self.client)
        slot = _slot(60)
        self.assertEqual(owner.post("/api/appointments", json=slot).status_code, 201)
        start = datetime.strptime(slot["scheduled_start"], "%Y-%m-%dT%H:%M").replace(tzinfo=timezone.utc) + timedelta(minutes=15)
        overlapping = dict(slot, scheduled_start=start.strftime("%Y-%m-%dT%H:%M"),
                           scheduled_end=(start + timedelta(minutes=30)).strftime("%Y-%m-%dT%H:%M"))
        self.assertEqual(owner.post("/api/appointments", json=overlapping).status_code, 409)
        # Another workspace's calendar is separate.
        self.assertEqual(_TenantClient(self.client).post("/api/appointments", json=overlapping).status_code, 201)


if __name__ == "__main__":
    unittest.main()
