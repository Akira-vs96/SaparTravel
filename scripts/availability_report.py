"""Conservative full-calendar-month SLI-A report, using Asia/Almaty boundaries."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
import json
import math
from pathlib import Path
from zoneinfo import ZoneInfo

from scripts.availability_probe import SCENARIO_VERSION, STEPS, identifier


def month_window(month: str) -> tuple[datetime, datetime]:
    start = datetime.strptime(month, "%Y-%m").replace(tzinfo=ZoneInfo("Asia/Almaty"))
    end = start.replace(year=start.year + 1, month=1) if start.month == 12 else start.replace(month=start.month + 1)
    return start.astimezone(timezone.utc), end.astimezone(timezone.utc)


def valid_success(record: dict) -> bool:
    """Never trust a top-level success flag without the underlying step evidence."""
    def duration(value, maximum):
        return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and 0 <= value <= maximum

    steps = record.get("steps")
    if (record.get("success") is not True or not duration(record.get("duration_ms"), 10_000)
            or not isinstance(steps, list) or len(steps) != len(STEPS)):
        return False
    expected_status = {name: 201 if name == "create" else 200 for name in STEPS}
    return all(isinstance(step, dict) and step.get("name") == name
               and step.get("success") is True and duration(step.get("duration_ms"), 2000)
               and step.get("status_code") == expected_status[name]
               for name, step in zip(STEPS, steps))


def aggregate(records: list[dict], *, month: str, points: list[str], deployment_id: str,
              scenario_version: str = SCENARIO_VERSION, now: datetime | None = None,
              scope: str = "acceptance-only", agreement: dict | None = None) -> dict:
    if len(points) != 3 or len(set(points)) != 3:
        raise ValueError("exactly three distinct, predeclared points are required")
    for value in [*points, deployment_id, scenario_version]:
        identifier(value)
    start, end = month_window(month)
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        raise ValueError("now must be timezone aware")
    if current < end:
        raise ValueError("only a completed calendar month can be reported")
    if scope not in {"acceptance-only", "operational"}:
        raise ValueError("unsupported scope")
    excluded = exclusion_minutes(agreement, month, deployment_id, start, end) if agreement is not None else set()
    slots = defaultdict(list)
    ignored = Counter()
    for record in records:
        if not isinstance(record, dict):
            ignored["invalid_record"] += 1
            continue
        try:
            stamp = datetime.fromisoformat(record["timestamp_utc"].replace("Z", "+00:00"))
            if stamp.tzinfo is None or stamp.utcoffset() != timedelta(0):
                raise ValueError
            minute = stamp.replace(second=0, microsecond=0)
        except (KeyError, TypeError, ValueError, AttributeError):
            ignored["invalid_timestamp"] += 1
            continue
        if not start <= stamp < end:
            ignored["outside_month"] += 1
            continue
        if (record.get("point") not in points or record.get("deployment_id") != deployment_id
                or record.get("scope") != scope
                or record.get("scenario_version") != scenario_version):
            ignored["wrong_configuration"] += 1
            continue
        slots[(minute, record["point"])].append(record)
    total_minutes = int((end - start).total_seconds() / 60)
    successes = 0
    sla_successes = 0
    complete_minutes = 0
    observed = Counter()
    successful_points = Counter()
    duplicate_slots = 0
    for minute_offset in range(total_minutes):
        minute = start + timedelta(minutes=minute_offset)
        successful = 0
        present = 0
        for point in points:
            entries = slots.get((minute, point), [])
            if entries:
                present += 1
                observed[point] += 1
            if len(entries) > 1:
                # Neither retries nor conflicting logs can repair an already failed observation.
                duplicate_slots += 1
            elif len(entries) == 1 and valid_success(entries[0]):
                successful += 1
                successful_points[point] += 1
        successes += successful >= 2
        if minute not in excluded:
            sla_successes += successful >= 2
        complete_minutes += present == 3
    observed_total = sum(observed.values())
    availability = successes / total_minutes * 100 if observed_total else None
    sla_minutes = total_minutes - len(excluded)
    sla_percent = sla_successes / sla_minutes * 100 if observed_total and sla_minutes else None
    evaluable = agreement is not None and scope == "operational" and agreement.get("independent_points") is True
    return {"month": month, "timezone": "Asia/Almaty", "scope": scope,
            "deployment_id": deployment_id, "scenario_version": scenario_version,
            "status": "measured" if observed_total else "no_data", "points": points,
            "window_start_utc": start.isoformat(), "window_end_utc": end.isoformat(),
            "total_minutes": total_minutes, "successful_minutes": successes,
            "failed_minutes": total_minutes - successes, "availability_percent": availability,
            "slo_target_percent": 99.9, "slo_met": availability >= 99.9 if availability is not None else None,
            "slo_error_budget_minutes": total_minutes * .001,
            "slo_remaining_budget_minutes": total_minutes * .001 - (total_minutes - successes),
            "complete_coverage_minutes": complete_minutes,
            "point_observations": {point: observed[point] for point in points},
            "successful_point_observations": {point: successful_points[point] for point in points},
            "missing_point_observations": total_minutes * 3 - observed_total,
            "duplicate_point_minutes": duplicate_slots, "ignored_records": dict(ignored),
            "sla_evaluation": "evaluated" if evaluable else "not_evaluated: independent operational points and an approved agreement are required",
            "sla_availability_percent": sla_percent if evaluable else None,
            "sla_target_percent": 99.5, "sla_met": sla_percent >= 99.5 if evaluable and sla_percent is not None else None,
            "sla_excluded_minutes": len(excluded), "sla_eligible_minutes": sla_minutes,
            "sla_successful_minutes": sla_successes,
            "exclusions": agreement.get("exclusions", []) if agreement else []}


def exclusion_minutes(agreement, month, deployment_id, start, end):
    if (not isinstance(agreement, dict) or agreement.get("approved") is not True
            or not agreement.get("agreement_reference") or agreement.get("month") != month
            or agreement.get("deployment_id") != deployment_id or not isinstance(agreement.get("exclusions"), list)):
        raise ValueError("An approved agreement for this deployment and month is required")
    result = set()
    for entry in agreement["exclusions"]:
        if not isinstance(entry, dict) or not all(entry.get(key) for key in ("reason", "evidence_reference", "approval_reference")):
            raise ValueError("Every exclusion requires a reason, evidence and approval")
        lower = datetime.fromisoformat(entry["start_utc"].replace("Z", "+00:00"))
        upper = datetime.fromisoformat(entry["end_utc"].replace("Z", "+00:00"))
        if (lower.tzinfo is None or upper.tzinfo is None or lower.utcoffset() != timedelta(0) or upper.utcoffset() != timedelta(0)
                or lower.second or upper.second or lower.microsecond or upper.microsecond or not start <= lower < upper <= end):
            raise ValueError("Exclusions must be whole UTC minutes inside the reporting month")
        while lower < upper:
            result.add(lower)
            lower += timedelta(minutes=1)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, nargs="+", required=True)
    parser.add_argument("--month", required=True)
    parser.add_argument("--points", nargs=3, required=True)
    parser.add_argument("--deployment-id", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--scope", choices=("acceptance-only", "operational"), default="acceptance-only")
    parser.add_argument("--agreement", type=Path)
    args = parser.parse_args()
    try:
        records = []
        for path in args.input:
            for line in path.read_text().splitlines():
                if line.strip():
                    # Truncated/corrupt lines do not fabricate observations. They are explicitly counted.
                    try:
                        records.append(json.loads(line))
                    except ValueError:
                        records.append(None)
        agreement = json.loads(args.agreement.read_text()) if args.agreement else None
        report = aggregate(records, month=args.month, points=args.points, deployment_id=args.deployment_id,
                           scope=args.scope, agreement=agreement)
        args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + "\n")
        return 0
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        print("Invalid report input, configuration or month; no details logged.")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
