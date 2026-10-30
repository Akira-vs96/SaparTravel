from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from scripts.availability_probe import SCENARIO_VERSION, STEPS
from scripts.availability_report import aggregate, month_window
from scripts.database_recovery import RecoveryError, verified_manifest
from scripts.monthly_service_report import build_report, credits
from scripts.ops_jobs import copy_backup, latest_backup
from scripts.recovery_report import recovery_report

POINTS = ["a", "b", "c"]
START, END = month_window("2026-10")
NOW = END + timedelta(days=1)


def observation(minute, point, scope="acceptance-only"):
    return {"timestamp_utc": minute.isoformat(), "point": point, "deployment_id": "test-deployment",
            "scope": scope, "scenario_version": SCENARIO_VERSION, "success": True, "duration_ms": 50,
            "steps": [{"name": name, "success": True, "status_code": 201 if name == "create" else 200, "duration_ms": 5} for name in STEPS]}


def agreement():
    return {"month": "2026-10", "deployment_id": "test-deployment", "approved": True,
            "agreement_reference": "synthetic test agreement", "independent_points": True, "exclusions": [],
            "fee": {"amount": "1000.00", "currency": "USD"}}


class RecoveryTests(unittest.TestCase):
    def report(self, rows):
        return recovery_report(rows, failure_at=START + timedelta(seconds=1), deployment_id="test-deployment", points=POINTS, now=NOW)

    def observations(self):
        return [observation(START + timedelta(minutes=index), point) for index in range(1, 6) for point in POINTS[:2]]

    def test_five_real_minutes_confirm_first_minute_not_end_of_confirmation(self):
        result = self.report(self.observations())
        self.assertTrue(result["sli_r_confirmed"])
        self.assertEqual(result["rto_seconds"], 59)
        self.assertFalse(result["independent_points"])

    def test_missing_minute_duplicate_or_invalid_steps_break_the_series(self):
        rows = self.observations()
        gap = [row for row in rows if row["timestamp_utc"] != (START + timedelta(minutes=3)).isoformat()]
        self.assertFalse(self.report(gap)["sli_r_confirmed"])
        self.assertFalse(self.report(rows + [deepcopy(rows[0])])["sli_r_confirmed"])
        wrong = deepcopy(rows)
        wrong[0]["steps"] = []
        self.assertFalse(self.report(wrong)["sli_r_confirmed"])

    def test_wrong_version_and_five_accelerated_observations_never_confirm(self):
        rows = self.observations()
        rows[0]["scenario_version"] = "different-version"
        self.assertFalse(self.report(rows)["sli_r_confirmed"])
        fast = [observation(START + timedelta(seconds=index), point) for index in range(1, 6) for point in POINTS]
        self.assertFalse(self.report(fast)["sli_r_confirmed"])


class AgreementTests(unittest.TestCase):
    def test_exclusion_changes_both_sla_counts_and_leaves_internal_slo_intact(self):
        policy = agreement()
        policy["exclusions"] = [{"start_utc": START.isoformat(), "end_utc": (START + timedelta(minutes=1)).isoformat(),
                                  "reason": "documented customer action", "evidence_reference": "incident-1", "approval_reference": "signed-exception-1"}]
        rows = [observation(START, point, "operational") for point in POINTS[:2]]
        result = aggregate(rows, month="2026-10", points=POINTS, deployment_id="test-deployment", scope="operational", agreement=policy, now=NOW)
        self.assertEqual(result["successful_minutes"], 1)
        self.assertEqual(result["sla_successful_minutes"], 0)
        self.assertEqual(result["sla_eligible_minutes"], result["total_minutes"] - 1)
        self.assertEqual(result["sla_excluded_minutes"], 1)

    def test_unapproved_exception_and_partial_minutes_are_rejected(self):
        policy = agreement()
        policy["approved"] = False
        with self.assertRaises(ValueError):
            aggregate([], month="2026-10", points=POINTS, deployment_id="test-deployment", agreement=policy, now=NOW)
        policy = agreement()
        policy["exclusions"] = [{"start_utc": (START + timedelta(seconds=1)).isoformat(), "end_utc": (START + timedelta(minutes=1)).isoformat(),
                                  "reason": "reason", "evidence_reference": "evidence", "approval_reference": "approval"}]
        with self.assertRaises(ValueError):
            aggregate([], month="2026-10", points=POINTS, deployment_id="test-deployment", agreement=policy, now=NOW)

    def test_no_observations_or_local_points_do_not_certify_sla(self):
        result = aggregate([], month="2026-10", points=POINTS, deployment_id="test-deployment", scope="operational", agreement=agreement(), now=NOW)
        self.assertIsNone(result["sla_met"])
        policy = agreement()
        policy["independent_points"] = False
        rows = [observation(START, point, "operational") for point in POINTS]
        self.assertNotEqual(aggregate(rows, month="2026-10", points=POINTS, deployment_id="test-deployment", scope="operational", agreement=policy, now=NOW)["sla_evaluation"], "evaluated")


class MonthlyTests(unittest.TestCase):
    def test_documented_credit_example_thresholds_and_total_cap(self):
        self.assertEqual(credits("99.2", 1, "1000")["total_credit"], "70.00")
        for availability, expected in (("99.5", "0.00"), ("99", "50.00"), ("95", "100.00"), ("94.9999", "250.00")):
            self.assertEqual(credits(availability, 0, "1000")["total_credit"], expected)
        self.assertEqual(credits("90", 100, "1000")["total_credit"], "250.00")

    def test_missing_sources_are_reported_and_do_not_create_service_credit(self):
        availability = aggregate([], month="2026-10", points=POINTS, deployment_id="test-deployment", now=NOW)
        result = build_report(availability=availability, agreement=agreement(), now=NOW)
        self.assertEqual(result["status"], "incomplete_evidence")
        self.assertIn("support_report", result["missing_evidence"])
        self.assertIsNone(result["service_credit"])

    def test_different_support_month_is_rejected(self):
        with self.assertRaises(ValueError):
            build_report(availability={"month": "2026-10"}, support={"month": "2026-09"}, now=NOW)

    def test_financial_threshold_uses_exact_minute_counts(self):
        availability = {"month": "2026-10", "status": "measured", "sla_evaluation": "evaluated",
                        "sla_availability_percent": 98.99999999999999, "sla_successful_minutes": 9900, "sla_eligible_minutes": 10000}
        support = {"month": "2026-10", "finalized": True, "unknown_deadlines": 0, "calendar_approved": True,
                   "priorities": {"P1": {"eligible": 1, "breaches": 0}}}
        report = build_report(availability=availability, support=support, agreement=agreement(), now=NOW)
        self.assertEqual(report["service_credit"]["availability_credit"], "50.00")


class BackupTests(unittest.TestCase):
    def fixture(self, root):
        archive = root / "sapartravel-20261030T000000Z-test.dump"
        archive.write_bytes(b"opaque archive fixture")
        manifest = {"schema_version": 1, "kind": "sapartravel-backup", "archive": archive.name,
                    "snapshot_lower_bound_utc": START.isoformat(), "bytes": archive.stat().st_size,
                    "sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
                    "contents": {"tables": {"fixture": {"rows": 1}}, "alembic_revisions": ["0005"]}}
        path = archive.with_suffix(".dump.json")
        path.write_text(json.dumps(manifest))
        return path, archive

    def test_second_copy_is_verified_private_and_corruption_is_not_hidden(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest, archive = self.fixture(root)
            copy_backup(manifest, root / "second")
            copied, _ = verified_manifest(root / "second" / manifest.name)
            self.assertEqual(copied["sha256"], hashlib.sha256(archive.read_bytes()).hexdigest())
            self.assertEqual((root / "second" / archive.name).stat().st_mode & 0o777, 0o600)
            archive.write_bytes(b"tampered")
            with self.assertRaises(RecoveryError):
                latest_backup(root)


if __name__ == "__main__":
    unittest.main()
