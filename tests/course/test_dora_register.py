import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from scripts.course.metrics import main, measured_dora, stamp


class ObservedDoraTests(unittest.TestCase):
    def setUp(self):
        self.start, self.end = stamp("2026-11-01T00:00:00Z"), stamp("2026-11-08T00:00:00Z")
        self.facts = {"repository": "owner/repo", "runs": [], "deployments": [
            {"id": 1, "environment": "qa", "state": "failure", "finished_at": "2026-11-02T10:00:00Z"},
            {"id": 2, "environment": "qa", "state": "success", "finished_at": "2026-11-02T10:10:00Z",
             "commit_at": "2026-11-02T09:10:00Z"},
            {"id": 3, "environment": "production", "state": "success", "finished_at": "2026-11-02T10:10:00Z"}]}
        self.register = {"environment": "qa", "complete": True, "covered_deployment_ids": [1, 2],
                         "incidents": [{"deployment_id": 1, "started_at": "2026-11-02T10:00:00Z",
                                        "recovered_at": "2026-11-02T10:10:00Z", "repair_automation_hours": 1 / 6}]}

    def measure(self, register=None):
        return measured_dora(self.facts, self.start, self.end, environment="qa", register=register)

    def test_cli_reads_actual_incidents_and_excludes_other_environments(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "facts.json").write_text(json.dumps(self.facts))
            (root / "incidents.json").write_text(json.dumps(self.register))
            with patch.object(sys, "argv", ["metrics", "--snapshot", str(root / "facts.json"),
                    "--incidents", str(root / "incidents.json"), "--environment", "qa", "--kind", "dora",
                    "--start", self.start.isoformat(), "--end", self.end.isoformat(), "--output", str(root / "out.json")]):
                main()
            result = json.loads((root / "out.json").read_text())
        self.assertEqual(result["deployment_ids"], [1, 2])
        self.assertEqual(result["deployment_frequency_per_week"], 1)
        self.assertEqual(result["lead_time_median_hours"], 1)
        self.assertEqual(result["change_failure_rate_percent"], 50)
        self.assertEqual(result["recovery_median_minutes"], 10)
        self.assertAlmostEqual(result["repair_automation_hours"], 1 / 6)
        self.assertIsNone(result["human_labor_hours"])

    def test_missing_or_incomplete_register_does_not_create_zero_failure_rate(self):
        self.assertIsNone(self.measure()["change_failure_rate_percent"])
        self.register["covered_deployment_ids"] = [1]
        result = self.measure(self.register)
        self.assertFalse(result["incident_register_complete"])
        self.assertIsNone(result["change_failure_rate_percent"])

    def test_foreign_environment_or_unknown_deployment_is_rejected(self):
        for key, value in [("environment", "production"), ("covered_deployment_ids", [1, 2, 3]),
                           ("covered_deployment_ids", [1, 2, 99])]:
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                self.measure({**self.register, key: value})

    def test_negative_repair_time_and_backward_recovery_are_rejected(self):
        for change in [{"recovered_at": "2026-11-02T09:00:00Z"}, {"repair_automation_hours": -1}]:
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.measure({**self.register, "incidents": [{**self.register["incidents"][0], **change}]})

    def test_recovery_not_observed_by_window_end_remains_unknown(self):
        self.register["incidents"][0]["recovered_at"] = "2026-11-09T00:00:00Z"
        self.assertIsNone(self.measure(self.register)["recovery_median_minutes"])

    def test_even_recovery_sample_uses_the_arithmetic_median(self):
        self.register["incidents"].append({"deployment_id": 2, "started_at": "2026-11-02T11:00:00Z",
                                           "recovered_at": "2026-11-02T11:20:00Z"})
        self.assertEqual(self.measure(self.register)["recovery_median_minutes"], 15)
