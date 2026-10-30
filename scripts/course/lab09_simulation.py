"""Deterministic educational simulation of two sprints; never writes real history."""
import argparse
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path

from scripts.course.flow_report import plot_cfd, write_csv, write_json
from scripts.course.metrics import STATUSES, WIP, flow, flow_details, stamp

ROOT = Path(__file__).resolve().parents[2]
KIND = "educational_simulation"
TICK = timedelta(minutes=15)
MODEL_REPO = "simulation/SaparTravel-LZ09"


@dataclass
class Job:
    issue: str
    title: str
    owner: str
    effort_ticks: int
    status: str = ""
    entered_at: object = None
    remaining: int = 0


class SprintSimulation:
    def __init__(self, config, index, review_slots):
        self.config = config
        self.sprint = config["sprints"][index]
        self.start = stamp(self.sprint["start_utc"])
        self.end = self.start + timedelta(days=7)
        self.slots = review_slots
        self.jobs = [Job(f"SIM-S{index + 1}-{n + 1:02d}", title,
                         "Developer A" if n % 2 == 0 else "Developer B", config["effort_ticks"][n])
                     for n, title in enumerate(self.sprint["tasks"])]
        self.developers = {"Developer A": None, "Developer B": None}
        self.tester = None
        self.reviewer = None
        self.events, self.trace, self.services = [], [], []

    def _count(self, status):
        return sum(job.status == status for job in self.jobs)

    def _active(self):
        return sum(job.status in WIP for job in self.jobs)

    def _move(self, job, status, at, actor):
        self.events.append({"id": f"{job.issue}-E{len(self.events) + 1:03d}", "issue": job.issue,
                            "at": at.isoformat(), "from": job.status, "to": status,
                            "actor": actor, "source": KIND})
        job.status, job.entered_at = status, at
        owners = Counter(job.owner for job in self.jobs if job.status == "In progress")
        row = {"data_kind": KIND, "at_utc": at.isoformat(), "Review": self._count("Review"),
               "In progress": self._count("In progress"), "active": self._active(), "per_owner": dict(owners)}
        limits = self.config["limits"]
        if (row["Review"] > limits["review"] or row["active"] > limits["active_team"]
                or any(n > limits["in_progress_per_owner"] for n in owners.values())):
            raise ValueError("The simulated transition would violate a WIP limit")
        self.trace.append(row)

    def _first(self, status, owner=None):
        candidates = [job for job in self.jobs if job.status == status and (owner is None or job.owner == owner)]
        return min(candidates, key=lambda job: (job.entered_at, job.issue)) if candidates else None

    def _settle(self, at):
        if self.reviewer is not None and self.reviewer.remaining == 0:
            self._move(self.reviewer, "Done", at, "Reviewer")
            self.reviewer = None
        if self.tester is not None and self.tester.remaining == 0 and self._count("Review") < self.config["limits"]["review"]:
            self._move(self.tester, "Review", at, "QA")
            self.tester = None
        for owner, job in self.developers.items():
            if job is not None and job.remaining == 0:
                self._move(job, "FOR TEST", at, owner)
                self.developers[owner] = None

    def _dispatch(self, at):
        if self.tester is None:
            self.tester = self._first("FOR TEST")
            if self.tester is not None:
                self.tester.remaining = self.config["qa_ticks"]
        if self.reviewer is None and at.strftime("%H:%M") in self.slots:
            self.reviewer = self._first("Review")
            if self.reviewer is not None:
                self.reviewer.remaining = self.config["review_ticks"]
                self.services.append({"data_kind": KIND, "issue": self.reviewer.issue,
                                      "review_started_at_utc": at.isoformat(),
                                      "review_finished_at_utc": (at + self.config["review_ticks"] * TICK).isoformat()})
        self._start_developers(at)

    def _start_developers(self, at):
        limits = self.config["limits"]
        for owner in self.developers:
            if self.developers[owner] is None and self._count("Review") < limits["review"] and self._active() < limits["active_team"]:
                job = self._first("Ready", owner)
                if job is not None:
                    self._move(job, "In progress", at, owner)
                    job.remaining = job.effort_ticks
                    self.developers[owner] = job

    def _advance(self):
        active = [*self.developers.values(), self.tester, self.reviewer]
        for job in active:
            if job is not None and job.remaining > 0:
                job.remaining -= 1

    def run(self):
        for job in self.jobs:
            self._move(job, "Backlog", self.start, "Facilitator")
        cursor = self.start
        while cursor <= self.end:
            if cursor == self.start + timedelta(hours=9):
                for job in self.jobs:
                    self._move(job, "Ready", cursor, "Facilitator")
            self._settle(cursor)
            if cursor.weekday() < 5 and 9 <= cursor.hour < 18:
                self._dispatch(cursor)
                self._advance()
            cursor += TICK
        if any(job.status != "Done" for job in self.jobs):
            raise ValueError("The scenario did not finish within its sprint; no automatic completion is inserted")
        return self


def validate_config(config):
    if config.get("data_kind") != KIND or len(config["sprints"]) != 2:
        raise ValueError("Expected an explicitly labelled two-sprint simulation")
    start = stamp(config["sprints"][0]["start_utc"])
    second = stamp(config["sprints"][1]["start_utc"])
    if start.weekday() != 0 or second != start + timedelta(days=7):
        raise ValueError("The two model weeks must start on consecutive Mondays")
    if any(len(row["tasks"]) != len(config["effort_ticks"]) for row in config["sprints"]):
        raise ValueError("Both sprints must use the same effort vector")
    if any(not isinstance(n, int) or n < 1 for n in [*config["effort_ticks"], config["qa_ticks"], config["review_ticks"]]):
        raise ValueError("Service durations must be positive 15-minute ticks")
    schedules = [config["review_slots_before"], config["review_slots_after"]]
    if len(schedules[0]) != len(schedules[1]):
        raise ValueError("The intervention must preserve daily reviewer capacity")
    if len(schedules[0]) != 2 or config["review_ticks"] != 2:
        raise ValueError("This experiment reserves exactly two 30-minute review slots daily")
    if config["tick_minutes"] != 15:
        raise ValueError("This model uses 15-minute ticks")
    for schedule in schedules:
        _validate_slots(schedule)


def _validate_slots(schedule):
    minutes = sorted(datetime.strptime(value, "%H:%M").hour * 60 + datetime.strptime(value, "%H:%M").minute
                     for value in schedule)
    if any(value % 15 or value < 9 * 60 or value + 30 > 18 * 60 for value in minutes):
        raise ValueError("Review slots must fit the model workday and tick boundaries")
    if any(right < left + 30 for left, right in zip(minutes, minutes[1:])):
        raise ValueError("Overlapping slots would not preserve the declared reviewer capacity")


def facts_for(runs):
    items, metadata, issues, events = [], [], [], []
    for run in runs:
        events.extend(run.events)
        for job in run.jobs:
            issues.append({"number": job.issue, "title": job.title, "owner": job.owner})
            items.append({"id": job.issue, "status": job.status, "owner": job.owner,
                          "content": {"type": "Issue", "number": job.issue, "repository": MODEL_REPO}})
            metadata.append({"issue": job.issue, "created_at": run.start.isoformat(), "repository": MODEL_REPO})
    return {"schema_version": 1, "data_kind": KIND, "real_events": False,
            "repository": MODEL_REPO, "project": {"id": "SIM-LZ09", "url": "synthetic:LZ09"},
            "project_evidence": "simulation", "membership_scope": "Explicit synthetic task cohort",
            "captured_at_utc": max(run.end for run in runs).isoformat(),
            "timestamp_basis": "Virtual model clock, not a real-world observation timestamp",
            "issues": issues, "project_items": items, "project_item_metadata": metadata,
            "project_items_truncated": False, "truncated_timelines": [],
            "transitions": sorted(events, key=lambda row: stamp(row["at"]))}


def experiment(config):
    validate_config(config)
    first = SprintSimulation(config, 0, config["review_slots_before"]).run()
    second = SprintSimulation(config, 1, config["review_slots_after"]).run()
    unchanged = SprintSimulation(config, 1, config["review_slots_before"]).run()
    facts = facts_for([first, second])
    periods = [flow(facts, run.start, run.end) for run in (first, second)]
    counterfactual = flow(facts_for([unchanged]), unchanged.start, unchanged.end)
    return {"runs": (first, second), "facts": facts, "periods": periods,
            "counterfactual": counterfactual, "counterfactual_facts": facts_for([unchanged])}


def hourly_cfd(facts, start, end):
    events = iter(sorted(facts["transitions"], key=lambda row: stamp(row["at"])))
    pending = next(events, None)
    states, rows = {}, []
    cursor = start
    while cursor < end:
        while pending is not None and stamp(pending["at"]) <= cursor:
            states[pending["issue"]] = pending["to"]
            pending = next(events, None)
        counts = Counter(states.values())
        rows.append({"data_kind": KIND, "at_utc": cursor.isoformat(), "date": cursor.date().isoformat(),
                     **{status: counts[status] for status in STATUSES}, "tracked_items": len(states)})
        cursor += timedelta(hours=1)
    return rows


def _percent_change(before, after):
    return 100 * (after - before) / before if before else None


def effects(result):
    first, second = result["periods"]
    before_review = first["observed_status_task_days"]["Review"] / first["throughput"]
    after_review = second["observed_status_task_days"]["Review"] / second["throughput"]
    return {"data_kind": KIND, "changed_parameter": "distribution of two daily review slots",
            "daily_review_minutes_before": 60, "daily_review_minutes_after": 60,
            "review_mean_hours_before": before_review * 24, "review_mean_hours_after": after_review * 24,
            "review_mean_change_percent": _percent_change(before_review, after_review),
            "cycle_mean_change_percent": _percent_change(first["cycle_mean_days"], second["cycle_mean_days"]),
            "cycle_p85_change_percent": _percent_change(first["cycle_p85_days"], second["cycle_p85_days"]),
            "wip_change_percent": _percent_change(first["average_wip"], second["average_wip"]),
            "throughput_change": second["throughput"] - first["throughput"],
            "causal_scope": "Controlled deterministic model with identical effort and arrivals; not an observed team productivity effect"}


def _summary(result):
    return {"data_kind": KIND, "periods": [{"throughput": row["throughput"],
            "cycle_mean_hours": row["cycle_mean_days"] * 24, "p85_hours": row["cycle_p85_days"] * 24,
            "average_wip": row["average_wip"], "little_difference": row["little_wip_difference"]}
            for row in result["periods"]], "effect": effects(result)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", type=Path, default=ROOT / "docs/labs/lab-09/simulation/scenario.json")
    args = parser.parse_args()
    print(json.dumps(_summary(experiment(json.loads(args.scenario.read_text()))), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
