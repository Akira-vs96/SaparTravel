"""Versioned support calendars and human acknowledgement evidence for SLI-S."""
from datetime import date, datetime, time, timedelta, timezone
import json
import math
from pathlib import Path
from zoneinfo import ZoneInfo

from app.core.clock import utc_now
from app.core.config import get_settings

ZONE = ZoneInfo("Asia/Almaty")
RESPONSE_MINUTES = {"P1": 15, "P2": 60, "P3": 540}


def aware(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def validate_calendar(value):
    if (not isinstance(value, dict) or not isinstance(value.get("id"), str) or not value["id"]
            or value.get("timezone") != "Asia/Almaty" or type(value.get("approved")) is not bool):
        raise ValueError("Invalid support calendar")
    if value.get("approved") and not value.get("approval_reference"):
        raise ValueError("Approved calendars require an agreement reference")
    first, last = date.fromisoformat(value["valid_from"]), date.fromisoformat(value["valid_until"])
    if first > last:
        raise ValueError("Invalid calendar coverage")
    for key in ("holidays", "working_days"):
        if not isinstance(value.get(key), list):
            raise ValueError("Calendar dates must be explicit lists")
        for day in value[key]:
            if not first <= date.fromisoformat(day) <= last:
                raise ValueError("Calendar date outside declared coverage")
    if set(value["holidays"]) & set(value["working_days"]):
        raise ValueError("Conflicting calendar dates")
    return value


def current_calendar():
    path = get_settings().support_calendar_file
    if path:
        return validate_calendar(json.loads(Path(path).read_text()))
    # Useful local deadlines, explicitly ineligible for a contractual SLA report.
    return {"id": "demo-weekdays-v1", "timezone": "Asia/Almaty", "approved": False,
            "valid_from": "2000-01-01", "valid_until": "2100-12-31",
            "holidays": [], "working_days": [], "approval_reference": None}


def working_window(day, calendar):
    if not calendar["valid_from"] <= day.isoformat() <= calendar["valid_until"]:
        raise ValueError("Support calendar does not cover the requested period")
    key = day.isoformat()
    if key in calendar["holidays"] or (day.weekday() >= 5 and key not in calendar["working_days"]):
        return None
    return datetime.combine(day, time(9), ZONE), datetime.combine(day, time(18), ZONE)


def response_deadline(registered_at, priority, calendar):
    remaining = RESPONSE_MINUTES[priority] * 60
    cursor = aware(registered_at).astimezone(ZONE)
    for _ in range(3660):
        window = working_window(cursor.date(), calendar)
        if window:
            opening, closing = window
            cursor = max(cursor, opening)
            available = max(0, (closing - cursor).total_seconds())
            if available >= remaining:
                return (cursor + timedelta(seconds=remaining)).astimezone(timezone.utc)
            remaining -= available
        cursor = datetime.combine(cursor.date() + timedelta(days=1), time.min, ZONE)
    raise ValueError("Support calendar contains no reachable response deadline")


def working_seconds(start, end, calendar):
    start, end = aware(start).astimezone(ZONE), aware(end).astimezone(ZONE)
    if end < start:
        raise ValueError("Response precedes registration")
    total = 0
    day = start.date()
    while day <= end.date():
        window = working_window(day, calendar)
        if window:
            opening, closing = window
            total += max(0, (min(end, closing) - max(start, opening)).total_seconds())
        day += timedelta(days=1)
    return math.ceil(total)


def set_deadline(ticket, calendar=None):
    calendar = calendar or current_calendar()
    ticket.response_calendar = calendar
    ticket.response_due_at = response_deadline(ticket.created_at, ticket.priority, calendar)


def acknowledge(ticket, actor, *, now=None):
    if ticket.first_response_at is not None:
        return
    moment = now or utc_now()
    if not ticket.response_calendar or not ticket.response_due_at:
        # A legacy ticket can get a prospective response, but no fabricated SLA deadline.
        ticket.first_response_at, ticket.first_response_by = moment, actor.id
        return
    ticket.response_working_seconds = working_seconds(ticket.created_at, moment, ticket.response_calendar)
    ticket.first_response_at, ticket.first_response_by = moment, actor.id


def month_window(month):
    if len(month) != 7 or datetime.strptime(month, "%Y-%m").strftime("%Y-%m") != month:
        raise ValueError("Expected YYYY-MM")
    start = datetime.strptime(month, "%Y-%m").replace(tzinfo=ZONE)
    end = start.replace(year=start.year + 1, month=1) if start.month == 12 else start.replace(month=start.month + 1)
    return start.astimezone(timezone.utc), end.astimezone(timezone.utc)


def response_report(tickets, month, *, now=None):
    moment = aware(now or utc_now())
    start, end = month_window(month)
    rows = list(tickets)
    priorities = {}
    for priority in RESPONSE_MINUTES:
        eligible = [row for row in rows if row.priority == priority and row.response_due_at
                    and start <= aware(row.response_due_at) < end and aware(row.response_due_at) <= moment]
        on_time = sum(row.first_response_at is not None and aware(row.first_response_at) <= aware(row.response_due_at) for row in eligible)
        priorities[priority] = {"eligible": len(eligible), "on_time": on_time, "breaches": len(eligible) - on_time,
                                "percent": on_time / len(eligible) * 100 if eligible else None,
                                "status": "measured" if eligible else "no_data"}
    unknown = sum(row.response_due_at is None and start <= aware(row.created_at) < end for row in rows)
    covered = [row for row in rows if row.response_due_at and start <= aware(row.response_due_at) < end]
    approved = bool(covered) and all((row.response_calendar or {}).get("approved") is True for row in covered)
    return {"month": month, "timezone": "Asia/Almaty", "finalized": moment >= end,
            "priorities": priorities, "unknown_deadlines": unknown,
            "calendar_approved": approved, "sla_evaluable": moment >= end and approved and unknown == 0,
            "selection": "response deadline in calendar month; current month contains only matured deadlines"}
