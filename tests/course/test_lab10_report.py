"""Check time, labor and merge-policy consistency of the lab 10 course history."""
import copy
import json
import tempfile
import unittest
from pathlib import Path

from scripts.course.lab10_report import DIRECTORY, analyse, build


class DeliveryHistoryTests(unittest.TestCase):
    def setUp(self):
        self.config = json.loads((DIRECTORY / "scenario.json").read_text())

    def test_red_ci_blocks_even_after_review_and_green_ci_requires_review(self):
        report = analyse(self.config)
        cases = report["merge_attempts"]
        self.assertEqual([row["calculated"] for row in cases], ["blocked", "blocked", "blocked", "allowed"])
        self.assertEqual(cases[1]["blockers"], ["backend"])
        self.assertEqual(cases[2]["blockers"], ["review"])
        self.assertFalse(report["human_events_confirmed"])
        self.assertEqual(sum(row["deployment_count"] for row in report["weekly"]), 16)

    def test_repair_hours_are_summed_across_roles_and_not_outage_minutes(self):
        report = analyse(self.config)
        self.assertAlmostEqual(sum(row["person_hours"] for row in report["worklog"]), 6, places=5)
        self.config["incidents"][0]["repair_labor_hours"] = 40 / 60
        with self.assertRaisesRegex(ValueError, "labor must match"):
            analyse(self.config)

    def test_chronology_capacity_and_merge_claims_are_validated(self):
        changes = [
            (lambda config: config["incidents"][0].update(started_at="2026-09-01T00:00:00Z"), "follow deployment"),
            (lambda config: config.update(team_capacity_hours=319), "Capacity must match"),
            (lambda config: config["merge_attempts"][1].update(expected="allowed"), "contradicts"),
        ]
        for change, message in changes:
            config = copy.deepcopy(self.config)
            change(config)
            with self.subTest(message=message), self.assertRaisesRegex(ValueError, message):
                analyse(config)

    def test_exports_are_reproducible_and_stale_exports_are_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            (directory / "scenario.json").write_text(json.dumps(self.config))
            report = build(directory)
            self.assertEqual(build(directory, check=True), report)
            checks = json.loads((directory / "merge-checks.json").read_text())
            self.assertFalse(checks["github_merge_attempt_performed"])
            self.assertEqual(checks["data_kind"], "educational_simulation")
            (directory / "repair-hours.csv").write_text("changed")
            with self.assertRaisesRegex(ValueError, "Stale lab 10 export"):
                build(directory, check=True)


if __name__ == "__main__":
    unittest.main()
