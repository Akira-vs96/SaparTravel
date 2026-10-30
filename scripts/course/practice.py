"""Recalculate clearly labelled course exercises without certifying human events."""
import argparse
import csv
from datetime import date, timedelta
import hashlib
import json
from pathlib import Path
import statistics

from scripts.course.ai import quality
from scripts.course.business_case import calculate
from scripts.course.forecast import simulate
from scripts.course.metrics import dora, percentile, stamp
from scripts.course.prioritize import rank

ROOT = Path(__file__).resolve().parents[2]
KIND = "educational_simulation"


def read(path, root=ROOT):
    return json.loads((root / path).read_text())


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _baseline(config, root):
    before, after = config["before_minutes"], config["after_minutes"]
    if len(before) != 60 or len(after) != 60 or min(before + after) <= 0:
        raise ValueError("The baseline exercise requires 60 positive paired observations")
    inputs = read("data/labs/lab-03/business-case.json", root)
    saved = (sum(before) - sum(after)) / 60
    benefit = saved * config["weeks_per_year"] * config["hourly_value_usd"]
    inputs["annual_benefit"] = str(benefit)
    return {"observations": len(before), "before_mean_minutes": statistics.mean(before),
            "after_mean_minutes": statistics.mean(after), "saved_hours_per_week": saved,
            "annual_benefit_usd": benefit, "finance": calculate(inputs),
            "horizon_decided_before_calculation": stamp(config["horizon_decision_utc"]) < stamp(config["calculation_utc"])}


def _capacity(config, root):
    gross = config["people"] * config["weeks"] * config["hours_per_week"]
    available = gross - config["absence_hours"]
    reserve = available * config["reserve_fraction"]
    emv = read("docs/labs/evidence/planning.json", root)["risk_emv_hours"]
    corrected = available - emv - config["management_reserve_hours"]
    return {"gross_hours": gross, "available_hours": available,
            "risk_reserve_hours": reserve, "baseline_capacity_hours": available - reserve,
            "capacity_after_emv_and_management_hours": corrected,
            "scope_reduction_hours": max(0, config["scope_hours"] - corrected),
            "dependency_count": len(config["dependencies"]),
            "reminders": [{"id": row["id"], "date": (date.fromisoformat(row["due"]) - timedelta(days=3)).isoformat()}
                          for row in config["dependencies"]]}


def _poker(config, root):
    scale = {1, 2, 3, 5, 8, 13}
    for row in config["stories"]:
        if len(row["votes"]) != 4 or any(v not in scale for v in row["votes"] + [row["final"]]):
            raise ValueError("Four virtual independent votes and a Fibonacci estimate are required")
    weeks = simulate(config["throughput"], len(config["stories"]))
    total = sum(r["final"] for r in config["stories"])
    return {"stories": len(config["stories"]), "first_round_spreads": [max(r["votes"]) - min(r["votes"]) for r in config["stories"]],
            "story_points": total, "point_forecast_weeks": total / config["assumed_points_per_week"],
            "monte_carlo_weeks": {str(p): percentile(weeks, p / 100) for p in (50, 70, 85, 95)},
            "runs": 10000, "seed": 42, "zero_weeks_in_history": config["throughput"].count(0),
            "history_is_measured": False, "story_point_velocity_is_measured": False}


def _delivery(config, root):
    result = dora(config["facts"], stamp(config["start"]), stamp(config["end"]), config["incidents"], True)
    result["repair_labor_hours"] = sum(row["repair_labor_hours"] for row in config["incidents"])
    result["reliability_capacity_fraction"] = result["repair_labor_hours"] / config["team_capacity_hours"]
    result["red_merge_allowed_for_non_admin"] = False
    result["production_admin_push_exception"] = True
    return result


def _economy(config, root):
    manual = statistics.median(config["manual_minutes"])
    assisted = config["generation_minutes"] + config["verification_minutes"] + config["correction_minutes"]
    saved = manual - assisted
    build_minutes = config["development_hours"] * 60
    return {"manual_median_minutes": manual, "assisted_minutes": assisted,
            "net_minutes_per_report": saved,
            "payback_reports": build_minutes / saved if saved > 0 else None,
            "semester_net_minutes": saved * config["reports_per_semester"] - build_minutes,
            "economically_justified_this_semester": saved * config["reports_per_semester"] > build_minutes}


def _ai(config, root):
    dataset = [json.loads(line) for line in (root / "evals/pm-routing/dataset.jsonl").read_text().splitlines() if line.strip()]
    truth = [row["proposed_label"] for row in dataset]
    results = read("docs/labs/lab-12/evidence/results.json", root)
    calculated = {}
    for mode in ("zero-shot", "few-shot"):
        rows = [json.loads(line) for line in (root / f"docs/labs/lab-12/evidence/{mode}.jsonl").read_text().splitlines() if line.strip()]
        if [r["id"] for r in rows] != [r["id"] for r in dataset]:
            raise ValueError("Raw responses must match evaluation examples in order")
        calculated[mode] = quality(truth, [row["prediction"] for row in rows])
        if calculated[mode] != results["diagnostic_metrics"][mode]:
            raise ValueError("Recorded metrics do not match actual raw responses")
    cost = read("docs/labs/lab-12/evidence/cost.json", root)
    return {"real_model_metrics_reproduced": True, "examples": len(dataset),
            "difficult_examples": sum(bool(r.get("difficult")) for r in dataset),
            "diagnostic_metrics": calculated, "gold_human_approved": False,
            "input_tokens_are_from_local_tokenizer": True,
            "api_estimate_not_actual_billing": True,
            "break_even_proxy_requests": cost["break_even_requests_per_month_estimate"],
            "deployment_decision": "Keep rules and manual review; reject automatic LLM routing"}


def _portfolio(config, root):
    with (root / "docs/labs/lab-14/initiatives.csv").open() as stream:
        ranked = rank(list(csv.DictReader(stream)))
    return {"initiatives": len(ranked), "wip_limit": config["wip_limit"],
            "selected": [r["id"] for r in ranked[:config["wip_limit"]]],
            "deferred": [r["id"] for r in ranked[config["wip_limit"]:]],
            "delay_days": config["delay_days"],
            "delay_cost_usd": 21700 / 365 * config["delay_days"],
            "reduced_scope_hours": 171 - config["defer_hours"],
            "extra_resource_usd": config["extra_hours"] * config["hourly_rate_usd"],
            "sponsor_approved": False}


def _rehearsal(config, root):
    words = len(config["speech"].split())
    duration = sum(config["defense_minutes"])
    return {"defense_minutes": duration, "speech_words": words,
            "estimated_speech_seconds": words / config["words_per_minute"] * 60,
            "actual_person_rehearsal_seconds": None,
            "estimate_is_a_rehearsal": False, "professional_profile_published": False}


CALCULATORS = {3: _baseline, 5: _capacity, 6: _poker, 10: _delivery,
               12: _ai, 13: _economy, 14: _portfolio, 15: _rehearsal}


def validate_exercise(number, config):
    if config.get("data_kind") != KIND or config.get("human_events_confirmed") is not False:
        raise ValueError("Exercises must be explicitly simulated and cannot certify human events")
    if config.get("lab") != number or not config.get("sections"):
        raise ValueError("Expected the matching lab number and exercise sections")
    checks = {
        1: lambda: len(config["virtual_team"]) == 4 and config["virtual_customer"]["name"].startswith("SIM-"),
        2: lambda: len(config["cases"]) == 3 and len({r["model"] for r in config["cases"]}) == 3 and config["teacher_access_confirmed"] is False,
        3: lambda: sum(config["defense_minutes"]) == 5 and config["horizon_years"] == 3 and stamp(config["horizon_decision_utc"]) < stamp(config["calculation_utc"]),
        4: lambda: len(config["interviews"]) == 2 and len({r["role"] for r in config["interviews"]}) == 2 and all(r["quote"] and r["change"] for r in config["interviews"]) and config["performed_with_real_people"] is False,
        5: lambda: len(config["dependencies"]) >= 3 and len({r["id"] for r in config["dependencies"]}) == len(config["dependencies"]) and all(r["owner"] and r["fallback"] for r in config["dependencies"]) and 0 < config["reserve_fraction"] < 1,
        6: lambda: len(config["stories"]) == 10 and all(r["ac_change"] and r["shown_simultaneously"] and r["second_round"] == [r["final"]] * 4 for r in config["stories"]),
        7: lambda: config["silent_minutes"] == 25 and len(set(config["risk_ids"])) == 20 and len(config["participants"]) == 4,
        8: lambda: len(config["options"]) >= 2 and all(r["eligible"] == r["database_in_kz"] for r in config["options"]) and config["quotes_are_real"] is False,
        10: lambda: len(config["facts"]["deployments"]) >= 4 and config["rules_demo"] == {"actor": "non-admin", "ci": "failure", "review_count": 0, "expected": "blocked"},
        11: lambda: len(config["uat_scenarios"]) >= 8 and config["developer_hints"] == 0 and config["external_uat_passed"] is False and all(r["owner"] and r["due"] for r in config["findings"]),
        12: lambda: len(set(config["virtual_annotators"])) == 2 and config["independent_humans_present"] is False and all(r["reason"] for r in config["disagreements"]),
        13: lambda: len(config["manual_minutes"]) >= 3 and min(config["manual_minutes"]) > 0 and config["verification_minutes"] > 0 and config["timings_are_real"] is False,
        14: lambda: config["wip_limit"] == 3 and config["delay_days"] == 28 and config["approved_by_sponsor"] is False,
        15: lambda: sum(config["defense_minutes"]) == 15 and config["profile_update_is_draft"] is True and len(config["speech"].split()) / config["words_per_minute"] * 60 <= 90,
    }
    if number not in checks or not checks[number]():
        raise ValueError(f"Lab {number}: required exercise constraints are not satisfied")


def calculate_exercise(number, config, root=ROOT):
    validate_exercise(number, config)
    result = CALCULATORS.get(number, lambda value, base: {"scenario_sections": len(value["sections"])})(config, root)
    return {"data_kind": KIND, "lab": number, "human_events_confirmed": False, **result}


def _safe_file(root, path):
    resolved = (root / path).resolve()
    if not resolved.is_relative_to(root.resolve()) or not resolved.is_file():
        raise ValueError("Missing or unsafe exercise evidence: " + str(path))
    return resolved


def build(root=ROOT, *, check=False):
    manifest = read("docs/labs/manifest.json", root)
    coverage, errors = [], []
    for lab in manifest["labs"]:
        number = lab["number"]
        if number == 9:
            accepted = read("docs/labs/lab-09/simulation/evidence/acceptance.json", root)
            if not accepted["simulation_complete"] or accepted["real_sprints_confirmed"]:
                raise ValueError("Lab 9 must remain a completed, explicitly synthetic exercise")
            proofs = {r["id"]: "docs/labs/lab-09/simulation/README.md" for r in accepted["requirements"]}
        else:
            directory = root / f"docs/labs/lab-{number:02d}/practice"
            config = json.loads((directory / "scenario.json").read_text())
            result = calculate_exercise(number, config, root)
            result["scenario_sha256"] = digest(directory / "scenario.json")
            result["generator_sha256"] = digest(Path(__file__))
            target = directory / "results.json"
            if check:
                if not target.is_file() or json.loads(target.read_text()) != result:
                    errors.append(f"Lab {number}: calculated results are stale; run scripts.course.practice")
            else:
                target.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
            proofs = config["requirements"]
        expected = {r["id"] for r in lab["steps"]}
        if set(proofs) != expected:
            errors.append(f"Lab {number}: exercise requirements must match the methodology exactly")
        for requirement in lab["steps"]:
            proof = proofs.get(requirement["id"])
            if not proof:
                continue
            _safe_file(root, proof.split("#")[0])
            coverage.append({"id": requirement["id"], "lab": number,
                             "factual_status": requirement["status"],
                             "exercise_evidence": proof,
                             "factual_evidence": requirement.get("evidence", []),
                             "human_event_certified_by_exercise": False})
    result = {"data_kind": "course_exercise_coverage", "labs": 15,
              "requirements": len(coverage), "all_requirements_covered": not errors,
              "human_events_confirmed": False, "course_factually_complete": False,
              "errors": errors, "coverage": coverage,
              "note": "Coverage proves that an exercise exists. It does not prove interviews, signatures, independent annotation, access or acceptance."}
    destination = root / "docs/labs/evidence/practice-audit.json"
    if not check:
        destination.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    elif not destination.is_file() or json.loads(destination.read_text()) != result:
        errors.append("Course exercise audit is stale")
    if errors:
        raise ValueError("; ".join(errors))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Fail on changed scenarios or stale calculations; never rewrite evidence")
    args = parser.parse_args()
    result = build(check=args.check)
    print(json.dumps({k: result[k] for k in ("labs", "requirements", "all_requirements_covered", "human_events_confirmed")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
