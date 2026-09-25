"""Google and Zoho calendar sync: connecting, pushing appointments, busy times and changes made in the calendar.
The provider classes run for real against an in-memory fake of each provider's HTTP API."""
import asyncio
import json
import os
import unittest
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

import httpx
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

import calendar_tools
import config_crypto
from app.core.database import Base, SessionLocal, engine
from app.main import app
from app.models.appointment import Appointment
from app.models.calendar import AppointmentCalendarEvent, CalendarConnection
from app.models.notification import Notification
from app.services import appointment_store, calendar_sync
from app.services import calendar_providers as cp
from app.tests.test_consolidation import _TenantClient
from app.tests.test_regression_matrix import _Member

ENV = {"GOOGLE_OAUTH_CLIENT_ID": "g-client", "GOOGLE_OAUTH_CLIENT_SECRET": "g-secret",
       "ZOHO_CLIENT_ID": "z-client", "ZOHO_CLIENT_SECRET": "z-secret",
       "SECRETS_ENCRYPTION_KEY": Fernet.generate_key().decode()}


class FakeGoogle:
    """Just enough of Google's OAuth and Calendar APIs."""
    def __init__(self):
        self.events: dict[str, dict] = {}
        self.busy: list[dict] = []
        self.requests: list[httpx.Request] = []
        self.expire_next = False  # answer the next API call with 401
        self.revoked = False
        self.refreshes = 0
        self.fail_writes = 0

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        url, method = request.url, request.method
        if url.host == "oauth2.googleapis.com" and url.path == "/token":
            form = parse_qs(request.content.decode())
            if form["grant_type"] == ["refresh_token"]:
                if self.revoked:
                    return httpx.Response(400, json={"error": "invalid_grant"})
                self.refreshes += 1
                return httpx.Response(200, json={"access_token": f"access-{self.refreshes}", "expires_in": 3600})
            assert form["code"] == ["good-code"], form
            return httpx.Response(200, json={"access_token": "access-0", "refresh_token": "refresh-secret", "expires_in": 3600})
        if url.path == "/revoke":
            return httpx.Response(200)
        if url.host == "openidconnect.googleapis.com":
            return httpx.Response(200, json={"email": "owner@gmail.com"})
        if self.expire_next:
            self.expire_next = False
            return httpx.Response(401, json={"error": {"message": "expired"}})
        if url.path.endswith("/freeBusy"):
            return httpx.Response(200, json={"calendars": {"primary": {"busy": self.busy}}})
        parts = url.path.split("/events")
        if method in ("POST", "PATCH") and self.fail_writes:
            self.fail_writes -= 1
            return httpx.Response(503, json={"error": {"message": "backend error"}})
        if method == "POST":
            body = json.loads(request.content)
            event_id = uuid.uuid4().hex
            self.events[event_id] = {**body, "id": event_id, "status": "confirmed", "etag": "e1"}
            return httpx.Response(200, json=self.events[event_id])
        event_id = parts[1].strip("/")
        event = self.events.get(event_id)
        if event is None:
            return httpx.Response(404, json={"error": {"message": "not found"}})
        if method == "PATCH":
            event.update(json.loads(request.content))
            event["etag"] = "e2"
            return httpx.Response(200, json=event)
        if method == "DELETE":
            del self.events[event_id]
            return httpx.Response(204)
        return httpx.Response(200, json=event)


def _slot(days: int, hour: int = 11) -> tuple[str, str]:
    day = (datetime.now(timezone.utc) + timedelta(days=days)).date()
    start = datetime(day.year, day.month, day.day, hour, 0, tzinfo=timezone.utc)
    return start.isoformat(), (start + timedelta(minutes=30)).isoformat()


class CalendarTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        Base.metadata.create_all(bind=engine)
        cls.client = TestClient(app)

    def setUp(self):
        self.fake = FakeGoogle()
        patches = [patch.dict(os.environ, ENV),
                   patch.object(cp, "http", lambda timeout=cp.TIMEOUT: httpx.Client(transport=httpx.MockTransport(self.fake)))]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        calendar_sync._busy_cache.clear()

    def connect_google(self, owner: _TenantClient) -> None:
        url = owner.post("/api/integrations/calendar/google/connect").json()["url"]
        state = parse_qs(urlparse(url).query)["state"][0]
        res = self.client.get("/api/integrations/calendar/google/callback", params={"code": "good-code", "state": state},
                              follow_redirects=False)
        self.assertEqual(res.status_code, 302)
        self.assertIn("result=connected", res.headers["location"])

    def book(self, owner: _TenantClient, days: int, hour: int = 11, **extra) -> dict:
        start, end = _slot(days, hour)
        res = owner.post("/api/appointments", json={"contact_name": "Asha", "contact_phone": "+919876500000",
                                                   "timezone": "UTC", "scheduled_start": start[:16],
                                                   "scheduled_end": end[:16], **extra})
        self.assertEqual(res.status_code, 201, res.text)
        return res.json()


class TestConnecting(CalendarTestCase):
    def test_admin_connects_and_tokens_are_encrypted(self):
        owner = _TenantClient(self.client)
        agent = _Member(self.client, owner, "Agent")
        self.assertEqual(agent.post("/api/integrations/calendar/google/connect").status_code, 403)
        url = owner.post("/api/integrations/calendar/google/connect").json()["url"]
        query = parse_qs(urlparse(url).query)
        self.assertEqual((query["client_id"], query["access_type"], query["prompt"]), (["g-client"], ["offline"], ["consent"]))
        self.assertTrue(query["redirect_uri"][0].endswith("/api/integrations/calendar/google/callback"))

        self.connect_google(owner)
        status = {s["provider"]: s for s in owner.get("/api/integrations/calendar").json()}
        self.assertTrue(status["google"]["connected"])
        self.assertEqual(status["google"]["account_email"], "owner@gmail.com")
        self.assertFalse(status["zoho"]["connected"])
        db = SessionLocal()
        try:
            conn = db.query(CalendarConnection).filter(CalendarConnection.tenant_id == owner.tenant_id).one()
            self.assertTrue(config_crypto.is_encrypted(conn.refresh_token))
            self.assertEqual(config_crypto.decrypt(conn.refresh_token), "refresh-secret")
        finally:
            db.close()
        # Status never includes tokens.
        self.assertNotIn("refresh", json.dumps(owner.get("/api/integrations/calendar").json()).replace("refresh_", ""))

    def test_bad_or_foreign_state_is_refused(self):
        owner = _TenantClient(self.client)
        url = owner.post("/api/integrations/calendar/google/connect").json()["url"]
        state = parse_qs(urlparse(url).query)["state"][0]
        for params in ({"code": "good-code", "state": state[:-2] + "00"},
                       {"code": "good-code", "state": "garbage"}):
            res = self.client.get("/api/integrations/calendar/google/callback", params=params, follow_redirects=False)
            self.assertIn("result=error", res.headers["location"])
        # A Google state can't complete a Zoho connection.
        res = self.client.get("/api/integrations/calendar/zoho/callback", params={"code": "x", "state": state}, follow_redirects=False)
        self.assertIn("result=error", res.headers["location"])
        denied = self.client.get("/api/integrations/calendar/google/callback", params={"error": "access_denied", "state": state},
                                 follow_redirects=False)
        self.assertIn("result=error", denied.headers["location"])
        self.assertFalse(any(s["connected"] for s in owner.get("/api/integrations/calendar").json()))

    def test_unconfigured_provider_and_other_tenants(self):
        owner, other = _TenantClient(self.client), _TenantClient(self.client)
        with patch.dict(os.environ, {"ZOHO_CLIENT_ID": ""}):
            res = owner.post("/api/integrations/calendar/zoho/connect")
            self.assertEqual(res.status_code, 503)
            self.assertIn("ZOHO_CLIENT_ID", res.json()["detail"])
        self.connect_google(owner)
        self.assertFalse(any(s["connected"] for s in other.get("/api/integrations/calendar").json()))
        self.assertEqual(other.delete("/api/integrations/calendar/google").status_code, 404)
        self.assertEqual(other.post("/api/integrations/calendar/google/sync").status_code, 404)
        self.assertEqual(owner.post("/api/integrations/calendar/outlook/connect").status_code, 404)

    def test_disconnect_revokes_and_stops_syncing(self):
        owner = _TenantClient(self.client)
        self.connect_google(owner)
        self.book(owner, 5)
        self.assertEqual(owner.delete("/api/integrations/calendar/google").status_code, 204)
        self.assertTrue(any(r.url.path == "/revoke" for r in self.fake.requests))
        db = SessionLocal()
        try:
            self.assertEqual(db.query(AppointmentCalendarEvent).join(Appointment).filter(
                Appointment.tenant_id == owner.tenant_id).count(), 0)
        finally:
            db.close()


class TestPushAndPull(CalendarTestCase):
    def test_appointments_are_created_moved_and_removed_in_the_calendar(self):
        owner = _TenantClient(self.client)
        earlier = self.book(owner, 4)  # booked before connecting: back-filled
        self.connect_google(owner)
        apt = self.book(owner, 6, notes="Wants a window seat")
        calendar_sync.push_pending(owner.tenant_id)
        by_apt = {e["extendedProperties"]["private"]["avn_appointment_id"]: e for e in self.fake.events.values()}
        self.assertEqual(set(by_apt), {earlier["id"], apt["id"]})
        event = by_apt[apt["id"]]
        self.assertEqual(event["summary"], "Appointment: Asha")
        self.assertIn("+919876500000", event["description"])
        self.assertIn("window seat", event["description"])
        self.assertEqual(event["start"]["dateTime"], apt["scheduled_start"])

        start, end = _slot(6, 13)
        self.assertEqual(owner.patch(f"/api/appointments/{apt['id']}", json={"scheduled_start": start[:16], "scheduled_end": end[:16]}).status_code, 200)
        calendar_sync.push_pending(owner.tenant_id)
        self.assertEqual(self.fake.events[event["id"]]["start"]["dateTime"], start)

        self.assertEqual(owner.post(f"/api/appointments/{apt['id']}/cancel", json={"reason": "ill"}).status_code, 200)
        calendar_sync.push_pending(owner.tenant_id)
        self.assertNotIn(event["id"], self.fake.events)
        status = {s["provider"]: s for s in owner.get("/api/integrations/calendar").json()}["google"]
        self.assertEqual((status["pending"], status["failed"]), (0, 0))
        self.assertIsNotNone(status["last_synced_at"])

    def test_expired_access_token_is_refreshed_once(self):
        owner = _TenantClient(self.client)
        self.connect_google(owner)
        self.fake.expire_next = True
        self.book(owner, 7)
        self.assertEqual(calendar_sync.push_pending(owner.tenant_id), 1)
        self.assertEqual(self.fake.refreshes, 1)
        self.assertEqual(len(self.fake.events), 1)

    def test_failures_retry_then_stop_and_sync_now_retries(self):
        owner = _TenantClient(self.client)
        self.connect_google(owner)
        self.book(owner, 8)
        self.fake.fail_writes = calendar_sync.MAX_ATTEMPTS
        for _ in range(calendar_sync.MAX_ATTEMPTS):
            db = SessionLocal()
            db.query(AppointmentCalendarEvent).filter(AppointmentCalendarEvent.tenant_id == owner.tenant_id).update(
                {"next_attempt_at": None})
            db.commit()
            db.close()
            calendar_sync.push_pending(owner.tenant_id)
        status = {s["provider"]: s for s in owner.get("/api/integrations/calendar").json()}["google"]
        self.assertEqual(status["failed"], 1)
        res = owner.post("/api/integrations/calendar/google/sync")
        self.assertEqual(res.status_code, 200, res.text)
        self.assertEqual(res.json()["pushed"], 1)
        self.assertEqual(len(self.fake.events), 1)

    def test_revoked_access_asks_for_reconnect(self):
        owner = _TenantClient(self.client)
        self.connect_google(owner)
        db = SessionLocal()
        db.query(CalendarConnection).filter(CalendarConnection.tenant_id == owner.tenant_id).update({"access_expires_at": None})
        db.commit()
        db.close()
        self.fake.revoked = True
        self.book(owner, 9)
        calendar_sync.push_pending(owner.tenant_id)
        status = {s["provider"]: s for s in owner.get("/api/integrations/calendar").json()}["google"]
        self.assertEqual(status["status"], "error")
        self.assertIn("Connect the calendar again", status["last_error"])
        self.assertEqual(status["pending"], 1)  # kept for after reconnecting
        self.assertEqual(owner.post("/api/integrations/calendar/google/sync").status_code, 409)
        self.fake.revoked = False
        self.connect_google(owner)
        calendar_sync.push_pending(owner.tenant_id)
        self.assertEqual(len(self.fake.events), 1)

    def test_moves_and_deletions_in_the_calendar_come_back(self):
        owner = _TenantClient(self.client)
        self.connect_google(owner)
        moved, deleted = self.book(owner, 10), self.book(owner, 10, hour=14)
        calendar_sync.push_pending(owner.tenant_id)
        by_apt = {e["extendedProperties"]["private"]["avn_appointment_id"]: e for e in self.fake.events.values()}
        new_start, new_end = _slot(11, 12)
        by_apt[moved["id"]]["start"] = {"dateTime": new_start.replace("+00:00", "Z")}
        by_apt[moved["id"]]["end"] = {"dateTime": new_end.replace("+00:00", "Z")}
        by_apt[deleted["id"]]["status"] = "cancelled"
        self.assertEqual(calendar_sync.pull_changes(owner.tenant_id), 2)
        rows = {a["id"]: a for a in owner.get("/api/appointments").json()}
        self.assertEqual((rows[moved["id"]]["scheduled_start"], rows[moved["id"]]["status"]), (new_start, "scheduled"))
        self.assertEqual(rows[deleted["id"]]["status"], "cancelled")
        self.assertIn("Cancelled in Google Calendar", rows[deleted["id"]]["notes"])
        db = SessionLocal()
        try:
            kinds = [n.title for n in db.query(Notification).filter(Notification.tenant_id == owner.tenant_id,
                                                                    Notification.kind == "appointment_changed")]
        finally:
            db.close()
        self.assertEqual(len(kinds), 2)
        # A second pass finds nothing new.
        self.assertEqual(calendar_sync.pull_changes(owner.tenant_id), 0)


class TestBusyTimes(CalendarTestCase):
    def test_busy_calendar_time_blocks_bookings_and_slots(self):
        owner = _TenantClient(self.client)
        self.connect_google(owner)
        # Next Monday 12:00-13:00 IST is busy in Google Calendar.
        today = datetime.now(timezone.utc).date()
        monday = today + timedelta(days=(7 - today.weekday()) or 7)
        busy_start = datetime(monday.year, monday.month, monday.day, 6, 30, tzinfo=timezone.utc)
        self.fake.busy = [{"start": busy_start.isoformat().replace("+00:00", "Z"),
                           "end": (busy_start + timedelta(hours=1)).isoformat().replace("+00:00", "Z")}]
        clash = {"contact_name": "B", "contact_phone": "+919876500001", "timezone": "Asia/Kolkata",
                 "scheduled_start": f"{monday}T12:30", "scheduled_end": f"{monday}T13:00"}
        res = owner.post("/api/appointments", json=clash)
        self.assertEqual(res.status_code, 409)
        self.assertIn("connected calendar", res.json()["detail"])
        with self.assertRaises(appointment_store.AppointmentConflict):
            appointment_store.book(owner.tenant_id, contact_name="C", contact_phone="+919876500002",
                                   start=f"{monday}T12:00", end=f"{monday}T12:30", tz_name="Asia/Kolkata")
        slots = asyncio.run(calendar_tools.get_available_slots(str(monday), tenant_id=owner.tenant_id))
        labels = [s["label"] for s in slots]
        self.assertNotIn("12:00 PM", labels)
        self.assertNotIn("12:30 PM", labels)
        self.assertIn("1:00 PM", labels)
        # The free slot right after still books.
        ok = dict(clash, scheduled_start=f"{monday}T13:00", scheduled_end=f"{monday}T13:30")
        self.assertEqual(owner.post("/api/appointments", json=ok).status_code, 201)

    def test_unreachable_calendar_does_not_stop_bookings(self):
        owner = _TenantClient(self.client)
        self.connect_google(owner)
        with patch.object(cp.GoogleCalendar, "busy", side_effect=httpx.ConnectTimeout("down")):
            self.book(owner, 12)

    def test_moving_within_its_own_slot_is_not_blocked_by_its_own_event(self):
        owner = _TenantClient(self.client)
        self.connect_google(owner)
        apt = self.book(owner, 13)
        self.fake.busy = [{"start": apt["scheduled_start"], "end": apt["scheduled_end"]}]
        later = (datetime.fromisoformat(apt["scheduled_start"]) + timedelta(minutes=15)).strftime("%Y-%m-%dT%H:%M")
        later_end = (datetime.fromisoformat(apt["scheduled_end"]) + timedelta(minutes=15)).strftime("%Y-%m-%dT%H:%M")
        res = owner.patch(f"/api/appointments/{apt['id']}", json={"scheduled_start": later, "scheduled_end": later_end})
        self.assertEqual(res.status_code, 200, res.text)
        # Other busy time still counts.
        calendar_sync._busy_cache.clear()
        self.fake.busy.append({"start": later_end[:16] + ":00+00:00", "end": (datetime.fromisoformat(apt["scheduled_end"]) + timedelta(hours=1)).isoformat()})
        res = owner.patch(f"/api/appointments/{apt['id']}", json={"scheduled_start": apt["scheduled_start"][:16],
                                                                 "scheduled_end": (datetime.fromisoformat(later_end) + timedelta(minutes=15)).strftime("%Y-%m-%dT%H:%M")})
        self.assertEqual(res.status_code, 409)


class TestZoho(unittest.TestCase):
    """Zoho request and response formats, against a fake Zoho API."""

    def setUp(self):
        self.seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            self.seen.append(request)
            path = request.url.path
            if path == "/oauth/v2/token":
                return httpx.Response(200, json={"access_token": "z-access", "refresh_token": "z-refresh", "expires_in": 3600})
            if path == "/oauth/user/info":
                return httpx.Response(200, json={"Email": "owner@zoho.in"})
            if path == "/api/v1/calendars":
                return httpx.Response(200, json={"calendars": [{"uid": "other"}, {"uid": "cal-1", "isdefault": True}]})
            if path == "/api/v1/calendars/freebusy":
                return httpx.Response(200, json={"fb": [{"startTime": "20261005T063000Z", "endTime": "20261005T073000Z", "fbtype": "busy"},
                                                        {"startTime": "20261005T090000Z", "endTime": "20261005T100000Z", "fbtype": "free"}]})
            if request.method == "POST":
                return httpx.Response(200, json={"events": [{"uid": "ev-1", "etag": 111}]})
            if request.method == "GET":
                return httpx.Response(200, json={"events": [{"uid": "ev-1", "etag": 112, "dateandtime": {
                    "timezone": "Asia/Kolkata", "start": "20261005T140000+0530", "end": "20261005T143000+0530"}}]})
            return httpx.Response(200, json={"events": [{"uid": "ev-1", "etag": 113}]})

        p = patch.object(cp, "http", lambda timeout=cp.TIMEOUT: httpx.Client(transport=httpx.MockTransport(handler)))
        p.start()
        self.addCleanup(p.stop)
        env = patch.dict(os.environ, ENV)
        env.start()
        self.addCleanup(env.stop)
        self.zoho = cp.PROVIDERS["zoho"]

    def test_connect_uses_the_accounts_data_centre_only_when_trusted(self):
        account = self.zoho.connect("code", "https://api.example.com/cb", {"accounts-server": "https://accounts.zoho.eu"})
        self.assertEqual((account.accounts_url, account.calendar_id, account.email), ("https://accounts.zoho.eu", "cal-1", "owner@zoho.in"))
        self.assertEqual(self.seen[0].url.host, "accounts.zoho.eu")
        self.assertIn("calendar.zoho.eu", {r.url.host for r in self.seen})
        self.seen.clear()
        account = self.zoho.connect("code", "https://api.example.com/cb", {"accounts-server": "https://evil.example.com"})
        self.assertEqual(account.accounts_url, "https://accounts.zoho.in")
        self.assertNotIn("evil.example.com", {r.url.host for r in self.seen})

    def test_events_and_busy_times(self):
        apt = cp.AppointmentData(id="a1", tenant_id="t1", title="Appointment", contact_name="Asha", contact_phone="+91",
                                 start="2026-10-05T04:00:00+00:00", end="2026-10-05T04:30:00+00:00", timezone="Asia/Kolkata")
        ref = self.zoho.create_event("tok", "cal-1", apt, "https://accounts.zoho.in")
        self.assertEqual((ref.external_id, ref.etag), ("ev-1", "111"))
        sent = json.loads(parse_qs(self.seen[-1].url.query.decode())["eventdata"][0])
        self.assertEqual(sent["dateandtime"], {"timezone": "Asia/Kolkata", "start": "20261005T093000+0530", "end": "20261005T100000+0530"})
        self.assertEqual(self.seen[-1].headers["authorization"], "Zoho-oauthtoken tok")
        self.zoho.update_event("tok", "cal-1", ref, apt, None)
        self.assertEqual(json.loads(parse_qs(self.seen[-1].url.query.decode())["eventdata"][0])["etag"], "111")
        remote = self.zoho.get_event("tok", "cal-1", ref, None)
        self.assertEqual((remote.start, remote.end), ("2026-10-05T08:30:00+00:00", "2026-10-05T09:00:00+00:00"))
        busy = self.zoho.busy("tok", "cal-1", "owner@zoho.in", "2026-10-05T00:00:00+00:00", "2026-10-06T00:00:00+00:00", None)
        self.assertEqual(busy, [("2026-10-05T06:30:00+00:00", "2026-10-05T07:30:00+00:00")])
        self.assertEqual(parse_qs(self.seen[-1].url.query.decode())["sdate"], ["20261005T000000Z"])


if __name__ == "__main__":
    unittest.main()
