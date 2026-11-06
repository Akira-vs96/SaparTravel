"""Export the dated lab 10 course scenario without changing GitHub evidence."""
import argparse
from collections import defaultdict
import csv
from datetime import datetime, timedelta
import hashlib
from html import escape
import io
import json
import math
from pathlib import Path

from scripts.course.metrics import dora, stamp
from scripts.course.practice import KIND, ROOT, calculate_exercise

DIRECTORY = ROOT / "docs/labs/lab-10/practice"


def analyse(config):
    result = calculate_exercise(10, config)
    start, end = stamp(config["start"]), stamp(config["end"])
    capacity = config["capacity"]
    if not math.isclose((end - start).total_seconds() / 604800, capacity["weeks"]):
        raise ValueError("Capacity weeks must match the reporting window")
    planned = capacity["people"] * capacity["weeks"] * capacity["hours_per_person_per_week"]
    if planned <= 0 or not math.isclose(planned, config["team_capacity_hours"]):
        raise ValueError("Capacity must match people, weeks and weekly hours")
    releases = {row["id"]: row for row in config["facts"]["deployments"]}
    if len(releases) != len(config["facts"]["deployments"]):
        raise ValueError("Deployment IDs must be unique")
    for release in releases.values():
        if not start <= stamp(release["commit_at"]) <= stamp(release["created_at"]) <= stamp(release["finished_at"]) < end:
            raise ValueError("Invalid deployment chronology")
    incidents = {row["id"]: row for row in config["incidents"]}
    if len(incidents) != len(config["incidents"]):
        raise ValueError("Incident IDs must be unique")
    for incident in incidents.values():
        release = releases.get(incident["deployment_id"])
        if release is None:
            raise ValueError("Unknown incident deployment")
        delay = stamp(incident["started_at"]) - stamp(release["finished_at"])
        if not timedelta(0) <= delay <= timedelta(days=1):
            raise ValueError("Incident must follow deployment within one day")
        if not stamp(incident["started_at"]) < stamp(incident["recovered_at"]) < end:
            raise ValueError("Invalid recovery chronology")
    hours = defaultdict(float)
    worklog = []
    for row in config["repair_worklog"]:
        incident = incidents.get(row["incident_id"])
        if incident is None:
            raise ValueError("Unknown worklog incident")
        left, right = stamp(row["started_at"]), stamp(row["finished_at"])
        if not stamp(incident["started_at"]) <= left < right < end:
            raise ValueError("Invalid repair work chronology")
        duration = (right - left).total_seconds() / 3600
        hours[row["incident_id"]] += duration
        worklog.append({**row, "person_hours": round(duration, 6)})
    for identifier, incident in incidents.items():
        if not math.isclose(hours[identifier], incident["repair_labor_hours"]):
            raise ValueError("Incident labor must match the worklog")
    if result["repair_labor_hours"] > planned:
        raise ValueError("Repair work exceeds capacity")
    policy = config["merge_policy"]
    attempts = []
    for row in config["merge_attempts"]:
        if row["actor"] != "non-admin" or not start <= stamp(row["at"]) < end:
            raise ValueError("Expected a non-admin policy case inside the window")
        blockers = [name for name in policy["required_checks"] if row["checks"].get(name) != "success"]
        if row["review_count"] < policy["required_approvals"]:
            blockers.append("review")
        outcome = "blocked" if blockers else "allowed"
        if row["expected"] != outcome:
            raise ValueError("Merge expectation contradicts required checks and review")
        attempts.append({**row, "calculated": outcome, "blockers": blockers})
    weekly = []
    local_start = datetime.fromisoformat(config["start"])
    for index in range(capacity["weeks"]):
        left = local_start + timedelta(weeks=index)
        right = left + timedelta(weeks=1)
        weekly.append({"week": index + 1, "from": left.date().isoformat(),
                       "through": (right - timedelta(days=1)).date().isoformat(),
                       **dora(config["facts"], stamp(left.isoformat()), stamp(right.isoformat()), config["incidents"], True)})
    return {"data_kind": KIND, "human_events_confirmed": False, "summary": result,
            "weekly": weekly, "worklog": worklog, "merge_attempts": attempts}


def json_text(value):
    return json.dumps(value, ensure_ascii=False, indent=2) + "\n"


def csv_text(rows, fields):
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fields, extrasaction="ignore", lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue()


def table(headers, rows):
    heading = "".join(f"<th scope='col'>{escape(str(value))}</th>" for value in headers)
    body = "".join("<tr>" + "".join(f"<td>{escape(str(value))}</td>" for value in row) + "</tr>" for row in rows)
    return f"<div class='scroll'><table><thead><tr>{heading}</tr></thead><tbody>{body}</tbody></table></div>"


def dashboard(config, report):
    summary = report["summary"]
    first = datetime.fromisoformat(config["start"]).strftime("%d.%m.%Y")
    last = (datetime.fromisoformat(config["end"]) - timedelta(days=1)).strftime("%d.%m.%Y")
    metrics = [("Выпусков в неделю", summary["deployment_frequency_per_week"]),
               ("От коммита до стенда, ч", summary["lead_time_median_hours"]),
               ("Неудачных изменений, %", summary["change_failure_rate_percent"]),
               ("Восстановление, мин", summary["recovery_median_minutes"])]
    cards = "".join(f"<article><p>{label}</p><strong>{value:g}</strong></article>" for label, value in metrics)
    weeks = table(["Неделя", "Период", "Выпуски", "Lead time p50, ч", "CFR, %", "Восстановление p50, мин"],
                  [(row["week"], f'{row["from"]} — {row["through"]}', row["deployment_count"],
                    row["lead_time_median_hours"], row["change_failure_rate_percent"],
                    row["recovery_median_minutes"] if row["recovery_median_minutes"] is not None else "нет инцидентов")
                   for row in report["weekly"]])
    releases = table(["Выпуск", "Стенд готов, UTC+5", "Содержание"],
                     [(row["id"], stamp(row["finished_at"]).astimezone(datetime.fromisoformat(config["start"]).tzinfo).strftime("%d.%m.%Y %H:%M"), row["scope"])
                      for row in config["facts"]["deployments"]])
    incidents = table(["Инцидент", "Выпуск", "Восстановление, мин", "Исправления, чел.-ч"],
                      [(row["id"], row["deployment_id"],
                        (stamp(row["recovered_at"]) - stamp(row["started_at"])).total_seconds() / 60,
                        row["repair_labor_hours"]) for row in config["incidents"]])
    merges = table(["Проверка", "CI backend", "Одобрения", "Результат", "Причина блокировки"],
                   [(row["id"], row["checks"]["backend"], row["review_count"], row["calculated"],
                     ", ".join(row["blockers"]) or "—") for row in report["merge_attempts"]])
    return f"""<!doctype html>
<html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="data-kind" content="{KIND}"><title>SaparTravel · история поставки</title>
<style>
*{{box-sizing:border-box}}body{{margin:0;background:#f4f7fa;color:#193345;font:16px/1.6 system-ui,sans-serif}}
main{{max-width:1160px;margin:auto;padding:32px 20px}}h1{{font-size:clamp(26px,5vw,40px);margin:8px 0}}
h2{{font-size:22px;margin-top:36px}}a{{color:#0b6863}}.kpis{{display:grid;grid-template-columns:repeat(4,1fr);gap:14px}}
article{{background:white;padding:20px;border:1px solid #d6e0e7;border-radius:12px}}article p{{margin:0;font-size:14px}}
strong{{font-size:36px;color:#0b6863}}.scroll{{overflow-x:auto;border:1px solid #d6e0e7;border-radius:10px;background:white}}
table{{border-collapse:collapse;width:100%;font-size:14px}}td,th{{text-align:left;padding:12px;border-bottom:1px solid #e5ecf0}}
th{{background:#e7eff1}}footer{{margin-top:36px;color:#506674;font-size:14px}}
@media(max-width:760px){{.kpis{{grid-template-columns:repeat(2,1fr)}}}}@media(max-width:380px){{.kpis{{grid-template-columns:1fr}}}}
</style></head><body><main>
<a href="README.md">Отчёт лабораторной №10</a><h1>SaparTravel · история поставки</h1>
<p>{first} — {last} · {config['capacity']['weeks']} недель · именованный учебный стенд</p>
<section class="kpis" aria-label="Четыре метрики DORA">{cards}</section>
<p>{summary['deployment_count']} выпусков · {len(config['incidents'])} инцидента ·
{summary['repair_labor_hours']:g} человеко-часов исправлений из {config['team_capacity_hours']:g} часов capacity:
{summary['reliability_capacity_fraction'] * 100:g}%.</p>
<h2>Динамика по неделям</h2>{weeks}<h2>Журнал выпусков</h2>{releases}
<h2>Инциденты и трудозатраты</h2>{incidents}
<h2>Правила слияния для участника без прав администратора</h2>{merges}
<p>Для администратора сохранено разрешение прямого push. Таблица вычисляет политику по состояниям CI и ревью.</p>
<footer>Источник: <a href="scenario.json">учебный сценарий</a> · <a href="results.json">расчёт</a> ·
<a href="provenance.json">происхождение данных</a>. Времена восстановлений и трудозатраты учитываются отдельно.
Сохранённые GitHub-события находятся в соседнем разделе evidence.</footer>
</main></body></html>
"""


def artifacts(config, report, source_bytes):
    labels = {"data_kind": KIND, "human_events_confirmed": False}
    exports = {
        "deployments.csv": csv_text(config["facts"]["deployments"],
                                    ["id", "environment", "state", "commit_at", "created_at", "finished_at", "scope"]),
        "incidents.csv": csv_text(config["incidents"],
                                  ["id", "deployment_id", "started_at", "recovered_at", "repair_labor_hours", "symptom", "resolution"]),
        "repair-hours.csv": csv_text(report["worklog"],
                                     ["incident_id", "role", "started_at", "finished_at", "person_hours", "activity"]),
        "merge-checks.json": json_text({**labels, "policy": config["merge_policy"], "attempts": report["merge_attempts"],
                                       "github_merge_attempt_performed": False}),
        "weekly.json": json_text({**labels, "weeks": report["weekly"]}),
        "dashboard.html": dashboard(config, report),
    }
    exports["provenance.json"] = json_text({**labels, **config["provenance"],
                                          "scenario_sha256": hashlib.sha256(source_bytes).hexdigest(),
                                          "generator_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                                          "artifact_sha256": {name: hashlib.sha256(content.encode()).hexdigest()
                                                              for name, content in exports.items()}})
    return exports


def build(directory=DIRECTORY, *, check=False):
    source_bytes = (directory / "scenario.json").read_bytes()
    config = json.loads(source_bytes)
    report = analyse(config)
    exports = artifacts(config, report, source_bytes)
    for name, content in exports.items():
        target = directory / name
        if check:
            if not target.is_file() or target.read_text() != content:
                raise ValueError(f"Stale lab 10 export: {name}")
        else:
            target.write_text(content)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    report = build(check=args.check)
    print(json_text({"data_kind": KIND, "summary": report["summary"],
                     "merge_cases": len(report["merge_attempts"])}))


if __name__ == "__main__":
    main()
