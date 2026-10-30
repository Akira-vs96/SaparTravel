"""Generate a checked PM draft from measured facts; never publish or send it."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from scripts.course.ai import generate, numeric_discrepancies
from scripts.course.metrics import stamp


def period_facts(snapshot, start, end):
    if not start < end:
        raise ValueError("Expected a nonempty reporting period")
    issues = snapshot["issues"]
    runs = [r for r in snapshot["runs"] if start <= stamp(r["created_at"]) < end]
    return {"period_start": start.date().isoformat(), "period_end_exclusive": end.date().isoformat(),
            "issues_created": sum(start <= stamp(r["created_at"]) < end for r in issues),
            "issues_closed": sum(bool(r["closed_at"]) and start <= stamp(r["closed_at"]) < end for r in issues),
            "ci_success": sum(r["conclusion"] == "success" for r in runs),
            "ci_failure": sum(r["conclusion"] == "failure" for r in runs),
            "recorded_deployments": sum(start <= stamp(r["created_at"]) < end for r in snapshot["deployments"]),
            "customer_approval": None, "sprint_goal": None, "measured_manual_minutes": None}


def build(snapshot, start, end, output, *, origin="http://127.0.0.1:18087", model="sapar-pm-qwen"):
    facts = period_facts(snapshot, start, end)
    output.mkdir(parents=True, exist_ok=True)
    journal = []
    for version in (1, 2):
        prompt = ("Write a short project status in Russian as JSON {\"summary\":\"...\"}. "
                  "Facts supplied below are the only source. Never invent numbers, dates, causes or approvals. "
                  "Use 'нет данных' for missing information. Max 90 words. CI success does not mean deployment.")
        if version == 2:
            prompt += (" Each factual sentence must name its source JSON key in square brackets. "
                       "Do not calculate ratios, duration or savings. Do not claim that UAT or interviews happened. "
                       "Missing sprint_goal and customer_approval must be explicitly described as unknown.")
        result = generate([{"role": "system", "content": prompt},
                           {"role": "user", "content": json.dumps(facts, ensure_ascii=False)}],
                          origin=origin, model=model, max_tokens=300)
        unexpected = numeric_discrepancies(result["text"], facts)
        (output / f"model-v{version}.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
        journal.append({"prompt_version": version, "machine_numeric_discrepancies": unexpected,
                        "machine_check_passed": not unexpected, "human_review": "pending", "reviewer": None,
                        "semantic_error_rate": None, "generation_seconds": result["seconds"]})
    (output / "facts.json").write_text(json.dumps(facts, ensure_ascii=False, indent=2) + "\n")
    (output / "verification.json").write_text(json.dumps({"claims": journal,
        "automatic_check_limitation": "Numeric whitelist cannot verify causes, approvals or sentence meaning",
        "manual_baseline_runs": [], "net_savings_minutes": None, "payback_runs": None,
        "status": "draft_requires_human_review"}, ensure_ascii=False, indent=2) + "\n")
    lines = ["# Статус проекта — черновик для проверки", "",
             f"Период: {facts['period_start']} — {facts['period_end_exclusive']} (конец не включён).", "",
             "Числа вычислены скриптом по GitHub, не языковой моделью:", ""]
    for key in ("issues_created", "issues_closed", "ci_success", "ci_failure", "recorded_deployments"):
        lines.append(f"- {key}: {facts[key]}.")
    lines += ["", "Нет данных о цели спринта, приёмке заказчиком и ручном хронометраже.", "",
              "Использование ИИ: локальная Qwen формулирует отдельный черновик в model-v2.json; "
              "он не опубликован и требует построчной проверки. Факты и расчёты подготовлены Python. "
              "Проверяющий: не назначен; одобрение и экономия не заявляются."]
    (output / "status.md").write_text("\n".join(lines) + "\n")
    return facts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--start", type=stamp, required=True)
    parser.add_argument("--end", type=stamp, required=True)
    parser.add_argument("--output-directory", type=Path, required=True)
    args = parser.parse_args()
    facts = build(json.loads(args.snapshot.read_text()), args.start, args.end, args.output_directory)
    print(json.dumps(facts))


if __name__ == "__main__":
    main()
