"""WSJF from explicit planning assumptions, with spreadsheet formulas preserved."""
import argparse
import csv
from fractions import Fraction
import json
from pathlib import Path

FIBONACCI = {1, 2, 3, 5, 8, 13}


def rank(rows):
    result = []
    if len({r["id"] for r in rows}) != len(rows):
        raise ValueError("Initiative identifiers must be unique")
    for row in rows:
        values = [int(row[k]) for k in ("value", "urgency", "risk_reduction", "size")]
        if any(v not in FIBONACCI for v in values):
            raise ValueError("Use the declared Fibonacci scale for all four components")
        score = Fraction(sum(values[:3]), values[3])
        result.append({**row, "cost_of_delay": sum(values[:3]), "wsjf": float(score)})
    return sorted(result, key=lambda r: (-r["wsjf"], r["id"]))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output-directory", type=Path, required=True)
    args = parser.parse_args()
    with args.input.open() as stream:
        rows = list(csv.DictReader(stream))
    ranked = rank(rows)
    out = args.output_directory
    out.mkdir(parents=True, exist_ok=True)
    (out / "wsjf.json").write_text(json.dumps({"wip_limit": 3, "scores_are_customer_approved": False,
                                              "status": "proposed planning estimates", "initiatives": ranked},
                                             indent=2, ensure_ascii=False) + "\n")
    from openpyxl import Workbook
    book = Workbook()
    sheet = book.active
    sheet.title = "WSJF"
    sheet.append(["ID", "Initiative", "Value", "Urgency", "Risk reduction", "Size", "CoD", "WSJF", "Rank", "Basis"])
    for index, row in enumerate(rows, 2):
        sheet.append([row["id"], row["initiative"], int(row["value"]), int(row["urgency"]), int(row["risk_reduction"]),
                      int(row["size"]), f"=SUM(C{index}:E{index})", f"=G{index}/F{index}",
                      f"=RANK(H{index},H$2:H${len(rows)+1},0)", row["basis"]])
    sheet.freeze_panes = "C2"
    sheet.auto_filter.ref = sheet.dimensions
    sheet.column_dimensions["B"].width = 50
    sheet.column_dimensions["J"].width = 75
    book.save(out / "wsjf.xlsx")
    print("WSJF calculated; all scores remain explicit proposals, not customer decisions")


if __name__ == "__main__":
    main()
