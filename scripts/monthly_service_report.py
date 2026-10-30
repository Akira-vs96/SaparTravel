"""Assemble actual SLI evidence and proposed service credits; never infer missing results."""
import argparse
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
import json
from pathlib import Path

from scripts.availability_report import month_window


def credits(availability, p1_breaches, fee):
    amount = Decimal(str(fee))
    percentage = Decimal(str(availability))
    if not amount.is_finite() or amount < 0 or not percentage.is_finite() or not 0 <= percentage <= 100:
        raise ValueError("Invalid fee or availability")
    if type(p1_breaches) is not int or p1_breaches < 0:
        raise ValueError("Invalid breach count")
    availability_rate = Decimal(0) if percentage >= Decimal("99.5") else Decimal("0.05") if percentage >= 99 else Decimal("0.10") if percentage >= 95 else Decimal("0.25")
    response_rate = min(Decimal("0.10"), Decimal("0.02") * p1_breaches)
    total_rate = min(Decimal("0.25"), availability_rate + response_rate)
    money = lambda value: format((amount * value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP), ".2f")
    return {"availability_credit": money(availability_rate), "p1_response_credit": money(response_rate),
            "total_credit": money(total_rate), "cap_reduction": money(availability_rate + response_rate - total_rate), "cap_percent": 25,
            "note": "Calculation for review under the supplied agreement; no charge or refund is performed"}


def build_report(*, availability, support=None, recoveries=None, load=None, agreement=None, now=None):
    month = availability["month"]
    start, end = month_window(month)
    moment = now or datetime.now(timezone.utc)
    if moment < end:
        raise ValueError("Only a completed calendar month can be reported")
    if support is not None and support.get("month") != month:
        raise ValueError("Support and availability must cover the same month")
    missing = []
    if availability.get("status") != "measured":
        missing.append("availability_observations")
    if availability.get("sla_evaluation") != "evaluated":
        missing.append("approved_operational_availability")
    if support is None:
        missing.append("support_report")
    elif not support.get("finalized") or support.get("unknown_deadlines", 0):
        missing.append("complete_support_deadlines")
    elif any(value["eligible"] for value in support["priorities"].values()) and not support.get("calendar_approved"):
        missing.append("approved_support_calendar")
    monthly_recoveries = []
    for recovery in recoveries or []:
        stamp = recovery.get("failure_started_at_utc") or recovery.get("failure_simulated_at_utc")
        if stamp and start <= datetime.fromisoformat(stamp) < end:
            monthly_recoveries.append(recovery)
    if not monthly_recoveries:
        missing.append("monthly_recovery_drill")
    credit = None
    fee = (agreement or {}).get("fee")
    if fee and agreement.get("approved") is True and agreement.get("month") == month and not any(
            name in missing for name in ("availability_observations", "approved_operational_availability", "support_report",
                                         "complete_support_deadlines", "approved_support_calendar")):
        if availability.get("sla_availability_percent") is not None:
            successes = availability["sla_successful_minutes"]
            eligible = availability["sla_eligible_minutes"]
            if type(successes) is not int or type(eligible) is not int or not 0 <= successes <= eligible or eligible == 0:
                raise ValueError("Invalid SLA minute accounting")
            exact_availability = Decimal(successes) * 100 / Decimal(eligible)
            credit = {**credits(exact_availability, support["priorities"]["P1"]["breaches"], fee["amount"]),
                      "currency": fee["currency"], "agreement_reference": agreement["agreement_reference"]}
    return {"schema_version": 1, "month": month, "timezone": "Asia/Almaty", "generated_at_utc": moment.isoformat(),
            "status": "complete_evidence" if not missing else "incomplete_evidence", "missing_evidence": missing,
            "availability": availability, "support": support, "recovery_drills_and_incidents": monthly_recoveries,
            "catalog_acceptance": load, "service_credit": credit,
            "acceptance": "Customer UAT and contractual activation remain explicit human decisions"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--availability", type=Path, required=True)
    parser.add_argument("--support", type=Path)
    parser.add_argument("--recovery", type=Path, action="append", default=[])
    parser.add_argument("--load", type=Path)
    parser.add_argument("--agreement", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    read = lambda path: json.loads(path.read_text()) if path else None
    try:
        report = build_report(availability=read(args.availability), support=read(args.support),
                              recoveries=[read(path) for path in args.recovery], load=read(args.load), agreement=read(args.agreement))
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + "\n")
        print(report["status"])
        return 0 if report["status"] == "complete_evidence" else 1
    except (OSError, ValueError, TypeError, KeyError):
        print("Invalid monthly evidence or agreement; no service credit is certified")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
