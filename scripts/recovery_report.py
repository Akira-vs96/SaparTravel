"""Confirm SLI-R only from five consecutive, quorum-successful real UTC minutes."""
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from scripts.availability_report import valid_success
from scripts.availability_probe import SCENARIO_VERSION


def recovery_report(records, *, failure_at, deployment_id, points, now=None, independent_points=False, scope="acceptance-only"):
    if len(points) != 3 or len(set(points)) != 3 or failure_at.tzinfo is None:
        raise ValueError("A timezone-aware outage start and three declared points are required")
    current = now or datetime.now(timezone.utc)
    slots = defaultdict(list)
    for row in records:
        if (not isinstance(row, dict) or row.get("deployment_id") != deployment_id or row.get("point") not in points
                or row.get("scenario_version") != SCENARIO_VERSION or row.get("scope") != scope):
            continue
        try:
            stamp = datetime.fromisoformat(row["timestamp_utc"])
            if stamp.tzinfo is None or not failure_at <= stamp <= current:
                continue
        except (KeyError, TypeError, ValueError):
            continue
        slots[(stamp.astimezone(timezone.utc).replace(second=0, microsecond=0), row["point"])].append(row)
    good = []
    for minute in sorted({key[0] for key in slots}):
        if minute < failure_at:
            continue
        successful = sum(len(slots[(minute, point)]) == 1 and valid_success(slots[(minute, point)][0]) for point in points)
        if successful >= 2:
            good.append(minute)
    first = confirmed = None
    for index in range(max(0, len(good) - 4)):
        window = good[index:index + 5]
        if window[-1] - window[0] == timedelta(minutes=4):
            first, confirmed = window[0], window[-1]
            break
    seconds = (first - failure_at).total_seconds() if first else None
    return {"failure_started_at_utc": failure_at.isoformat(),
            "recovery_started_at_utc": first.isoformat() if first else None,
            "confirmation_minute_utc": confirmed.isoformat() if confirmed else None,
            "successful_consecutive_minutes": 5 if first else 0, "rto_seconds": seconds,
            "rto_target_seconds": 900, "rto_met": seconds <= 900 if seconds is not None else None,
            "sli_r_confirmed": first is not None, "independent_points": independent_points,
            "scope": "operational" if independent_points else "local-acceptance"}
