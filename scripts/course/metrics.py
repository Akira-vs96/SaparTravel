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


def flow(facts, start, end):
    if not start < end:
        raise ValueError("Expected a nonempty time window")
    events = sorted(facts["transitions"], key=lambda row: row["at"])
    cycles, completed, by_status = [], [], Counter()
    starts, current = {}, {}
    for row in events:
        at, issue = stamp(row["at"]), row["issue"]
        if at >= end:
            continue
        previous = current.get(issue)
        if previous:
            overlap = max(0, (min(at, end) - max(previous[1], start)).total_seconds())
            by_status[previous[0]] += overlap / 86400
        if row["to"] == "In progress" and issue not in starts:
            starts[issue] = at
        if row["to"] == "Done" and row["from"] and start <= at < end:
            completed.append(issue)
            if issue in starts:
                cycles.append((at - starts.pop(issue)).total_seconds() / 86400)
        current[issue] = (row["to"], at)
    for status, at in current.values():
        by_status[status] += max(0, (end - max(start, at)).total_seconds()) / 86400
    days = (end - start).total_seconds() / 86400
    mismatches = []
    latest = {row["issue"]: row["to"] for row in events}
    for item in facts["project_items"]:
        number = item.get("content", {}).get("number")
        if number in latest and item.get("status") != latest[number]:
            mismatches.append(number)
    mean_cycle = sum(cycles) / len(cycles) if cycles else None
    average_wip = sum(by_status[s] for s in ("In progress", "Review", "Blocked")) / days
    return {"start_utc": start.isoformat(), "end_utc": end.isoformat(), "calendar_days": days,
            "throughput": len(set(completed)), "completed_issues": sorted(set(completed)),
            "cycle_time_samples": len(cycles), "cycle_mean_days": mean_cycle,
            "cycle_p85_days": percentile(cycles, .85), "observed_average_wip": average_wip,
            "observed_status_task_days": dict(by_status),
            "little_expected_wip": len(set(completed)) / days * mean_cycle if mean_cycle is not None else None,
            "little_law_evaluable": mean_cycle is not None and not mismatches,
            "history_matches_current_snapshot": not mismatches,
            "history_snapshot_mismatches": mismatches,
            "limitation": "Observed transitions only; absent start times are never replaced with issue creation dates. Initial Done is not throughput."}


def cfd(facts, start, end):
    rows, cursor = [], start
    while cursor < end:
        state = {}
        for event in sorted(facts["transitions"], key=lambda r: r["at"]):
            if stamp(event["at"]) <= cursor:
                state[event["issue"]] = event["to"]
        rows.append({"date": cursor.date().isoformat(), **dict(Counter(state.values()))})
        cursor += timedelta(days=1)
    return rows


def dora(facts, start, end, incidents=None, incident_register_complete=False):
    if not start < end:
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
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        data = cfd(facts, args.start, args.end)
        statuses = ("Backlog", "Ready", "In progress", "Review", "Blocked", "Done")
        fig, ax = plt.subplots(figsize=(10, 5))
        ax.stackplot(range(len(data)), *[[row.get(status, 0) for row in data] for status in statuses], labels=statuses)
        ax.set(xlabel="Observed day", ylabel="Recorded project items", title="Observed CFD; incomplete transition history")
        ax.legend(loc="upper left", ncols=3)
        fig.tight_layout()
        fig.savefig(args.output.with_suffix(".png"), dpi=160)
        plt.close(fig)
    print("Recorded evidence calculated; missing metrics remain null")


if __name__ == "__main__":
    main()
