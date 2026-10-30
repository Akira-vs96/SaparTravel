"""LZ3 scenario arithmetic from explicitly assumed inputs, not observed customer savings."""
import argparse
from decimal import Decimal
import json
from pathlib import Path


def calculate(inputs):
    benefit = Decimal(str(inputs["annual_benefit"]))
    initial = Decimal(str(inputs["initial_cost"]))
    costs = [Decimal(str(c)) for c in inputs["annual_costs"]]
    rate = Decimal(str(inputs["discount_rate"]))
    if not costs or initial < 0 or benefit < 0 or rate < 0 or any(c < 0 for c in costs):
        raise ValueError("Expected a positive horizon and nonnegative amounts")
    tco = initial + sum(costs)
    if tco == 0:
        raise ValueError("ROI requires a nonzero cost denominator")
    npv = -initial + sum((benefit - c) / (1 + rate) ** year for year, c in enumerate(costs, 1))
    cumulative, payback = -initial, None
    for year, cost in enumerate(costs, 1):
        flow = benefit - cost
        if payback is None and cumulative < 0 <= cumulative + flow and flow > 0:
            payback = Decimal(year - 1) - cumulative / flow
        cumulative += flow
    return {"currency": inputs["currency"], "status": "planning assumptions; customer measurements pending",
            "tco": str(tco), "horizon_years": len(costs), "roi": str((benefit * len(costs) - tco) / tco),
            "npv": str(npv.quantize(Decimal(".01"))), "payback_years": str(payback) if payback is not None else None,
            "cost_of_delay_per_month": str((benefit / 12).quantize(Decimal(".01"))),
            "break_even_annual_benefit": str(tco / len(costs)),
            "sensitivity": [{"cost_factor": str(c), "benefit_factor": str(b),
                             "roi": str((benefit * len(costs) * b - tco * c) / (tco * c))}
                            for c, b in [(Decimal("1.3"), Decimal(1)), (Decimal(1), Decimal(".5")), (Decimal("1.3"), Decimal(".5"))]]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = calculate(json.loads(args.input.read_text()))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print("Calculated baseline and three adverse scenarios; no actual benefit is inferred")


if __name__ == "__main__":
    main()
