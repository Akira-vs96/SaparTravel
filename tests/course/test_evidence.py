import hashlib
import tempfile
from pathlib import Path
import unittest

from scripts.course.ai import baseline, numeric_discrepancies, quality
from scripts.course.audit import audit
from scripts.course.finance import raid_total
from scripts.course.forecast import simulate
from scripts.course.metrics import dora, flow, stamp
from scripts.course.prioritize import rank
from scripts.course.weekly_status import period_facts


class ForecastTests(unittest.TestCase):
    def test_zero_weeks_are_retained_and_seed_reproduces_the_distribution(self):
        weeks = simulate([0, 1], 2)
        self.assertEqual(weeks, simulate([0, 1], 2))
        self.assertEqual(len(weeks), 10000)
        self.assertGreater(sum(weeks) / len(weeks), 3.8)
        self.assertEqual(set(simulate([1], 2)), {2})

    def test_an_all_zero_history_cannot_fabricate_a_completion_date(self):
        for history in ([], [0, 0], [-1, 2]):
            with self.assertRaises(ValueError):
                simulate(history, 10)
        with self.assertRaises(ValueError):
            simulate([1], 10, runs=100)

    def test_empty_backlog_finishes_without_consuming_a_week(self):
        self.assertEqual(set(simulate([1], 0)), {0})


class MetricTests(unittest.TestCase):
    def setUp(self):
        self.start = stamp("2026-10-01T00:00:00Z")
        self.end = stamp("2026-10-08T00:00:00Z")
        self.facts = {"issues": [], "runs": [], "deployments": [], "project_items": [], "transitions": []}

    def test_created_to_done_is_not_reported_as_cycle_time(self):
        self.facts["transitions"] = [{"issue": 1, "at": "2026-10-02T00:00:00Z", "from": "Backlog", "to": "Done"}]
        result = flow(self.facts, self.start, self.end)
        self.assertEqual(result["throughput"], 1)
        self.assertIsNone(result["cycle_mean_days"])
        self.assertFalse(result["little_law_evaluable"])

    def test_initial_done_is_not_a_completion_in_the_period(self):
        self.facts["transitions"] = [{"issue": 1, "at": "2026-10-02T00:00:00Z", "from": "", "to": "Done"}]
        self.assertEqual(flow(self.facts, self.start, self.end)["throughput"], 0)

    def test_real_start_and_done_give_cycle_time_with_exclusive_end(self):
        self.facts["transitions"] = [
            {"issue": 1, "at": "2026-10-02T00:00:00Z", "from": "Ready", "to": "In progress"},
            {"issue": 1, "at": "2026-10-04T00:00:00Z", "from": "In progress", "to": "Done"},
            {"issue": 2, "at": "2026-10-08T00:00:00Z", "from": "Ready", "to": "Done"}]
        result = flow(self.facts, self.start, self.end)
        self.assertEqual(result["cycle_mean_days"], 2)
        self.assertEqual(result["completed_issues"], [1])

    def test_snapshot_disagreement_is_exposed_not_repaired_retroactively(self):
        self.facts["transitions"] = [{"issue": 1, "at": "2026-10-02T00:00:00Z", "from": "", "to": "Ready"}]
        self.facts["project_items"] = [{"content": {"number": 1}, "status": "Done"}]
        self.assertEqual(flow(self.facts, self.start, self.end)["history_snapshot_mismatches"], [1])

    def test_green_ci_does_not_create_a_deployment_or_zero_failure_rate(self):
        self.facts["runs"] = [{"created_at": "2026-10-02T00:00:00Z", "conclusion": "success"}]
        result = dora(self.facts, self.start, self.end)
        self.assertEqual(result["ci_success"], 1)
        self.assertIsNone(result["deployment_frequency_per_week"])
        self.assertIsNone(result["change_failure_rate_percent"])

    def test_real_deployment_and_incident_supply_the_denominators(self):
        self.facts["deployments"] = [{"id": 1, "state": "success", "created_at": "2026-10-02T00:00:00Z",
            "finished_at": "2026-10-03T00:00:00Z", "commit_at": "2026-10-02T00:00:00Z"}]
        incidents = [{"deployment_id": 1, "started_at": "2026-10-03T00:00:00Z", "recovered_at": "2026-10-03T00:10:00Z"}]
        result = dora(self.facts, self.start, self.end, incidents, True)
        self.assertEqual(result["deployment_frequency_per_week"], 1)
        self.assertEqual(result["lead_time_median_hours"], 24)
        self.assertEqual(result["change_failure_rate_percent"], 100)
        self.assertEqual(result["recovery_median_minutes"], 10)

    def test_incidents_cannot_use_an_unrelated_deployment_denominator(self):
        with self.assertRaises(ValueError):
            dora(self.facts, self.start, self.end, [{"deployment_id": 99, "started_at": "2026-10-03T00:00:00Z"}], True)

    def test_naive_timestamps_are_rejected(self):
        with self.assertRaises(ValueError):
            stamp("2026-10-01")


class EvidenceTests(unittest.TestCase):
    def test_missing_or_malformed_lab_artifacts_fail_the_structure_check(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "source").write_bytes(b"source")
            (root / "report").write_text("report")
            labs = [{"number": n, "report": "report", "steps": [{"id": f"L{n}",
                    "status": "verified", "evidence": ["report"]}]} for n in range(1, 16)]
            manifest = {"source": {"path": "source", "sha256": hashlib.sha256(b"source").hexdigest()}, "labs": labs}
            self.assertTrue(audit(manifest, root)["structure_valid"])
            for artifacts in ([{"path": "missing"}], ["report"], [{"path": "../outside"}]):
                labs[0]["artifacts"] = artifacts
                self.assertFalse(audit(manifest, root)["structure_valid"])

    def test_a_human_event_cannot_be_certified_by_a_generated_file(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "source.docx").write_bytes(b"source")
            labs = []
            for number in range(1, 16):
                report = f"lab{number}.md"
                (root / report).write_text("report")
                labs.append({"number": number, "report": report, "steps": [{"id": f"L{number}",
                    "status": "verified", "requires_people": True, "text": "Interview", "note": "No participant",
                    "evidence": [report]}]})
            result = audit({"source": {"path": "source.docx", "sha256": hashlib.sha256(b"source").hexdigest()}, "labs": labs}, root)
            self.assertFalse(result["structure_valid"])
            self.assertFalse(result["course_complete"])

    def test_raid_sum_is_not_a_manually_typed_total(self):
        rows = "\n".join(f"| R-{i:02d} | Risk | 0,1 | 10 | 1,0 | Owner |" for i in range(1, 21))
        with self.assertRaises(ValueError):
            raid_total(rows + "\n**Итого EMV:** 21,0")
        self.assertEqual(raid_total(rows + "\n**Итого EMV:** 20,0"), 20)

    def test_wsjf_uses_all_three_components_and_rejects_invalid_scores(self):
        rows = [{"id": "A", "value": 8, "urgency": 1, "risk_reduction": 1, "size": 13},
                {"id": "B", "value": 3, "urgency": 8, "risk_reduction": 13, "size": 3}]
        self.assertEqual(rank(rows)[0]["id"], "B")
        self.assertEqual(rank(rows)[0]["cost_of_delay"], 24)
        with self.assertRaises(ValueError):
            rank([{**rows[0], "size": 0}])

    def test_macro_f1_and_abstention_are_not_hidden_by_accuracy(self):
        labels = ["catalog", "access", "booking", "operations", "process"]
        self.assertEqual(quality(labels, labels)["macro_f1"], 1)
        result = quality(labels, ["catalog"] * 5)
        self.assertAlmostEqual(result["macro_f1"], 1 / 15)
        self.assertLess(result["macro_f1"], result["accuracy"])
        self.assertEqual(quality(labels, ["abstain"] * 5)["abstentions"], 5)

    def test_numeric_checker_reports_invented_numbers_but_never_claims_semantic_review(self):
        self.assertEqual(numeric_discrepancies("10 done, 100 approved", {"done": 10}), ["100"])
        self.assertEqual(baseline("непонятно"), "abstain")

    def test_weekly_facts_count_end_exclusively_and_keep_human_measurements_unknown(self):
        facts = {"issues": [{"created_at": "2026-10-01T00:00:00Z", "closed_at": "2026-10-08T00:00:00Z"}], "runs": [], "deployments": []}
        result = period_facts(facts, stamp("2026-10-01T00:00:00Z"), stamp("2026-10-08T00:00:00Z"))
        self.assertEqual(result["issues_created"], 1)
        self.assertEqual(result["issues_closed"], 0)
        self.assertIsNone(result["customer_approval"])
        self.assertIsNone(result["measured_manual_minutes"])


if __name__ == "__main__":
    unittest.main()
