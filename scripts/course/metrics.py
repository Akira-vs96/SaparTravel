"""Flow and DORA measurements. Missing transitions and deployments stay unknown."""
from collections import Counter
from datetime import datetime, timedelta, timezone
import math


def stamp(value):
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("Evidence timestamps must have an explicit timezone")
    return result.astimezone(timezone.utc)


def percentile(values, fraction):
    return sorted(values)[max(0, math.ceil(len(values) * fraction) - 1)] if values else None


IN_PROGRESS = "In progress"
STATUSES = ("Backlog", "Ready", IN_PROGRESS, "Review", "Blocked", "Done", "Unknown")
WIP = (IN_PROGRESS, "Review", "Blocked")


def _normalised_events(facts):
    events, seen, duplicates = [], set(), 0
    for source in facts.get("transitions", []):
        row = {**source, "instant": stamp(source["at"])}
        identity = source.get("id") or (source["issue"], row["instant"], source["from"], source["to"])
        if identity in seen:
            duplicates += 1
            continue
        seen.add(identity)
        events.append(row)
    return sorted(events, key=lambda r: r["instant"]), duplicates


def _project_snapshots(facts):
    snapshots = {}
    for item in facts.get("project_items", []):
        content = item.get("content") or {}
        if content.get("type", "Issue") != "Issue" or "number" not in content:
            continue
        if facts.get("repository") and content.get("repository", facts["repository"]) != facts["repository"]:
            continue
        snapshots[content["number"]] = item.get("status") or "Unknown"
    return snapshots


def _span(row, following, captured, snapshot):
    until = following["instant"] if following else captured
    status = row["to"] if row["to"] in STATUSES else "Unknown"
    broken = following is not None and following["from"] != row["to"]
    tail_mismatch = following is None and snapshot is not None and (row["to"] or "Unknown") != snapshot
    gap = None
    if broken or tail_mismatch:
        gap = {"issue": row["issue"], "after_utc": row["instant"].isoformat(),
               "before_utc": until.isoformat(), "last_observed": status,
               "next_previous_status": following["from"] if following else snapshot,
               "kind": "broken_chain" if broken else "snapshot_mismatch"}
        status = "Unknown"
    return until, status, gap, tail_mismatch


def _issue_intervals(events, since, captured, snapshot):
    spans, gaps, tail_mismatch = [], [], False
    if not events:
        return [(since, captured, "Unknown")], [], False
    if since < events[0]["instant"]:
        spans.append((since, events[0]["instant"], "Unknown"))
    for index, row in enumerate(events):
        following = events[index + 1] if index + 1 < len(events) else None
        until, status, gap, mismatch = _span(row, following, captured, snapshot)
        if gap:
            gaps.append(gap)
        tail_mismatch = tail_mismatch or mismatch
        spans.append((max(since, row["instant"]), until, status))
    return spans, gaps, tail_mismatch


def _timelines(by_issue, snapshots, added, captured):
    bounds, intervals, gaps, mismatches, unlocated = {}, {}, [], [], []
    for issue in sorted(set(by_issue) | set(snapshots)):
        events = by_issue.get(issue, [])
        since = added.get(issue, events[0]["instant"] if events else None)
        if since is None:
            unlocated.append(issue)
            continue
        bounds[issue] = since
        spans, issue_gaps, mismatch = _issue_intervals(events, since, captured, snapshots.get(issue))
        intervals[issue] = spans
        gaps.extend(issue_gaps)
        if mismatch:
            mismatches.append(issue)
    return {"bounds": bounds, "intervals": intervals, "gaps": gaps,
            "snapshot_mismatches": mismatches, "unlocated_items": unlocated}


def _history(facts, start, end):
    if start.tzinfo is None or end.tzinfo is None or start >= end:
        raise ValueError("Expected a nonempty timezone-aware time window")
    start, end = start.astimezone(timezone.utc), end.astimezone(timezone.utc)
    captured = stamp(facts["captured_at_utc"]) if facts.get("captured_at_utc") else end
    if end > captured:
        raise ValueError("The requested window extends beyond the evidence capture")
    events, duplicates = _normalised_events(facts)
    snapshots = _project_snapshots(facts)
    added = {r["issue"]: stamp(r["created_at"]) for r in facts.get("project_item_metadata", [])
             if r.get("issue") is not None and r.get("repository", facts.get("repository")) == facts.get("repository")}
    by_issue = {}
    for row in events:
        by_issue.setdefault(row["issue"], []).append(row)
    return {**_timelines(by_issue, snapshots, added, captured),
            "start": start, "end": end, "events": events, "by_issue": by_issue,
            "items_without_added_at": sorted((set(snapshots) | set(by_issue)) - set(added)),
            "duplicate_events_removed": duplicates, "captured_at": captured,
            "collection_complete": facts.get("project_evidence") != "not_requested"
                and not facts.get("project_items_truncated") and not facts.get("truncated_timelines")}


def _update_start(starts, previous, row):
    issue = row["issue"]
    gap = issue in previous and previous[issue] != row["from"]
    reopened = row["from"] == "Done" and row["to"] != "Done"
    if gap or reopened or not row["to"]:
        starts.pop(issue, None)
    if row["to"] == IN_PROGRESS and row["from"] in ("Backlog", "Ready", "Done") and issue not in starts:
        starts[issue] = row["instant"]


def _completion_record(row, begun):
    return {"issue": row["issue"], "completed_at_utc": row["instant"].isoformat(),
            "started_at_utc": begun.isoformat() if begun else None,
            "cycle_days": (row["instant"] - begun).total_seconds() / 86400 if begun else None}


def _completions(events, start, end):
    starts, previous, completions, count = {}, {}, {}, 0
    for row in events:
        at, issue = row["instant"], row["issue"]
        if at >= end:
            break
        _update_start(starts, previous, row)
        if row["to"] == "Done":
            begun = starts.pop(issue, None)  # Reset even for a completion outside the window.
            if row["from"] and row["from"] != "Done" and start <= at:
                count += 1
                completions[issue] = _completion_record(row, begun)
        previous[issue] = row["to"]
    return completions, count


def _status_exposure(history, start, end):
    by_status = Counter(dict.fromkeys(STATUSES, 0.0))
    for spans in history["intervals"].values():
        for left, right, status in spans:
            overlap = max(0, (min(right, end) - max(left, start)).total_seconds()) / 86400
            by_status[status] += overlap
    return by_status


def _quality(history, start, end, exposure):
    complete = (history["collection_complete"] and not history["unlocated_items"]
                and not history["items_without_added_at"] and exposure["Unknown"] == 0)
    return {"capture_at_utc": history["captured_at"].isoformat(), "coverage_complete": complete,
            "unlocated_items": history["unlocated_items"], "items_without_added_at": history["items_without_added_at"],
            "duplicate_events_removed": history["duplicate_events_removed"],
            "gaps": [g for g in history["gaps"] if stamp(g["after_utc"]) < end and stamp(g["before_utc"]) > start]}


def flow(facts, start, end):
    history = _history(facts, start, end)
    start, end = history["start"], history["end"]
    completions, count = _completions(history["events"], start, end)
    by_status = _status_exposure(history, start, end)
    quality = _quality(history, start, end, by_status)
    days = (end - start).total_seconds() / 86400
    cycles = [r["cycle_days"] for r in completions.values() if r["cycle_days"] is not None]
    mean_cycle = sum(cycles) / len(cycles) if cycles else None
    lower_wip = sum(by_status[s] for s in WIP) / days
    upper_wip = lower_wip + by_status["Unknown"] / days
    complete_cycles = bool(completions) and len(cycles) == len(completions)
    expected_wip = len(completions) / days * mean_cycle if complete_cycles else None
    evaluable = complete_cycles and quality["coverage_complete"]
    return {"start_utc": start.isoformat(), "end_utc": end.isoformat(), "calendar_days": days,
            "throughput": len(completions), "completed_issues": sorted(completions),
            "completion_events": count, "completed_items": [completions[k] for k in sorted(completions)],
            "cycle_time_samples": len(cycles), "cycle_mean_days": mean_cycle,
            "cycle_p85_days": percentile(cycles, .85),
            "cycle_sample_coverage": len(cycles) / len(completions) if completions else None,
            "observed_average_wip": lower_wip, "average_wip": lower_wip if quality["coverage_complete"] else None,
            "wip_lower_bound": lower_wip, "wip_upper_bound": upper_wip if not history["unlocated_items"] else None,
            "observed_status_task_days": dict(by_status), "little_expected_wip": expected_wip,
            "little_law_evaluable": evaluable, "little_wip_difference": lower_wip - expected_wip if evaluable else None,
            "history_matches_current_snapshot": not history["snapshot_mismatches"],
            "history_snapshot_mismatches": history["snapshot_mismatches"], "data_quality": quality,
            "limitation": "Observed issue cohort only. Missing or inconsistent status intervals are Unknown; WIP is a bound. Cycle statistics use the final observed completion per issue and witnessed, continuous starts. Little's law needs complete inputs and a sufficiently stable observation window."}


def cfd(facts, start, end):
    history = _history(facts, start, end)
    start, end = history["start"], history["end"]
    rows, cursor = [], start
    while cursor < end:
        counts = Counter(dict.fromkeys(STATUSES, 0))
        for issue, since in history["bounds"].items():
            if cursor < since:
                continue
            exact = [r for r in history["by_issue"].get(issue, []) if r["instant"] == cursor]
            if exact:
                value = exact[-1]["to"]
                status = value if value in STATUSES else "Unknown"
            else:
                status = next((s for a, b, s in history["intervals"][issue] if a <= cursor < b), "Unknown")
            counts[status] += 1
        rows.append({"date": cursor.date().isoformat(), "at_utc": cursor.isoformat(),
                     "sample": "daily_boundary_utc", **dict(counts),
                     "tracked_items": sum(counts.values()), "unlocated_items": len(history["unlocated_items"])})
        cursor += timedelta(days=1)
    return rows


def dora(facts, start, end, incidents=None, incident_register_complete=False):
    if start >= end:
        raise ValueError("Expected a nonempty time window")
    deployments = [d for d in facts["deployments"] if d.get("finished_at") and start <= stamp(d["finished_at"]) < end]
    successes = [d for d in deployments if d["state"] == "success"]
    leads = [(stamp(d["finished_at"]) - stamp(d["commit_at"])).total_seconds() / 3600
             for d in successes if d.get("commit_at") and stamp(d["finished_at"]) >= stamp(d["commit_at"])]
    failed_ids = {i["deployment_id"] for i in incidents or [] if start <= stamp(i["started_at"]) < end}
    if incident_register_complete and not failed_ids.issubset({d["id"] for d in deployments}):
        raise ValueError("Incidents must reference deployments from the measured denominator")
    recovery = [(stamp(i["recovered_at"]) - stamp(i["started_at"])).total_seconds() / 60
                for i in incidents or [] if i.get("recovered_at") and start <= stamp(i["started_at"]) < end]
    runs = [r for r in facts["runs"] if start <= stamp(r["created_at"]) < end]
    return {"start_utc": start.isoformat(), "end_utc": end.isoformat(), "deployment_count": len(deployments),
            "deployment_frequency_per_week": len(successes) / ((end - start).total_seconds() / 604800) if deployments else None,
            "lead_time_median_hours": percentile(leads, .5),
            "change_failure_rate_percent": len(failed_ids) / len(deployments) * 100 if deployments and incident_register_complete else None,
            "recovery_median_minutes": percentile(recovery, .5),
            "ci_runs": len(runs), "ci_success": sum(r["conclusion"] == "success" for r in runs),
            "ci_failure": sum(r["conclusion"] == "failure" for r in runs),
            "status": "measured" if deployments else "no_deployment_evidence",
            "limitation": "A green CI run is not a deployment. Missing incident evidence is not a 0% failure rate."}


def main():
    import argparse
    import json
    from pathlib import Path
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--start", type=stamp, required=True)
    parser.add_argument("--end", type=stamp, required=True)
    parser.add_argument("--kind", choices=("flow", "dora"), default="flow")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--plot", action="store_true")
    args = parser.parse_args()
    facts = json.loads(args.snapshot.read_text())
    result = flow(facts, args.start, args.end) if args.kind == "flow" else dora(facts, args.start, args.end)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    if args.plot:
        from scripts.course.flow_report import plot_cfd
        plot_cfd(cfd(facts, args.start, args.end), args.output.with_suffix(".png"))
    print("Recorded evidence calculated; missing metrics remain null")


if __name__ == "__main__":
    main()
