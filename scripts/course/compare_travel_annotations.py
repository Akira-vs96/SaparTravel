"""Compare two independent blind travel-query annotations without inventing adjudications."""
import argparse
import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATASET = ROOT / "evals/travel-assistant/dataset.jsonl"
FIELDS = ("budget", "category", "duration_max", "travelers", "destination_slug", "date_from", "date_to")
CSV_FIELDS = {
    "budget": "budget_kzt_total", "category": "category_code", "duration_max": "duration_max_days",
    "travelers": "travelers", "destination_slug": "destination_slug", "date_from": "date_from", "date_to": "date_to",
}


def _read(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def _value(value: str, *, integer: bool = False):
    value = (value or "").strip()
    if not value:
        return None
    if integer:
        try:
            return int(value)
        except ValueError:
            raise ValueError(f"Expected an integer, got {value!r}") from None
    return value


def _label(row: dict) -> dict:
    raw_search = (row.get("search") or "").strip().casefold()
    search = {"yes": True, "да": True, "true": True, "no": False, "нет": False, "false": False}.get(raw_search)
    if search is None:
        raise ValueError(f"Row {row.get('id')} needs search=yes/no")
    filters = {key: _value(row.get(column, ""), integer=key in {"budget", "duration_max", "travelers"})
               for key, column in CSV_FIELDS.items()}
    return {"search": search, "filters": filters}


def compare(annotation_a: Path, annotation_b: Path, output: Path, po_decisions: Path | None = None) -> dict:
    expected_ids = [json.loads(line)["id"] for line in DATASET.read_text(encoding="utf-8").splitlines() if line.strip()]
    a_rows, b_rows = _read(annotation_a), _read(annotation_b)
    issues = []
    if [row.get("id") for row in a_rows] != expected_ids:
        issues.append("Form A must contain every dataset row exactly once, in dataset order.")
    if [row.get("id") for row in b_rows] != expected_ids:
        issues.append("Form B must contain every dataset row exactly once, in dataset order.")
    reviewers_a = {row.get("reviewer", "").strip() for row in a_rows if row.get("reviewer", "").strip()}
    reviewers_b = {row.get("reviewer", "").strip() for row in b_rows if row.get("reviewer", "").strip()}
    if any(not row.get("reviewer", "").strip() for row in a_rows + b_rows):
        issues.append("Every annotated row needs the reviewer's name.")
    if len(reviewers_a) != 1 or len(reviewers_b) != 1 or reviewers_a == reviewers_b:
        issues.append("Each form needs one named reviewer, and A/B reviewers must be different people.")

    conflicts, unresolved, labels_a, labels_b, final_labels = [], [], [], [], []
    adjudications = {}
    decisions = {}
    if po_decisions and po_decisions.is_file():
        decision_rows = _read(po_decisions)
        decisions = {row.get("id", "").strip(): row for row in decision_rows if row.get("id", "").strip()}
        if len(decisions) != len(decision_rows):
            issues.append("PO decision form contains a blank or duplicate ID.")
    for row_a, row_b in zip(a_rows, b_rows):
        try:
            label_a, label_b = _label(row_a), _label(row_b)
        except ValueError as exc:
            issues.append(str(exc))
            continue
        labels_a.append(label_a)
        labels_b.append(label_b)
        different = {key: {"A": label_a["filters"][key], "B": label_b["filters"][key]}
                     for key in FIELDS if label_a["filters"][key] != label_b["filters"][key]}
        if label_a["search"] != label_b["search"]:
            different["search"] = {"A": label_a["search"], "B": label_b["search"]}
        if different:
            decision_row = decisions.get(row_a.get("id", ""))
            conflict = {"id": row_a.get("id"), "differences": different,
                        "rationale_a": row_a.get("rationale", ""), "rationale_b": row_b.get("rationale", "")}
            if decision_row:
                try:
                    final_label = _label(decision_row)
                    if not decision_row.get("decision_reason", "").strip() or not decision_row.get("product_owner", "").strip() or not decision_row.get("reviewed_at_utc", "").strip():
                        raise ValueError("PO decision needs a reason, name and review timestamp")
                    conflict["product_owner_decision"] = final_label
                    conflict["product_owner"] = decision_row["product_owner"].strip()
                    conflict["decision_reason"] = decision_row["decision_reason"].strip()
                    conflict["reviewed_at_utc"] = decision_row["reviewed_at_utc"].strip()
                    adjudications[row_a["id"]] = {"name": conflict["product_owner"],
                                                   "reason": conflict["decision_reason"],
                                                   "reviewed_at_utc": conflict["reviewed_at_utc"]}
                    final_labels.append(final_label)
                except ValueError as exc:
                    issues.append(f"PO decision {row_a.get('id')}: {exc}")
                    unresolved.append(row_a.get("id"))
            else:
                unresolved.append(row_a.get("id"))
            conflicts.append(conflict)
        else:
            final_labels.append(label_a)
        for row, side in ((row_a, "A"), (row_b, "B")):
            if not row.get("rationale", "").strip() or not row.get("reviewed_at_utc", "").strip():
                issues.append(f"{row.get('id')} form {side} is missing rationale or review timestamp.")

    approved = not issues and not unresolved and len(final_labels) == len(expected_ids)
    report = {
        "dataset": "evals/travel-assistant/dataset.jsonl", "examples": len(expected_ids),
        "independent_reviewers": sorted(reviewers_a | reviewers_b),
        "human_events_confirmed": bool(reviewers_a and reviewers_b and reviewers_a != reviewers_b
                                        and len(labels_a) == len(expected_ids) and not issues),
        "agreement": len(expected_ids) - len(conflicts) if not issues else None,
        "disagreements": conflicts, "unresolved_disagreements": unresolved,
        "validation_issues": sorted(set(issues)),
        "gold_ready": approved,
        "note": "Disagreements are not resolved automatically. The Product Owner must record a decision and rationale before creating human-approved gold.",
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    if unresolved:
        template = output.parent / "po-adjudication.csv"
        columns = ["id", "search", *CSV_FIELDS.values(), "decision_reason", "product_owner", "reviewed_at_utc"]
        old_rows = {row.get("id", ""): row for row in _read(template)} if template.is_file() else {}
        with template.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=columns)
            writer.writeheader()
            for row_id in unresolved:
                writer.writerow({key: old_rows.get(row_id, {}).get(key, "") for key in columns} | {"id": row_id})
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if approved:
        gold = output.with_name("human-gold.jsonl")
        reviewer_names = sorted(reviewers_a | reviewers_b)
        gold.write_text("".join(json.dumps({"id": row_id, "expected": label, "reviewers": reviewer_names,
                                              "annotation_status": "two-human-reviewed",
                                              **({"product_owner_adjudication": adjudications[row_id]} if row_id in adjudications else {})},
                                             ensure_ascii=False) + "\n"
                                  for row_id, label in zip(expected_ids, final_labels)), encoding="utf-8")
        report["human_gold_path"] = str(gold.relative_to(ROOT))
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--a", type=Path, default=ROOT / "evals/travel-assistant/annotation-a.csv")
    parser.add_argument("--b", type=Path, default=ROOT / "evals/travel-assistant/annotation-b.csv")
    parser.add_argument("--output", type=Path, default=ROOT / "docs/labs/lab-12/travel-assistant-evidence/annotation-comparison.json")
    parser.add_argument("--po-decisions", type=Path, default=ROOT / "docs/labs/lab-12/travel-assistant-evidence/po-adjudication.csv")
    args = parser.parse_args()
    result = compare(args.a, args.b, args.output, args.po_decisions)
    print(json.dumps({"examples": result["examples"], "gold_ready": result["gold_ready"],
                      "disagreements": len(result["disagreements"]),
                      "unresolved_disagreements": len(result["unresolved_disagreements"]),
                      "validation_issues": len(result["validation_issues"])},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
