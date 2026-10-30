"""Rebuild the complete Lab 9 evidence package from one immutable GitHub snapshot."""
import argparse
from collections import Counter
import csv
from datetime import timedelta
import hashlib
import json
import os
from pathlib import Path

from scripts.course.metrics import STATUSES, cfd, flow, flow_details, stamp


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def plot_cfd(rows, path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.dates as mdates
    import matplotlib.pyplot as plt

    stages = ("Done", "Review", "FOR TEST", "In progress", "Blocked", "Ready", "Backlog", "Unknown")
    dates = [stamp(r["at_utc"]) for r in rows]
    fig, ax = plt.subplots(figsize=(11, 6))
    bands = ax.stackplot(dates, *[[r[s] for r in rows] for s in stages], labels=stages,
                        colors=["#3b956c", "#798bd0", "#b084cc", "#e5b94c", "#d67a79", "#66bfc3", "#9fb9cd", "#dddddd"],
                        step="post", alpha=.9)
    bands[-1].set_hatch("///")
    bands[-1].set_edgecolor("#777777")
    ax.set(xlabel="UTC daily observation", ylabel="Items in the recorded issue cohort",
           title="CFD: recorded states and explicit gaps")
    ax.xaxis.set_major_locator(mdates.AutoDateLocator(minticks=3, maxticks=8))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%d.%m"))
    ax.set_xlim(dates[0], dates[-1] + timedelta(days=1))
    ax.set_ylim(bottom=0)
    ax.legend(loc="upper left", ncols=4)
    fig.text(.05, .025, "Grey hatch = unknown status, not idle work. Daily samples do not locate missing transitions.", fontsize=9)
    fig.tight_layout(rect=(0, .05, 1, 1))
    fig.savefig(path, dpi=160)
    plt.close(fig)


def write_csv(path, rows, fields):
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def write_details(details, periods, output):
    write_json(output / "item-times.json", details["items"])
    write_json(output / "daily-wip.json", details["daily_wip"])
    items = [{"issue": r["issue"], "start_utc": r["start_utc"], "end_utc": r["end_utc"],
              "coverage_complete": r["coverage_complete"],
              **{f"{s}_days": r["status_task_days"][s] for s in STATUSES},
              **{key: (r["completion"] or {}).get(key) for key in ("started_at_utc", "completed_at_utc", "cycle_days", "cycle_weekdays")}}
             for r in details["items"]]
    item_fields = ["issue", "start_utc", "end_utc", "coverage_complete", *[f"{s}_days" for s in STATUSES],
                   "started_at_utc", "completed_at_utc", "cycle_days", "cycle_weekdays"]
    write_csv(output / "item-times.csv", items, item_fields)
    daily = [{**{key: r[key] for key in ("date", "start_utc", "end_utc", "calendar_days", "average_wip", "wip_lower_bound", "wip_upper_bound")},
              **{f"{s}_days": r["status_task_days"][s] for s in STATUSES}}
             for r in details["daily_wip"]]
    write_csv(output / "daily-wip.csv", daily, ["date", "start_utc", "end_utc", "calendar_days", "average_wip", "wip_lower_bound", "wip_upper_bound", *[f"{s}_days" for s in STATUSES]])
    fields = ["start_utc", "end_utc", "throughput", "cycle_time_samples", "cycle_mean_days", "cycle_p85_days", "average_wip", "little_expected_wip", "little_law_evaluable", "little_wip_difference"]
    comparison = [{**{key: r[key] for key in fields},
                   "working_days": r["working_time"]["working_days"],
                   **{f"working_{key}": r["working_time"][key] for key in ("cycle_mean_days", "cycle_p85_days", "average_wip", "little_expected_wip", "little_law_evaluable", "little_wip_difference")}}
                  for r in periods]
    write_csv(output / "comparison.csv", comparison, list(comparison[0]))


def board_policy(facts):
    counts = {s: sum(item.get("status") == s for item in facts.get("project_items", [])) for s in STATUSES}
    review = counts["Review"]
    active = [r for r in facts.get("project_items", []) if r.get("status") == "In progress"]
    owners = Counter(r.get("owner") for r in active if r.get("owner"))
    missing_owner = [(r.get("content") or {}).get("number") for r in active if not r.get("owner")]
    return {"captured_at_utc": facts.get("captured_at_utc"), "status_counts": counts,
            "review_limit": 3, "review_count": review, "review_limit_passed": review <= 3,
            "review_over_limit": max(0, review - 3),
            "review_issues": [(r.get("content") or {}).get("number") for r in facts.get("project_items", []) if r.get("status") == "Review"],
            "per_person_limit": 2, "per_person_historical_check": "not_evaluable_without_historical_assignees",
            "current_in_progress_by_owner": dict(owners), "current_items_without_owner": missing_owner,
            "per_person_current_limit_passed": all(n <= 2 for n in owners.values()) if not missing_owner else None,
            "action": "Finish or explicitly resolve existing review before pulling new work" if review > 3 else "Review queue is within its limit"}


def build(snapshot, start, end, output, *, period_days=7, plot=True):
    if period_days < 1:
        raise ValueError("The observation period must contain at least one day")
    raw = snapshot.read_bytes()
    facts = json.loads(raw)
    overall = flow(facts, start, end)
    rows = cfd(facts, start, end)
    periods, cursor = [], start
    while cursor < end:
        stop = min(cursor + timedelta(days=period_days), end)
        periods.append(flow(facts, cursor, stop))
        cursor = stop
    source = Path(os.path.relpath(snapshot.resolve(), output.resolve())).as_posix()
    source_hash = hashlib.sha256(raw).hexdigest()
    total_days = sum(overall["observed_status_task_days"].values())
    unknown_days = overall["observed_status_task_days"]["Unknown"]
    quality = {**overall["data_quality"], "schema_version": 3,
               "source": source, "source_sha256": source_hash,
               "project": facts.get("project"), "membership_scope": facts.get("membership_scope"),
               "known_status_fraction": 1 - unknown_days / total_days if total_days else None,
               "completed_without_witnessed_cycle": [r["issue"] for r in overall["completed_items"] if r["cycle_days"] is None],
               "bottleneck": None,
               "bottleneck_reason": ("Incomplete status exposure; a flat or growing band cannot establish a process bottleneck."
                                     if not overall["data_quality"]["coverage_complete"] else "Complete exposure; a process bottleneck still needs interpretation of stage queues and capacity."),
               "periods_are_confirmed_sprints": False}
    output.mkdir(parents=True, exist_ok=True)
    write_json(output / "flow.json", {"schema_version": 3, "periods": periods,
               "periods_are_confirmed_sprints": False, "source": source, "source_sha256": source_hash})
    write_json(output / "observed-flow.json", {**overall, "source": source, "source_sha256": source_hash})
    write_json(output / "cfd.json", rows)
    write_json(output / "data-quality.json", quality)
    write_json(output / "board-policy.json", board_policy(facts))
    write_details(flow_details(facts, start, end), periods, output)
    with (output / "cfd.csv").open("w", newline="") as stream:
        fields = ["date", "at_utc", "sample", *STATUSES, "tracked_items", "unlocated_items"]
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    with (output / "transitions.csv").open("w", newline="") as stream:
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(["issue", "at_utc", "from", "to", "event_id", "project_id"])
        for row in sorted(facts["transitions"], key=lambda r: stamp(r["at"])):
            writer.writerow([row["issue"], stamp(row["at"]).isoformat(), row["from"], row["to"], row.get("id", ""), row.get("project_id", "")])
    summary = ["# Проверка потока ЛЗ 9", "", f"Источник: [{snapshot.name}]({source}), получен {facts.get('captured_at_utc', 'без даты')}. Неизменность подтверждается SHA-256 в JSON.", "",
               "Это наблюдаемые календарные окна. Проведёнными командными спринтами они пока не подтверждены.", "",
               "| Окно UTC [начало, конец) | Завершено уникальных задач | Достоверных cycle samples | Mean / p85, дни | Средний WIP |",
               "|---|---:|---:|---|---|"]
    for row in periods:
        cycle = "нет данных" if row["cycle_mean_days"] is None else f"{row['cycle_mean_days']:.3f} / {row['cycle_p85_days']:.3f}"
        wip = "не определён" if row["average_wip"] is None else f"{row['average_wip']:.3f}"
        summary.append(f"| {row['start_utc'][:10]} — {row['end_utc'][:10]} | {row['throughput']} | {row['cycle_time_samples']} | {cycle} | {wip} |")
    summary += ["", "## Как читать CFD", "",
                "Каждая строка — точка времени at_utc, шаг один день от начала окна. Для выбранных окон это 00:00 UTC; переход днём отражается на следующем суточном срезе. Нулевые столбцы сохранены.", "",
                "Unknown обозначает отсутствие достоверного статуса. При разрыве цепочки неизвестен весь интервал между соседними наблюдениями. Если последняя запись расходится с текущим снимком, неизвестен интервал до снимка; его текущий статус не переносится назад.", "",
                "Дата добавления карточки берётся из ProjectV2Item.createdAt, не из даты создания issue. Область — зафиксированная когорта issue; полностью восстановить удалённые/архивированные членства по текущему API-снимку нельзя.", "",
                f"Найдено интервалов с разрывом: {len(quality['gaps'])}. Завершения без достоверного начала: {quality['completed_without_witnessed_cycle']}. WIP lower/upper относятся только к зафиксированной когорте, а не ко всей работе команды.", "",
                "## Единицы, детализация и сравнение", "",
                "p85 использует линейную интерполяцию PERCENTILE.INC из формулы Calc: позиция (n−1)×0,85. Например, для 1 и 3 дней p85=2,7 дня. Выборочный максимум вместо интерполяции не используется.", "",
                "Основная таблица считает календарные сутки UTC. В working_time отдельно рассчитаны дни Пн–Пт UTC без исключения праздников, включая рабочую длительность каждого цикла и экспозицию WIP. Throughput/рабочие дни умножается на рабочую длительность цикла: календарные и рабочие дни в одной формуле не смешиваются. Обе оценки требуют достаточно устойчивого потока; перенос работы через границы окна тоже может объяснить расхождение.", "",
                "[Сравнение окон](comparison.csv), [каждая задача и её время в статусах](item-times.csv), [средний WIP по дням](daily-wip.csv). Последний интегрируется по точным timestamp; работа между двумя полуночными срезами не теряется. Пустое поле CSV означает отсутствие достоверной оценки, а не ноль. Столбец FOR TEST входит в активный WIP.", "",
                f"Текущий снимок доски: Review={board_policy(facts)['review_count']} при лимите 3. Это состояние на дату выгрузки, а не восстановленный WIP исторических спринтов. [Проверка политики](board-policy.json) показывает превышение и ограничение проверки персонального WIP.", "",
                "## Вывод", "",
                _conclusion(quality), "",
                "Дальнейшее проверяемое действие и будущие цели описаны в [плане эксперимента](../sprint-experiment.md). Состоявшаяся ретроспектива и эффект изменения требуют отдельного протокола.", ""]
    (output / "analysis.md").write_text("\n".join(summary))
    if plot:
        plot_cfd(rows, output / "observed-flow.png")
    return {"periods": len(periods), "daily_rows": len(rows), "transitions": len(facts["transitions"]),
            "coverage_complete": quality["coverage_complete"], "source_sha256": source_hash}


def _conclusion(quality):
    if quality["coverage_complete"]:
        return ("Статусы зафиксированной когорты покрыты полностью. Результаты проверки Литтла приведены в JSON/CSV; конечное окно требует проверки устойчивости потока и переноса незавершённой работы через его границы. Узкое место следует обосновать расширением полос CFD, временем стадий и доступностью исполнителей.")
    return ("Узкое место по историческим окнам не доказано. Причина неполного измерения — отсутствующие переходы. Закон Литтла не проверяется на неполных cycle samples или неизвестной экспозиции WIP. Даже при полных данных конечное окно требует проверки устойчивости потока.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--start", type=stamp, required=True)
    parser.add_argument("--end", type=stamp, required=True)
    parser.add_argument("--output-directory", type=Path, required=True)
    parser.add_argument("--period-days", type=int, default=7)
    args = parser.parse_args()
    print(json.dumps(build(args.snapshot, args.start, args.end, args.output_directory, period_days=args.period_days)))


if __name__ == "__main__":
    main()
