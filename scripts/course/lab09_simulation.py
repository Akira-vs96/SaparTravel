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


def bottleneck(result):
    rows = []
    for number, (run, metrics) in enumerate(zip(result["runs"], result["periods"]), 1):
        full_hours = sum((stamp(right["at_utc"]) - stamp(left["at_utc"])).total_seconds() / 3600
                         for left, right in zip(run.trace, run.trace[1:]) if left["Review"] == 3)
        stage_hours = {status: metrics["observed_status_task_days"][status] * 24 for status in WIP}
        rows.append({"sprint": number, "dominant_stage": max(stage_hours, key=stage_hours.get),
                     "stage_elapsed_task_hours": stage_hours, "review_full_elapsed_hours": full_hours,
                     "review_share_of_cycle_time": stage_hours["Review"] / sum(stage_hours.values()),
                     "peak_review": max(row["Review"] for row in run.trace),
                     "peak_active": max(row["active"] for row in run.trace),
                     "peak_in_progress_per_owner": max(n for row in run.trace for n in row["per_owner"].values()),
                     "review_service_hours": len(run.services) * .5, "reserved_review_hours": 5.0})
    return {"data_kind": KIND, "stage": "Review", "periods": rows,
            "explanation": "The reviewer consumes all five reserved hours per week; the review band reaches its WIP cap and dominates elapsed cycle time."}


def process_action(result, config):
    change = effects(result)
    deadline = result["runs"][1].end - timedelta(days=2, hours=7)
    return {"data_kind": KIND, "actions": [{"id": "SIM-ACTION-01", "owner": "Reviewer (virtual role)",
            "description": "Split the existing hour of daily review into two half-hour windows",
            "before_slots_utc": config["review_slots_before"], "after_slots_utc": config["review_slots_after"],
            "deadline_virtual_utc": deadline.isoformat(), "target": "Reduce mean time in Review by at least 10%",
            "target_achieved": change["review_mean_change_percent"] <= -10,
            "measured_review_change_percent": change["review_mean_change_percent"],
            "decision_in_model": "Hypothesis supported" if change["review_mean_change_percent"] <= -10 else "Hypothesis not supported; do not claim a productivity improvement"}],
            "retrospective_duration_model_minutes": 30, "real_meeting_confirmed": False}


def _csv(path, rows):
    labelled = [{"data_kind": KIND, **row} for row in rows]
    write_csv(path, labelled, list(labelled[0]))


def export_evidence(result, config, output):
    evidence = output / "evidence"
    evidence.mkdir(parents=True, exist_ok=True)
    facts = result["facts"]
    write_json(evidence / "facts.json", facts)
    write_json(evidence / "flow.json", {"data_kind": KIND, "periods": result["periods"],
                                       "simulated_sprints": True, "real_sprints_confirmed": False})
    write_json(evidence / "effect.json", effects(result))
    write_json(evidence / "action.json", process_action(result, config))
    write_json(evidence / "bottleneck.json", bottleneck(result))
    write_json(evidence / "counterfactual.json", {"data_kind": KIND, "policy": "Sprint 2 with unchanged review slots",
               "metrics": result["counterfactual"], "facts": result["counterfactual_facts"]})
    write_json(evidence / "wip-trace.json", {"data_kind": KIND, "events": [row for run in result["runs"] for row in run.trace]})
    _csv(evidence / "transitions.csv", [{"issue": row["issue"], "at_utc": row["at"], "from": row["from"],
          "to": row["to"], "actor": row["actor"], "event_id": row["id"]} for row in facts["transitions"]])
    _csv(evidence / "review-services.csv", [row for run in result["runs"] for row in run.services])
    _export_metrics(result, evidence)
    _export_details(result, evidence)
    for number, run in enumerate(result["runs"], 1):
        rows = hourly_cfd(facts_for([run]), run.start, run.end)
        write_json(evidence / f"cfd-sprint-{number}.json", {"data_kind": KIND, "sample_hours": 1, "rows": rows})
        _csv(evidence / f"cfd-sprint-{number}.csv", rows)


def _export_metrics(result, evidence):
    comparison, cycles = [], []
    for number, metrics in enumerate(result["periods"], 1):
        comparison.append({"sprint": number, "start_virtual_utc": metrics["start_utc"], "end_virtual_utc": metrics["end_utc"],
                           "throughput": metrics["throughput"], "cycle_mean_hours": metrics["cycle_mean_days"] * 24,
                           "cycle_p85_hours": metrics["cycle_p85_days"] * 24, "average_wip": metrics["average_wip"],
                           "calendar_days": metrics["calendar_days"], "working_days": metrics["working_time"]["working_days"],
                           "working_average_wip": metrics["working_time"]["average_wip"],
                           "little_expected_wip": metrics["little_expected_wip"], "little_difference": metrics["little_wip_difference"]})
        cycles.extend({"sprint": number, **row, "cycle_hours": row["cycle_days"] * 24} for row in metrics["completed_items"])
    _csv(evidence / "comparison.csv", comparison)
    _csv(evidence / "cycles.csv", cycles)


def _export_details(result, evidence):
    first, last = result["runs"]
    details = flow_details(result["facts"], first.start, last.end)
    write_json(evidence / "item-times.json", {"data_kind": KIND, "items": details["items"]})
    write_json(evidence / "daily-wip.json", {"data_kind": KIND, "rows": details["daily_wip"]})
    _csv(evidence / "item-times.csv", [{"issue": row["issue"],
          **{f"{status}_hours": days * 24 for status, days in row["status_task_days"].items()}}
         for row in details["items"]])
    _csv(evidence / "daily-wip.csv", [{"date_virtual_utc": row["date"], "average_wip": row["average_wip"],
          **{f"{status}_hours": days * 24 for status, days in row["status_task_days"].items()}}
         for row in details["daily_wip"]])


def acceptance(result, config):
    periods = result["periods"]
    queues = bottleneck(result)
    checks = {"two_weekly_sprints": len(periods) == 2 and all(row["calendar_days"] == 7 for row in periods),
              "goals_written": all(row["goal"] for row in config["sprints"]),
              "all_tasks_completed": all(row["throughput"] == len(config["effort_ticks"]) for row in periods),
              "complete_status_history": all(row["data_quality"]["coverage_complete"] for row in periods),
              "cycle_mean_and_p85": all(row["cycle_time_samples"] == row["throughput"] for row in periods),
              "little_calendar_and_working": all(abs(row["little_wip_difference"]) < 1e-9
                    and abs(row["working_time"]["little_wip_difference"]) < 1e-9 for row in periods),
              "wip_limits": all(row["peak_review"] <= 3 and row["peak_active"] <= 8
                    and row["peak_in_progress_per_owner"] <= 2 for row in queues["periods"]),
              "bottleneck_from_data": all(row["dominant_stage"] == "Review" and row["review_full_elapsed_hours"] > 0 for row in queues["periods"]),
              "one_action": len(process_action(result, config)["actions"]) == 1,
              "capacity_unchanged": len(config["review_slots_before"]) == len(config["review_slots_after"]),
              "counterfactual": abs(result["counterfactual"]["cycle_mean_days"] - periods[0]["cycle_mean_days"]) < 1e-9,
              "effect_measured": effects(result)["cycle_mean_change_percent"] is not None}
    evidence = {"S01": "../../../project-board-workflow.md", "S02": "evidence/wip-trace.json", "S03": "sprint-1.md",
                "S04": "sprint-1.md", "S05": "evidence/transitions.csv", "S06": "evidence/facts.json",
                "S07": "evidence/comparison.csv", "S08": "evidence/flow.json", "S09": "evidence/bottleneck.json",
                "S10": "retrospective.md", "S11": "evidence/action.json", "S12": "sprint-2.md",
                "C01": "evidence/transitions.csv", "C02": "sprint-2.md", "C03": "evidence/cycles.csv",
                "C04": "evidence/bottleneck.json", "C05": "evidence/effect.json"}
    complete = all(checks.values())
    return {"data_kind": KIND, "simulation_complete": complete, "real_sprints_confirmed": False,
            "real_meeting_confirmed": False, "checks": checks,
            "requirements": [{"id": "LZ09-" + key, "status": "fulfilled_in_simulation" if complete else "needs_model_fix", "evidence": value}
                             for key, value in evidence.items()]}


def _sprint_document(result, config, number):
    index = number - 1
    run, metrics = result["runs"][index], result["periods"][index]
    slots = config["review_slots_before"] if number == 1 else config["review_slots_after"]
    lines = [f"# Спринт {number} — учебная симуляция", "", "Модельные события и виртуальные роли. Реальная работа команды этим документом не удостоверяется.", "",
             f"Виртуальное окно UTC: {run.start.date()} — {run.end.date()} (конец исключён). Планирование: понедельник 08:30–09:00 в виртуальном времени.", "",
             "## Пользовательская цель", "", config["sprints"][index]["goal"], "",
             "## План и правила", "",
             f"Выбрано 10 модельных задач. Ревью: {', '.join(slots)} UTC; суммарно 60 минут в день. Разработчики A/B, QA и Reviewer — виртуальные роли. WIP: ≤2 In progress на владельца, ≤3 Review, ≤8 активных задач на команду.", "",
             "DoR: цель, владелец, размер, критерий приёмки, зависимости известны. DoD в модели: реализация, успешная модельная QA-проверка, ревью другой виртуальной ролью, публикация на виртуальном стенде и обновление модельной документации. Сбои и возвраты в этом контролируемом опыте не вводятся; DoD не является заявлением о реальном стенде.", "",
             "## Результаты задач", "", "| ID | Задача | Владелец | Работа, ч | Начало цикла, UTC | Done, UTC | Цикл, ч |", "|---|---|---|---:|---|---|---:|"]
    completed = {row["issue"]: row for row in metrics["completed_items"]}
    for job in run.jobs:
        row = completed[job.issue]
        lines.append(f"| {job.issue} | {job.title} | {job.owner} | {job.effort_ticks / 4:g} | {row['started_at_utc'][:16]} | {row['completed_at_utc'][:16]} | {row['cycle_days'] * 24:.2f} |")
    lines += ["", f"Итог модели: завершено {metrics['throughput']}; среднее {metrics['cycle_mean_days'] * 24:.3f} ч, p85 {metrics['cycle_p85_days'] * 24:.3f} ч; средний WIP {metrics['average_wip']:.6f}.", "",
              "Модельная демонстрация проверяет заявленный пользовательский результат по набору задач и принятым допущениям; реальные браузерные сценарии здесь не запускались.", "",
              f"![Модельная CFD](evidence/cfd-sprint-{number}.png)", "", "[Общий отчёт и сравнение](README.md) · [Циклы всех задач](evidence/cycles.csv)", ""]
    return "\n".join(lines)


def _retrospective_document(result, config):
    change = effects(result)
    action = process_action(result, config)["actions"][0]
    date = result["runs"][0].end - timedelta(days=3)
    return f'''# Ретроспектива — учебная симуляция

Это модельный протокол, сформированный сценарием. Реальной встречи и подписей участников он не подтверждает.

Виртуальное время: {date.date()}, 17:15–17:45 UTC, 30 минут. Роли: Developer A, Developer B, QA, Reviewer/фасилитатор.

| Минуты | Обсуждение в модели | Итог |
|---|---|---|
| 0–5 | Цель первого спринта и десять завершённых задач | Модельная цель выполнена, история полна |
| 5–15 | Продолжать / прекратить / начать | Предложения ниже |
| 15–25 | Выбор одного изменения | Только SIM-ACTION-01 |
| 25–30 | Владелец, срок, измерение | Reviewer; конец второго спринта; среднее время Review |

«Продолжать»: Developer A — единый DoD и отдельная QA-роль; QA — точные timestamps и WIP-лимиты.
«Прекратить»: Developer B — оценивать поток только по числу закрытых задач: оно скрывает ожидание.
«Начать»: Reviewer — проверять распределение ревью внутри дня при том же часовом бюджете.

## Ровно одно принятое в модели действие

SIM-ACTION-01: распределить существующий час ревью на окна {', '.join(config['review_slots_after'])} UTC вместо {', '.join(config['review_slots_before'])} UTC.
Объём ревью, четыре виртуальные роли, трудоёмкость, поступление задач и WIP-лимиты одинаковы.
Владелец: Reviewer, виртуальная роль. Срок: {action['deadline_virtual_utc']}. Цель гипотезы: сократить среднее время Review хотя бы на 10%.

## Проверенный эффект во втором спринте

Среднее время Review: {change['review_mean_hours_before']:.2f} → {change['review_mean_hours_after']:.2f} ч ({change['review_mean_change_percent']:+.2f}%).
Среднее время цикла: {change['cycle_mean_change_percent']:+.2f}%; p85: {change['cycle_p85_change_percent']:+.2f}%; выпуск: изменение {change['throughput_change']} задач.
Достижение модельной цели: **{'да' if action['target_achieved'] else 'нет'}**. {action['decision_in_model']}.

Это результат одного эксперимента. Новое изменение процесса во время второго спринта не добавлялось.
Контрольный пересчёт второго спринта со старым расписанием воспроизводит первый: [контроль](evidence/counterfactual.json).
Измеренные различия не переносятся на производительность реальной команды.

[Полный разбор механизма](README.md) · [Машинное действие](evidence/action.json) · [Эффект](evidence/effect.json)
'''


def _report_document(result, config, verified):
    first, second = result["periods"]
    change, queues = effects(result), bottleneck(result)
    lines = ["# ЛЗ 9: полная учебная симуляция двух спринтов", "",
             "**Режим: учебная симуляция.** Все SIM-задачи, даты событий и участники модельные. Это законченный учебный разбор; реальные спринты и командные встречи им не подтверждаются.", "",
             "[Основной раздел ЛЗ 9](../README.md) · [Сценарий](scenario.json) · [Исходные события модели](evidence/facts.json) · [Проверка 17 требований](evidence/acceptance.json)", "",
             "## Цели и организация", "",
             f"Спринт 1 ({first['start_utc'][:10]}—{first['end_utc'][:10]}): {config['sprints'][0]['goal']}", "",
             f"Спринт 2 ({second['start_utc'][:10]}—{second['end_utc'][:10]}): {config['sprints'][1]['goal']}", "",
             "[Планирование, DoR/DoD и результаты первого спринта](sprint-1.md) · [Второй спринт](sprint-2.md) · [30-минутная модельная ретроспектива](retrospective.md)", "",
             "## Допущения модели", "",
             "Четыре виртуальные роли: Developer A/B, QA, Reviewer. Дискретный шаг — 15 минут. Работа идёт Пн–Пт 09:00–18:00 UTC. Все десять задач поступают в Ready в понедельник 09:00. На каждый спринт приходится одинаковый вектор трудоёмкости: 21 час реализации, 5 часов QA и 5 часов ревью. Размеры задач и владельцы закреплены; меняются названия пользовательских задач.", "",
             "У каждого разработчика одна одновременно обслуживаемая задача; политика допускает не более двух In progress на владельца. Review ограничен тремя, общий активный WIP — восемью. Новая разработка при полной очереди Review не начинается. QA ждёт места в Review; ожидание и ночные паузы учитываются в длительности статуса. Отпусков, праздников, дефектов и случайных возвратов нет. Начало и конец каждого цикла лежат внутри своего окна.", "",
             f"Единственное изменение: два слота ревью {', '.join(config['review_slots_before'])} заменены на {', '.join(config['review_slots_after'])} UTC. Сохраняются один Reviewer и 60 минут ревью в день. Гипотеза — среднее время Review уменьшится не менее чем на 10%.", "",
             "## Сравнение по данным модели", "", "| Показатель | Спринт 1 | Спринт 2 |", "|---|---:|---:|"]
    pairs = [("Throughput, задач", first["throughput"], second["throughput"]),
             ("Среднее время цикла, ч", first["cycle_mean_days"] * 24, second["cycle_mean_days"] * 24),
             ("p85 времени цикла, ч", first["cycle_p85_days"] * 24, second["cycle_p85_days"] * 24),
             ("Средний WIP, календарная шкала", first["average_wip"], second["average_wip"]),
             ("Средний WIP, Пн–Пт", first["working_time"]["average_wip"], second["working_time"]["average_wip"]),
             ("Среднее время в Review, ч", change["review_mean_hours_before"], change["review_mean_hours_after"]),
             ("Достоверных cycle samples", first["cycle_time_samples"], second["cycle_time_samples"])]
    lines += [f"| {name} | {before:.6g} | {after:.6g} |" for name, before, after in pairs]
    lines += ["", "[Сравнение CSV](evidence/comparison.csv) · [Цикл каждой задачи](evidence/cycles.csv) · [Время по статусам](evidence/item-times.csv) · [Средний WIP по дням](evidence/daily-wip.csv) · [Все переходы](evidence/transitions.csv)", "",
              "Часы здесь — прошедшее время цикла, включая ожидание и ночные перерывы. Трудозатраты из сценария приведены отдельно. p85 рассчитан линейной интерполяцией Calc PERCENTILE.INC. Рабочая шкала использует 24-часовые дни Пн–Пт без праздников; единицы не смешиваются с календарными.", "",
              "## Закон Литтла", ""]
    for number, row in enumerate(result["periods"], 1):
        working = row["working_time"]
        lines += [f"Спринт {number}: календарно {row['throughput']}/7 × {row['cycle_mean_days']:.6f} = {row['little_expected_wip']:.6f}; интеграл WIP даёт {row['average_wip']:.6f}.", "",
                  f"По рабочим дням: {row['throughput']}/5 × {working['cycle_mean_days']:.6f} = {working['little_expected_wip']:.6f}; наблюдаемый WIP {working['average_wip']:.6f}.", ""]
    lines += ["Невязки меньше 1e−9. В этой модели это учётное равенство закрытого набора задач: все циклы полностью внутри окон и незавершённого WIP на границах нет. Оно проверяет согласованность расчётов и не доказывает долгосрочную стационарность реальной команды.", "",
              "## Узкое место и CFD", "",
              f"Review достигает лимита 3, использует все 5 выделенных часов ревью за неделю и занимает {queues['periods'][0]['review_share_of_cycle_time'] * 100:.2f}% суммарного времени цикла в первом спринте. Это наибольшая полоса активного времени; очередь определяется по данным, а не по названию роли. Часовые срезы показывают внутридневное накопление, которое полуночный срез скрывает.", "",
              "![CFD первого спринта — симуляция](evidence/cfd-sprint-1.png)", "", "![CFD второго спринта — симуляция](evidence/cfd-sprint-2.png)", "",
              "[Числа по узкому месту](evidence/bottleneck.json) · [Срезы CFD 1](evidence/cfd-sprint-1.csv) · [Срезы CFD 2](evidence/cfd-sprint-2.csv) · [Контроль WIP после каждого перехода](evidence/wip-trace.json)", "",
              "## Что дало одно изменение", "",
              f"Выпуск остался 10 задач. Среднее время цикла изменилось на {change['cycle_mean_change_percent']:+.2f}%, p85 — на {change['cycle_p85_change_percent']:+.2f}%, среднее время Review — на {change['review_mean_change_percent']:+.2f}%. Поэтому общий вывод «стали работать лучше» из этих чисел не следует.", "",
              "Раннее окно завершает первые проверки раньше и меняет момент освобождения WIP. Другие задачи попадают в очереди раньше, но Reviewer по-прежнему может принять только две задачи в день. Ожидание перераспределяется между стадиями; общий выпуск остаётся ограничен той же ёмкостью.", "",
              "| Стадия | Суммарное прошедшее время задач S1, ч | S2, ч | Изменение, ч |", "|---|---:|---:|---:|"]
    for status in ("In progress", "FOR TEST", "Review"):
        before, after = (row["observed_status_task_days"][status] * 24 for row in (first, second))
        lines.append(f"| {status} | {before:.2f} | {after:.2f} | {after - before:+.2f} |")
    decision = process_action(result, config)["actions"][0]
    lines += ["", f"Цель гипотезы достигнута: **{'да' if decision['target_achieved'] else 'нет'}**. Модельный результат сохраняется даже при неудачном эффекте. Среднее, хвост распределения и выпуск рассматриваются вместе.", "",
              f"Контроль: второй спринт со старым расписанием даёт среднее {result['counterfactual']['cycle_mean_days'] * 24:.3f} ч и воспроизводит первый спринт. Состав ресурсов, входной поток и трудоёмкость совпадают; в детерминированной модели различие вызвано распределением слотов. Это модельная причинность, а не измерение эффективности реальной команды.", "",
              "[Эффект](evidence/effect.json) · [Контрольный сценарий](evidence/counterfactual.json) · [Единственное действие](evidence/action.json)", "",
              "## Все требования ЛЗ 9", "", "| Требование | Результат учебной симуляции | Доказательство |", "|---|---|---|"]
    for row in verified["requirements"]:
        lines.append(f"| {row['id']} | Выполнено в модели | [Артефакт]({row['evidence']}) |")
    lines += ["", "## Воспроизведение", "", "Из корня репозитория:", "", "```bash",
              ".venv/bin/python -m scripts.course.lab09_simulation --scenario docs/labs/lab-09/simulation/scenario.json --output docs/labs/lab-09/simulation",
              ".venv/bin/python -m unittest tests.course.test_lab09_simulation -v", "```", "",
              "Весь вход модели — в сценарии; случайных чисел нет. [Происхождение и контрольные суммы](evidence/provenance.json) связывают сценарий, код и события. Поле simulation_complete относится только к учебному варианту. Реальная история и журнал находятся в родительском разделе и не изменяются генератором.", ""]
    return "\n".join(lines)


def build(scenario, output, *, plot=True):
    for name in ("evidence", "journal"):
        actual = (ROOT / "docs/labs/lab-09" / name).resolve()
        if output.resolve().is_relative_to(actual):
            raise ValueError("Simulation output cannot overwrite real Lab 9 history")
    raw = scenario.read_bytes()
    config = json.loads(raw)
    result = experiment(config)
    verified = acceptance(result, config)
    if not verified["simulation_complete"]:
        raise ValueError("Simulation requirements did not pass: " + str(verified["checks"]))
    output.mkdir(parents=True, exist_ok=True)
    if (output / "scenario.json").resolve() != scenario.resolve():
        (output / "scenario.json").write_bytes(raw)
    export_evidence(result, config, output)
    if plot:
        for number, run in enumerate(result["runs"], 1):
            rows = hourly_cfd(facts_for([run]), run.start, run.end)
            plot_cfd(rows, output / f"evidence/cfd-sprint-{number}.png",
                     title=f"SIMULATION: Sprint {number} — hourly CFD",
                     note="Synthetic tasks and virtual time. No real GitHub transitions or team meetings are represented.")
    for number in (1, 2):
        (output / f"sprint-{number}.md").write_text(_sprint_document(result, config, number))
    (output / "retrospective.md").write_text(_retrospective_document(result, config))
    (output / "README.md").write_text(_report_document(result, config, verified))
    write_json(output / "evidence/acceptance.json", verified)
    write_json(output / "evidence/provenance.json", {"data_kind": KIND,
               "generated_at_utc": datetime.now(timezone.utc).isoformat(),
               "scenario_sha256": hashlib.sha256(raw).hexdigest(),
               "generator_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
               "metrics_sha256": hashlib.sha256((ROOT / "scripts/course/metrics.py").read_bytes()).hexdigest(),
               "facts_sha256": hashlib.sha256((output / "evidence/facts.json").read_bytes()).hexdigest(),
               "randomness": "none; deterministic data, plotting appearance may depend on installed fonts"})
    return _summary(result)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", type=Path, default=ROOT / "docs/labs/lab-09/simulation/scenario.json")
    parser.add_argument("--output", type=Path, default=ROOT / "docs/labs/lab-09/simulation")
    args = parser.parse_args()
    print(json.dumps(build(args.scenario, args.output), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
