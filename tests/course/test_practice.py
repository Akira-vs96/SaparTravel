"""Protect calculation units and the boundary between exercises and real acceptance."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from zipfile import ZipFile

from scripts.course.audit import audit, source_paragraphs
from scripts.course.practice import ROOT, build, calculate_exercise, validate_exercise


def scenario(number):
    return json.loads((ROOT / f"docs/labs/lab-{number:02d}/practice/scenario.json").read_text())


class PracticeTests(unittest.TestCase):
    def test_financial_capacity_and_units_are_recalculated(self):
        baseline = calculate_exercise(3, scenario(3))
        self.assertEqual(baseline["saved_hours_per_week"], 22)
        self.assertEqual(baseline["annual_benefit_usd"], 21736)
        self.assertEqual(baseline["finance"]["tco"], "46000")
        capacity = calculate_exercise(5, scenario(5))
        self.assertEqual(capacity["baseline_capacity_hours"], 204)
        self.assertEqual(capacity["capacity_after_emv_and_management_hours"], 162)
        self.assertEqual(capacity["scope_reduction_hours"], 9)

    def test_full_incident_denominator_and_labor_are_distinct(self):
        result = calculate_exercise(10, scenario(10))
        self.assertEqual(result["deployment_frequency_per_week"], 2)
        self.assertEqual(result["lead_time_median_hours"], 2)
        self.assertEqual(result["change_failure_rate_percent"], 25)
        self.assertEqual(result["recovery_median_minutes"], 30)
        self.assertEqual(result["repair_labor_hours"], 2)
        self.assertAlmostEqual(result["reliability_capacity_fraction"], .025)
        self.assertFalse(result["human_events_confirmed"])

    def test_unprofitable_automation_and_timing_estimates_stay_honest(self):
        result = calculate_exercise(13, scenario(13))
        self.assertAlmostEqual(result["net_minutes_per_report"], 2.95)
        self.assertAlmostEqual(result["semester_net_minutes"], -324.6)
        self.assertGreater(result["payback_reports"], 122)
        self.assertFalse(result["economically_justified_this_semester"])
        rehearsal = calculate_exercise(15, scenario(15))
        self.assertIsNone(rehearsal["actual_person_rehearsal_seconds"])
        self.assertFalse(rehearsal["estimate_is_a_rehearsal"])

    def test_virtual_participants_cannot_certify_a_human_event(self):
        config = copy.deepcopy(scenario(4))
        config["human_events_confirmed"] = True
        with self.assertRaisesRegex(ValueError, "cannot certify human events"):
            validate_exercise(4, config)
        config = copy.deepcopy(scenario(6))
        config["stories"][0]["shown_simultaneously"] = False
        with self.assertRaisesRegex(ValueError, "constraints"):
            validate_exercise(6, config)

    def test_poker_comparison_keeps_bad_weeks_and_ai_metrics_match_raw_outputs(self):
        forecast = calculate_exercise(6, scenario(6))
        self.assertEqual(forecast["zero_weeks_in_history"], 2)
        self.assertGreater(forecast["monte_carlo_weeks"]["85"], forecast["point_forecast_weeks"])
        result = calculate_exercise(12, scenario(12))
        self.assertTrue(result["real_model_metrics_reproduced"])
        self.assertFalse(result["gold_human_approved"])
        self.assertEqual(result["examples"], 30)
        self.assertGreaterEqual(result["difficult_examples"], 5)

    def test_all_methodology_steps_have_exercises_but_acceptance_is_not_invented(self):
        result = build(check=True)
        self.assertEqual(result["requirements"], 275)
        self.assertTrue(result["all_requirements_covered"])
        self.assertFalse(result["course_factually_complete"])
        self.assertFalse(result["human_events_confirmed"])


class MethodologySourceTests(unittest.TestCase):
    def test_audit_reads_tracked_text_and_rejects_the_wrong_source_paragraph(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source.docx"
            xml = ('<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
                   '<w:body><w:p/><w:p><w:ins><w:r><w:t>Actual requirement</w:t></w:r></w:ins></w:p>'
                   '<w:p><w:r><w:t>Other requirement</w:t></w:r></w:p></w:body></w:document>')
            with ZipFile(source, "w") as archive:
                archive.writestr("word/document.xml", xml)
            self.assertEqual(source_paragraphs(source), ["Actual requirement", "Other requirement"])
            (root / "report.md").write_text("Prepared artifact")
            manifest = {"source": {"path": "source.docx", "sha256": hashlib.sha256(source.read_bytes()).hexdigest()},
                        "labs": [{"number": i, "report": "report.md", "steps": [{"id": f"L{i}", "status": "verified",
                                  "source_paragraph": 1, "text": "Actual requirement", "evidence": ["report.md"]}]} for i in range(1, 16)]}
            self.assertTrue(audit(manifest, root)["structure_valid"])
            manifest["labs"][0]["steps"][0]["source_paragraph"] = 2
            result = audit(manifest, root)
            self.assertFalse(result["structure_valid"])
            self.assertIn("original methodology paragraph", result["errors"][0])


if __name__ == "__main__":
    unittest.main()
