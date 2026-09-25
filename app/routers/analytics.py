from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.agent import Agent
from app.models.appointment import Appointment
from app.models.call import CallLog, CallTurnMetric
from app.models.lead import Lead
from app.core.auth_deps import get_current_user
from app.models.user import User
from app.schemas.common import UTCDateTime

router = APIRouter(prefix="/api/stats", tags=["Dashboard Analytics"])

MONTH_DAYS = 32  # always load enough history to cover the whole current month


@router.get("")
def get_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Calculate system-wide summaries: call count, total bookings, durations, and booking rate."""
    total_calls = db.query(CallLog).filter(CallLog.tenant_id == current_user.tenant_id).count()
    total_bookings = db.query(CallLog).filter(
        CallLog.tenant_id == current_user.tenant_id,
        CallLog.was_booked == True
    ).count()

    avg_dur = db.query(func.avg(CallLog.duration_seconds)).filter(
        CallLog.tenant_id == current_user.tenant_id
    ).scalar() or 0.0
    avg_duration = round(float(avg_dur))

    booking_rate = 0
    if total_calls > 0:
        booking_rate = round((total_bookings / total_calls) * 100)

    return {
        "total_calls": total_calls,
        "total_bookings": total_bookings,
        "avg_duration": avg_duration,
        "booking_rate": booking_rate
    }


class Totals(BaseModel):
    calls: int
    calls_today: int
    bookings: int
    booking_rate: int
    avg_duration: int
    minutes: int
    cost_usd: float


class Trend(BaseModel):
    calls_7d: int
    calls_prev_7d: int
    bookings_7d: int
    bookings_prev_7d: int


class DayPoint(BaseModel):
    date: str
    calls: int
    bookings: int
    avg_duration: int


class HeatCell(BaseModel):
    day: int  # 0 = Monday
    hour: int
    calls: int


class Latency(BaseModel):
    turns: int
    avg_total_ms: Optional[float] = None
    avg_stt_ms: Optional[float] = None
    avg_llm_ms: Optional[float] = None
    avg_tts_ms: Optional[float] = None
    avg_kb_ms: Optional[float] = None
    kb_usage_rate: Optional[int] = None


class AgentActivity(BaseModel):
    id: str
    name: str
    status: str
    calls: int
    bookings: int


class ActivityItem(BaseModel):
    kind: str  # call | lead | appointment
    title: str
    at: UTCDateTime


class MonthUsage(BaseModel):
    calls: int
    minutes: int
    cost_usd: float


class FollowUps(BaseModel):
    overdue: int
    today: int


class OverviewOut(BaseModel):
    timezone: str
    days: int
    totals: Totals
    trend: Trend
    daily: List[DayPoint]
    sentiment: Dict[str, int]
    heatmap: List[HeatCell]
    latency: Latency
    agents: List[AgentActivity]
    activity: List[ActivityItem]
    month: MonthUsage
    follow_ups: FollowUps


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def _avg(values: list) -> Optional[float]:
    values = [v for v in values if v is not None]
    return round(sum(values) / len(values), 1) if values else None


@router.get("/overview", response_model=OverviewOut)
def get_overview(
    tz: str = Query("UTC", description="IANA timezone used for days and hours, e.g. Asia/Kolkata"),
    days: int = Query(14, ge=1, le=90, description="Period for the daily series, sentiment, heatmap, latency and agents"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Everything the dashboard and analytics pages show, computed from this workspace's own records."""
    try:
        zone = ZoneInfo(tz)
    except (ZoneInfoNotFoundError, ValueError):
        raise HTTPException(status_code=422, detail=f"Unknown timezone: {tz}")
    tenant = current_user.tenant_id
    now = datetime.now(timezone.utc)
    today = now.astimezone(zone).date()

    total_calls = db.query(CallLog).filter(CallLog.tenant_id == tenant).count()
    total_bookings = db.query(CallLog).filter(CallLog.tenant_id == tenant, CallLog.was_booked == True).count()
    total_seconds = db.query(func.coalesce(func.sum(CallLog.duration_seconds), 0)).filter(CallLog.tenant_id == tenant).scalar() or 0
    total_cost = db.query(func.coalesce(func.sum(CallLog.estimated_cost_usd), 0.0)).filter(CallLog.tenant_id == tenant).scalar() or 0.0

    loaded_since = now - timedelta(days=max(days, MONTH_DAYS))
    loaded = db.query(CallLog).filter(CallLog.tenant_id == tenant, CallLog.created_at >= loaded_since.replace(tzinfo=None)).all()
    local = [(_utc(c.created_at).astimezone(zone), c) for c in loaded]
    first_day = today - timedelta(days=days - 1)
    period = [(m, c) for m, c in local if m.date() >= first_day]
    recent = [c for _, c in period]
    since = datetime.combine(first_day, datetime.min.time(), zone).astimezone(timezone.utc)

    daily_counts: Counter = Counter()
    daily_bookings: Counter = Counter()
    daily_seconds: Counter = Counter()
    heat: Counter = Counter()
    for moment, call in local:
        daily_counts[moment.date()] += 1
        daily_bookings[moment.date()] += int(bool(call.was_booked))
        daily_seconds[moment.date()] += call.duration_seconds or 0
    for moment, _ in period:
        heat[(moment.weekday(), moment.hour)] += 1
    day_list = [today - timedelta(days=i) for i in range(days - 1, -1, -1)]

    def window(start: int, end: int, booked: bool = False) -> int:
        return sum(1 for m, c in local if start <= (today - m.date()).days < end and (c.was_booked or not booked))

    month_start = today.replace(day=1)
    month_calls = [c for m, c in local if m.date() >= month_start]

    turns = db.query(CallTurnMetric).filter(
        CallTurnMetric.tenant_id == tenant, CallTurnMetric.created_at >= since.replace(tzinfo=None)
    ).all()
    assistant_turns = [t for t in turns if t.speaker == "assistant"] or turns
    latency = Latency(
        turns=len(assistant_turns),
        avg_total_ms=_avg([t.total_turn_ms for t in assistant_turns]),
        avg_stt_ms=_avg([t.stt_endpoint_ms for t in assistant_turns]),
        avg_llm_ms=_avg([t.llm_first_token_ms for t in assistant_turns]),
        avg_tts_ms=_avg([t.tts_first_audio_ms for t in assistant_turns]),
        avg_kb_ms=_avg([t.kb_ms for t in assistant_turns if t.kb_used]),
        kb_usage_rate=round(100 * sum(t.kb_used for t in assistant_turns) / len(assistant_turns)) if assistant_turns else None,
    )

    per_agent: Counter = Counter(c.agent_id for c in recent if c.agent_id)
    per_agent_booked: Counter = Counter(c.agent_id for c in recent if c.agent_id and c.was_booked)
    agents = [
        AgentActivity(id=a.id, name=a.name, status=a.status, calls=per_agent[a.id], bookings=per_agent_booked[a.id])
        for a in db.query(Agent).filter(Agent.tenant_id == tenant, Agent.disabled_at.is_(None)).all()
    ]
    agents.sort(key=lambda a: (-a.calls, a.name.lower()))

    activity: list[ActivityItem] = []
    for call in db.query(CallLog).filter(CallLog.tenant_id == tenant).order_by(CallLog.created_at.desc()).limit(10):
        who = call.caller_name or call.phone_number
        booked = " and booked an appointment" if call.was_booked else ""
        activity.append(ActivityItem(kind="call", title=f"{call.direction.capitalize()} call with {who}{booked}", at=call.created_at))
    for lead in db.query(Lead).filter(Lead.tenant_id == tenant, Lead.deleted_at.is_(None)).order_by(Lead.created_at.desc()).limit(10):
        activity.append(ActivityItem(kind="lead", title=f"New lead: {lead.name}", at=lead.created_at))
    for apt in db.query(Appointment).filter(Appointment.tenant_id == tenant).order_by(Appointment.created_at.desc()).limit(10):
        activity.append(ActivityItem(kind="appointment", title=f"Appointment booked with {apt.contact_name}", at=apt.created_at))
    activity.sort(key=lambda item: item.at, reverse=True)

    open_leads = db.query(Lead).filter(Lead.tenant_id == tenant, Lead.deleted_at.is_(None),
                                       Lead.status.notin_(("Converted", "Lost")), Lead.follow_up_date.isnot(None))
    today_iso = today.isoformat()
    follow_ups = FollowUps(overdue=open_leads.filter(Lead.follow_up_date < today_iso).count(),
                           today=open_leads.filter(Lead.follow_up_date == today_iso).count())

    return OverviewOut(
        timezone=tz,
        days=days,
        totals=Totals(
            calls=total_calls,
            calls_today=daily_counts[today],
            bookings=total_bookings,
            booking_rate=round(100 * total_bookings / total_calls) if total_calls else 0,
            avg_duration=round(total_seconds / total_calls) if total_calls else 0,
            minutes=round(total_seconds / 60),
            cost_usd=round(float(total_cost), 2),
        ),
        trend=Trend(calls_7d=window(0, 7), calls_prev_7d=window(7, 14),
                    bookings_7d=window(0, 7, booked=True), bookings_prev_7d=window(7, 14, booked=True)),
        daily=[DayPoint(date=d.isoformat(), calls=daily_counts[d], bookings=daily_bookings[d],
                        avg_duration=round(daily_seconds[d] / daily_counts[d]) if daily_counts[d] else 0) for d in day_list],
        sentiment=dict(Counter((c.sentiment or "unknown") for c in recent)),
        heatmap=[HeatCell(day=d, hour=h, calls=n) for (d, h), n in sorted(heat.items())],
        latency=latency,
        agents=agents,
        activity=activity[:10],
        follow_ups=follow_ups,
        month=MonthUsage(
            calls=len(month_calls),
            minutes=round(sum(c.duration_seconds or 0 for c in month_calls) / 60),
            cost_usd=round(sum(c.estimated_cost_usd or 0.0 for c in month_calls), 2),
        ),
    )
