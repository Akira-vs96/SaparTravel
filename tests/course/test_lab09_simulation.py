"""Validate model accounting, the one-change experiment and separation from real records."""
import copy
import csv
import json
from pathlib import Path
import tempfile
import unittest

from scripts.course.flow_journal import initialize
from scripts.course.lab09_simulation import ROOT, acceptance, build, effects, experiment, validate_config

SCENARIO = ROOT / "docs/labs/lab-09/simulation/scenario.json"


class Lab09SimulationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = json.loads(SCENARIO.read_text())
        cls.result = experiment(cls.config)

    def test_complete_model_has_all_seventeen_requirements_and_consistent_accounting(self):
        result = self.result
        checked = acceptance(result, self.config)
        self.assertTrue(checked["simulation_complete"])
        self.assertEqual(len(checked["requirements"]), 17)
        self.assertFalse(checked["real_sprints_confirmed"])
        for row in result["periods"]:
            self.assertEqual(row["throughput"], 10)
            self.assertEqual(row["cycle_time_samples"], 10)
            self.assertEqual(row["observed_status_task_days"]["Unknown"], 0)
            self.assertAlmostEqual(row["little_wip_difference"], 0)
            self.assertAlmostEqual(row["working_time"]["little_wip_difference"], 0)
        first = result["periods"][0]["completed_items"][0]
        second = result["periods"][1]["completed_items"][0]
        self.assertAlmostEqual(first["cycle_days"] * 24, 7.5)
        self.assertAlmostEqual(second["cycle_days"] * 24, 2.5)

    def test_counterfactual_and_deterministic_inputs_preserve_the_negative_result(self):
        repeated = experiment(self.config)
        self.assertEqual(repeated["facts"], self.result["facts"])
        self.assertAlmostEqual(self.result["counterfactual"]["cycle_mean_days"], self.result["periods"][0]["cycle_mean_days"])
        change = effects(self.result)
        self.assertGreater(change["cycle_mean_change_percent"], 0)
        self.assertLess(change["cycle_p85_change_percent"], 0)
        self.assertEqual(change["daily_review_minutes_before"], change["daily_review_minutes_after"])
        for run in self.result["runs"]:
            self.assertTrue(all(row["Review"] <= 3 and row["active"] <= 8 for row in run.trace))
            self.assertTrue(all(n <= 2 for row in run.trace for n in row["per_owner"].values()))

    def test_every_export_is_labelled_and_model_cannot_initialize_a_real_journal(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "simulation"
            build(SCENARIO, output, plot=False)
            for path in (output / "evidence").glob("*.json"):
                self.assertEqual(json.loads(path.read_text())["data_kind"], "educational_simulation", path.name)
            for path in (output / "evidence").glob("*.csv"):
                with path.open() as stream:
                    rows = list(csv.DictReader(stream))
                self.assertTrue(rows)
                self.assertTrue(all(row["data_kind"] == "educational_simulation" for row in rows), path.name)
            facts = output / "evidence/facts.json"
            journal = Path(temporary) / "journal"
            with self.assertRaisesRegex(ValueError, "current Project snapshot"):
                initialize(facts, journal)

    def test_real_history_and_declared_review_capacity_are_protected(self):
        real_output = ROOT / "docs/labs/lab-09/evidence"
        with self.assertRaisesRegex(ValueError, "real Lab 9 history"):
            build(SCENARIO, real_output, plot=False)
        config = copy.deepcopy(self.config)
        config["review_slots_after"] = ["16:00", "16:00"]
        with self.assertRaisesRegex(ValueError, "Overlapping"):
            validate_config(config)


if __name__ == "__main__":
    unittest.main()
