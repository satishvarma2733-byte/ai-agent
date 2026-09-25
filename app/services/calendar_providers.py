"""Google Calendar and Zoho Calendar behind one interface: OAuth, events, and busy times.

Every call takes an access token; refreshing it and retrying lives in calendar_sync. Times cross this
boundary as UTC ISO strings ("2026-10-01T04:00:00+00:00"), the format appointments are stored in.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from urllib.parse import quote, urlencode, urlparse
from zoneinfo import ZoneInfo

import httpx

TIMEOUT = 10
# Busy times are read while a caller waits on the line, so they get less time before we carry on without them.
BUSY_TIMEOUT = 4


class CalendarApiError(Exception):
    def __init__(self, message: str, status: int = 0):
        super().__init__(message)
        self.status = status

    @property
    def unauthorized(self) -> bool:
        return self.status == 401


class ReconnectRequired(CalendarApiError):
    """The refresh token was revoked or expired: an admin has to connect the calendar again."""


@dataclass
class Tokens:
    access_token: str
    expires_in: int
    refresh_token: str | None = None


@dataclass
class Account:
    tokens: Tokens
    email: str | None
    calendar_id: str
    accounts_url: str | None = None


@dataclass
class EventRef:
    external_id: str
    etag: str | None = None


@dataclass
class RemoteEvent:
    start: str | None
    end: str | None
    cancelled: bool = False
    etag: str | None = None


@dataclass
class AppointmentData:
    id: str
    tenant_id: str
    title: str
    contact_name: str
    contact_phone: str
    start: str
    end: str
    timezone: str
    notes: str = ""
    extra: dict = field(default_factory=dict)

    @property
    def summary(self) -> str:
        return f"{self.title}: {self.contact_name}" if self.title and self.title != self.contact_name else self.contact_name

    @property
    def description(self) -> str:
        lines = [f"Phone: {self.contact_phone}"]
        if self.notes:
            lines += ["", self.notes.strip()]
        lines += ["", "Booked in aVn. Moving or deleting this event updates the appointment."]
        return "\n".join(lines)


def http(timeout: float = TIMEOUT) -> httpx.Client:
    """One client per call; tests replace this to intercept requests."""
    return httpx.Client(timeout=timeout)


def _utc_iso(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).replace(microsecond=0).isoformat()


def _raise_for(res: httpx.Response, what: str) -> None:
    if res.status_code >= 400:
        detail = res.text[:300]
        try:
            body = res.json()
            detail = body.get("error_description") or body.get("error", {}).get("message") or body.get("error") or detail
        except Exception:
            pass
        raise CalendarApiError(f"{what} failed ({res.status_code}): {detail}", res.status_code)


class Provider:
    name = ""
    label = ""
    client_id_env = ""
    client_secret_env = ""

    @property
    def client_id(self) -> str:
        return os.environ.get(self.client_id_env, "").strip()

    @property
    def client_secret(self) -> str:
        return os.environ.get(self.client_secret_env, "").strip()

    def configured(self) -> bool:
        return bool(self.client_id and self.client_secret)

    # Implemented per provider.
    def auth_url(self, state: str, redirect_uri: str) -> str: ...
    def connect(self, code: str, redirect_uri: str, params: dict) -> Account: ...
    def refresh(self, refresh_token: str, accounts_url: str | None) -> Tokens: ...
    def create_event(self, token: str, calendar_id: str, apt: AppointmentData, accounts_url: str | None) -> EventRef: ...
    def update_event(self, token: str, calendar_id: str, ref: EventRef, apt: AppointmentData, accounts_url: str | None) -> EventRef: ...
    def delete_event(self, token: str, calendar_id: str, ref: EventRef, accounts_url: str | None) -> None: ...
    def get_event(self, token: str, calendar_id: str, ref: EventRef, accounts_url: str | None) -> RemoteEvent: ...
    def busy(self, token: str, calendar_id: str, account_email: str | None, start: str, end: str,
             accounts_url: str | None) -> list[tuple[str, str]]: ...


class GoogleCalendar(Provider):
    name = "google"
    label = "Google Calendar"
    client_id_env = "GOOGLE_OAUTH_CLIENT_ID"
    client_secret_env = "GOOGLE_OAUTH_CLIENT_SECRET"
    AUTH = "https://accounts.google.com/o/oauth2/v2/auth"
    TOKEN = "https://oauth2.googleapis.com/token"
    USERINFO = "https://openidconnect.googleapis.com/v1/userinfo"
    API = "https://www.googleapis.com/calendar/v3"
    SCOPES = ("openid email https://www.googleapis.com/auth/calendar.events "
              "https://www.googleapis.com/auth/calendar.freebusy")

    def auth_url(self, state: str, redirect_uri: str) -> str:
        return self.AUTH + "?" + urlencode({
            "client_id": self.client_id, "redirect_uri": redirect_uri, "response_type": "code",
            "scope": self.SCOPES, "access_type": "offline", "prompt": "consent", "include_granted_scopes": "true",
            "state": state,
        })

    def _tokens(self, data: dict) -> dict:
        with http() as client:
            res = client.post(self.TOKEN, data={**data, "client_id": self.client_id, "client_secret": self.client_secret})
        if res.status_code == 400 and "invalid_grant" in res.text:
            raise ReconnectRequired("Google no longer accepts this connection. Connect the calendar again.", 400)
        _raise_for(res, "Google sign-in")
        return res.json()

    def connect(self, code: str, redirect_uri: str, params: dict) -> Account:
        body = self._tokens({"grant_type": "authorization_code", "code": code, "redirect_uri": redirect_uri})
        if not body.get("refresh_token"):
            raise CalendarApiError("Google didn't grant offline access. Remove aVn from your Google account's "
                                   "third-party access and connect again.")
        tokens = Tokens(body["access_token"], int(body.get("expires_in", 3600)), body["refresh_token"])
        with http() as client:
            info = client.get(self.USERINFO, headers={"Authorization": f"Bearer {tokens.access_token}"})
        email = info.json().get("email") if info.status_code == 200 else None
        return Account(tokens=tokens, email=email, calendar_id="primary")

    def refresh(self, refresh_token: str, accounts_url: str | None) -> Tokens:
        body = self._tokens({"grant_type": "refresh_token", "refresh_token": refresh_token})
        return Tokens(body["access_token"], int(body.get("expires_in", 3600)), body.get("refresh_token"))

    def _event_body(self, apt: AppointmentData) -> dict:
        return {
            "summary": apt.summary,
            "description": apt.description,
            "start": {"dateTime": apt.start, "timeZone": apt.timezone},
            "end": {"dateTime": apt.end, "timeZone": apt.timezone},
            "extendedProperties": {"private": {"avn_appointment_id": apt.id, "avn_tenant_id": apt.tenant_id}},
        }

    def _events_url(self, calendar_id: str) -> str:
        return f"{self.API}/calendars/{quote(calendar_id, safe='')}/events"

    def create_event(self, token, calendar_id, apt, accounts_url=None) -> EventRef:
        with http() as client:
            res = client.post(self._events_url(calendar_id), json=self._event_body(apt), headers=_bearer(token))
        _raise_for(res, "Creating the Google Calendar event")
        body = res.json()
        return EventRef(body["id"], body.get("etag"))

    def update_event(self, token, calendar_id, ref, apt, accounts_url=None) -> EventRef:
        body = {**self._event_body(apt), "status": "confirmed"}
        with http() as client:
            res = client.patch(f"{self._events_url(calendar_id)}/{ref.external_id}", json=body, headers=_bearer(token))
        if res.status_code in (404, 410):
            return self.create_event(token, calendar_id, apt)
        _raise_for(res, "Updating the Google Calendar event")
        return EventRef(ref.external_id, res.json().get("etag"))

    def delete_event(self, token, calendar_id, ref, accounts_url=None) -> None:
        with http() as client:
            res = client.delete(f"{self._events_url(calendar_id)}/{ref.external_id}", headers=_bearer(token))
        if res.status_code in (404, 410):
            return
        _raise_for(res, "Deleting the Google Calendar event")

    def get_event(self, token, calendar_id, ref, accounts_url=None) -> RemoteEvent:
        with http() as client:
            res = client.get(f"{self._events_url(calendar_id)}/{ref.external_id}", headers=_bearer(token))
        if res.status_code in (404, 410):
            return RemoteEvent(None, None, cancelled=True)
        _raise_for(res, "Reading the Google Calendar event")
        body = res.json()
        if body.get("status") == "cancelled":
            return RemoteEvent(None, None, cancelled=True, etag=body.get("etag"))
        return RemoteEvent(_google_time(body.get("start")), _google_time(body.get("end")), etag=body.get("etag"))

    def busy(self, token, calendar_id, account_email, start, end, accounts_url=None) -> list[tuple[str, str]]:
        with http(BUSY_TIMEOUT) as client:
            res = client.post(f"{self.API}/freeBusy", headers=_bearer(token),
                              json={"timeMin": start, "timeMax": end, "items": [{"id": calendar_id}]})
        _raise_for(res, "Reading Google Calendar busy times")
        periods = res.json().get("calendars", {}).get(calendar_id, {}).get("busy", [])
        return [(_utc_iso(_parse(p["start"])), _utc_iso(_parse(p["end"]))) for p in periods]


# Zoho runs separate data centres; only these accounts servers are trusted in the OAuth callback.
ZOHO_ACCOUNTS_HOSTS = {"accounts.zoho.com", "accounts.zoho.eu", "accounts.zoho.in", "accounts.zoho.com.au",
                       "accounts.zoho.jp", "accounts.zoho.ca", "accounts.zoho.sa", "accounts.zohocloud.ca"}


class ZohoCalendar(Provider):
    name = "zoho"
    label = "Zoho Calendar"
    client_id_env = "ZOHO_CLIENT_ID"
    client_secret_env = "ZOHO_CLIENT_SECRET"
    SCOPES = "ZohoCalendar.calendar.ALL,ZohoCalendar.event.ALL,ZohoCalendar.freebusy.READ,AaaServer.profile.Read"

    @property
    def default_accounts_url(self) -> str:
        return os.environ.get("ZOHO_ACCOUNTS_URL", "https://accounts.zoho.in").rstrip("/")

    @staticmethod
    def trusted_accounts_url(url: str | None) -> str | None:
        parsed = urlparse(url or "")
        if parsed.scheme == "https" and parsed.hostname in ZOHO_ACCOUNTS_HOSTS and not parsed.path.strip("/"):
            return f"https://{parsed.hostname}"
        return None

    @staticmethod
    def _api(accounts_url: str | None) -> str:
        host = urlparse(accounts_url or "https://accounts.zoho.in").hostname or "accounts.zoho.in"
        return f"https://{host.replace('accounts.', 'calendar.', 1)}/api/v1"

    def auth_url(self, state: str, redirect_uri: str) -> str:
        return f"{self.default_accounts_url}/oauth/v2/auth?" + urlencode({
            "client_id": self.client_id, "redirect_uri": redirect_uri, "response_type": "code",
            "scope": self.SCOPES, "access_type": "offline", "prompt": "consent", "state": state,
        })

    def _tokens(self, accounts_url: str, data: dict) -> dict:
        with http() as client:
            res = client.post(f"{accounts_url}/oauth/v2/token",
                              data={**data, "client_id": self.client_id, "client_secret": self.client_secret})
        body = res.json() if res.headers.get("content-type", "").startswith("application/json") else {}
        # Zoho reports token errors with HTTP 200 and an "error" field.
        if body.get("error") == "invalid_code" or (data.get("grant_type") == "refresh_token" and body.get("error")):
            raise ReconnectRequired("Zoho no longer accepts this connection. Connect the calendar again.", 400)
        if res.status_code >= 400 or body.get("error") or "access_token" not in body:
            raise CalendarApiError(f"Zoho sign-in failed: {body.get('error') or res.text[:200]}", res.status_code)
        return body

    def connect(self, code: str, redirect_uri: str, params: dict) -> Account:
        accounts_url = self.trusted_accounts_url(params.get("accounts-server")) or self.default_accounts_url
        body = self._tokens(accounts_url, {"grant_type": "authorization_code", "code": code, "redirect_uri": redirect_uri})
        if not body.get("refresh_token"):
            raise CalendarApiError("Zoho didn't grant offline access. Connect the calendar again.")
        tokens = Tokens(body["access_token"], int(body.get("expires_in", 3600)), body["refresh_token"])
        headers = _zoho(tokens.access_token)
        with http() as client:
            info = client.get(f"{accounts_url}/oauth/user/info", headers=headers)
            calendars = client.get(f"{self._api(accounts_url)}/calendars", params={"category": "own"}, headers=headers)
        _raise_for(calendars, "Reading your Zoho calendars")
        own = calendars.json().get("calendars", [])
        default = next((c for c in own if c.get("isdefault")), own[0] if own else None)
        if not default or not default.get("uid"):
            raise CalendarApiError("This Zoho account has no calendar to add appointments to.")
        email = info.json().get("Email") if info.status_code == 200 else None
        return Account(tokens=tokens, email=email, calendar_id=default["uid"], accounts_url=accounts_url)

    def refresh(self, refresh_token: str, accounts_url: str | None) -> Tokens:
        body = self._tokens(accounts_url or self.default_accounts_url,
                            {"grant_type": "refresh_token", "refresh_token": refresh_token})
        return Tokens(body["access_token"], int(body.get("expires_in", 3600)))

    @staticmethod
    def _eventdata(apt: AppointmentData, etag: str | None = None) -> str:
        tz = ZoneInfo(apt.timezone or "Asia/Kolkata")
        data = {
            "title": apt.summary,
            "description": apt.description,
            "dateandtime": {"timezone": apt.timezone, "start": _zoho_time(apt.start, tz), "end": _zoho_time(apt.end, tz)},
        }
        if etag:
            data["etag"] = etag
        return json.dumps(data)

    def create_event(self, token, calendar_id, apt, accounts_url=None) -> EventRef:
        with http() as client:
            res = client.post(f"{self._api(accounts_url)}/calendars/{calendar_id}/events",
                              params={"eventdata": self._eventdata(apt)}, headers=_zoho(token))
        _raise_for(res, "Creating the Zoho Calendar event")
        event = (res.json().get("events") or [{}])[0]
        if not event.get("uid"):
            raise CalendarApiError("Zoho did not return the new event.")
        return EventRef(event["uid"], str(event.get("etag") or ""))

    def update_event(self, token, calendar_id, ref, apt, accounts_url=None) -> EventRef:
        with http() as client:
            res = client.put(f"{self._api(accounts_url)}/calendars/{calendar_id}/events/{ref.external_id}",
                             params={"eventdata": self._eventdata(apt, ref.etag)}, headers=_zoho(token))
        if res.status_code == 404:
            return self.create_event(token, calendar_id, apt, accounts_url)
        _raise_for(res, "Updating the Zoho Calendar event")
        event = (res.json().get("events") or [{}])[0]
        return EventRef(ref.external_id, str(event.get("etag") or ref.etag or ""))

    def delete_event(self, token, calendar_id, ref, accounts_url=None) -> None:
        with http() as client:
            res = client.delete(f"{self._api(accounts_url)}/calendars/{calendar_id}/events/{ref.external_id}",
                                headers={**_zoho(token), "etag": ref.etag or ""})
        if res.status_code == 404:
            return
        _raise_for(res, "Deleting the Zoho Calendar event")

    def get_event(self, token, calendar_id, ref, accounts_url=None) -> RemoteEvent:
        with http() as client:
            res = client.get(f"{self._api(accounts_url)}/calendars/{calendar_id}/events/{ref.external_id}",
                             headers=_zoho(token))
        if res.status_code == 404:
            return RemoteEvent(None, None, cancelled=True)
        _raise_for(res, "Reading the Zoho Calendar event")
        events = res.json().get("events") or []
        if not events:
            return RemoteEvent(None, None, cancelled=True)
        when = events[0].get("dateandtime", {})
        return RemoteEvent(_from_zoho_time(when.get("start"), when.get("timezone")),
                           _from_zoho_time(when.get("end"), when.get("timezone")), etag=str(events[0].get("etag") or ""))

    def busy(self, token, calendar_id, account_email, start, end, accounts_url=None) -> list[tuple[str, str]]:
        if not account_email:
            return []
        params = {"uemail": account_email, "ftype": "eventbased",
                  "sdate": _parse(start).astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
                  "edate": _parse(end).astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")}
        with http(BUSY_TIMEOUT) as client:
            res = client.get(f"{self._api(accounts_url)}/calendars/freebusy", params=params, headers=_zoho(token))
        _raise_for(res, "Reading Zoho Calendar busy times")
        body = res.json()
        periods = body.get("fb") or body.get("freebusy") or []
        out = []
        for p in periods:
            if str(p.get("fbtype", "busy")).lower() != "busy":
                continue
            s, e = p.get("startTime") or p.get("start"), p.get("endTime") or p.get("end")
            if s and e:
                out.append((_from_zoho_time(s, None), _from_zoho_time(e, None)))
        return out


PROVIDERS: dict[str, Provider] = {"google": GoogleCalendar(), "zoho": ZohoCalendar()}


def _bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _zoho(token: str) -> dict:
    return {"Authorization": f"Zoho-oauthtoken {token}"}


def _parse(value: str) -> datetime:
    moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


def _google_time(value: dict | None) -> str | None:
    if not value:
        return None
    if value.get("dateTime"):
        return _utc_iso(_parse(value["dateTime"]))
    if value.get("date"):  # an all-day event
        tz = ZoneInfo(value.get("timeZone") or "UTC")
        return _utc_iso(datetime.fromisoformat(value["date"]).replace(tzinfo=tz))
    return None


def _zoho_time(utc_iso: str, tz: ZoneInfo) -> str:
    return _parse(utc_iso).astimezone(tz).strftime("%Y%m%dT%H%M%S%z")


def _from_zoho_time(value: str | None, tz_name: str | None) -> str | None:
    """Zoho writes "20261001T093000+0530", "20261001T040000Z" or, with a separate timezone, "20261001T093000"."""
    if not value:
        return None
    text = value.strip()
    for fmt in ("%Y%m%dT%H%M%S%z", "%Y%m%dT%H%M%SZ", "%Y%m%dT%H%M%S", "%Y%m%d"):
        try:
            moment = datetime.strptime(text, fmt)
        except ValueError:
            continue
        if fmt == "%Y%m%dT%H%M%SZ":
            moment = moment.replace(tzinfo=timezone.utc)
        elif moment.tzinfo is None:
            moment = moment.replace(tzinfo=ZoneInfo(tz_name or "UTC"))
        return _utc_iso(moment)
    return _utc_iso(_parse(text))
