"""Recalculate vacancy frequencies from reviewed primary-source observations."""
import argparse
import csv
import json
from pathlib import Path


def frequencies(rows):
    if len(rows) != 10 or len({r["url"] for r in rows}) != 10:
        raise ValueError("Ten distinct primary vacancy records are required")
    if len({r["channel"] for r in rows}) < 2:
        raise ValueError("The sample must use more than one channel")
    terms = sorted({v for row in rows for v in row["normalized_requirements"]})
    return [{"requirement": term, "vacancies": sum(term in r["normalized_requirements"] for r in rows),
             "denominator": 10, "percent": 10 * sum(term in r["normalized_requirements"] for r in rows)} for term in terms]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output-directory", type=Path, required=True)
    args = parser.parse_args()
    rows = json.loads(args.input.read_text())
    values = frequencies(rows)
    args.output_directory.mkdir(parents=True, exist_ok=True)
    with (args.output_directory / "frequency.csv").open("w") as stream:
        writer = csv.DictWriter(stream, fieldnames=["requirement", "vacancies", "denominator", "percent"])
        writer.writeheader()
        writer.writerows(values)
    print("Calculated frequencies for ten distinct observations; source interpretation remains reviewable")


if __name__ == "__main__":
    main()
