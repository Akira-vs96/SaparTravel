"""Regressions for actual gaps and reopened work in Project history."""
import unittest
import csv
import hashlib
import json
from pathlib import Path
import tempfile

from scripts.course.metrics import cfd, flow, flow_details, stamp
from scripts.course.flow_report import build


def event(at, before, after, issue=1):
    return {"issue": issue, "at": at, "from": before, "to": after}


class FlowHistoryTests(unittest.TestCase):
    def setUp(self):
        self.start = stamp("2026-10-01T00:00:00Z")
        self.end = stamp("2026-10-08T00:00:00Z")
        self.facts = {"issues": [], "project_items": [], "transitions": []}

    def test_completion_before_window_resets_the_next_reopened_cycle(self):
        self.facts["transitions"] = [
            event("2026-09-01T00:00:00Z", "Ready", "In progress"),
            event("2026-09-02T00:00:00Z", "In progress", "Done"),
            event("2026-10-02T00:00:00Z", "Done", "Ready"),
            event("2026-10-03T00:00:00Z", "Ready", "In progress"),
            event("2026-10-04T00:00:00Z", "In progress", "Done")]
        self.assertEqual(flow(self.facts, self.start, self.end)["cycle_mean_days"], 1)

    def test_a_missing_transition_invalidates_the_cycle_and_exposure(self):
        self.facts["transitions"] = [
            event("2026-10-01T00:00:00Z", "Ready", "In progress"),
            event("2026-10-03T00:00:00Z", "Review", "Done")]
        result = flow(self.facts, self.start, self.end)
        self.assertIsNone(result["cycle_mean_days"])
        self.assertFalse(result["little_law_evaluable"])
        self.assertGreater(result["observed_status_task_days"]["Unknown"], 0)

    def test_initial_in_progress_is_a_censored_start(self):
        self.facts["transitions"] = [
            event("2026-10-01T00:00:00Z", "", "In progress"),
            event("2026-10-03T00:00:00Z", "In progress", "Done")]
        result = flow(self.facts, self.start, self.end)
        self.assertEqual(result["throughput"], 1)
        self.assertIsNone(result["cycle_mean_days"])

    def test_timezone_offsets_are_ordered_by_instant(self):
        self.facts["transitions"] = [
            event("2026-10-02T09:00:00+05:00", "Ready", "In progress"),
            event("2026-10-02T05:00:00Z", "In progress", "Done")]
        self.assertAlmostEqual(flow(self.facts, self.start, self.end)["cycle_mean_days"], 1 / 24)

    def test_duplicate_or_noop_done_is_not_an_extra_completion(self):
        self.facts["transitions"] = [
            event("2026-10-01T00:00:00Z", "Ready", "In progress"),
            event("2026-10-02T00:00:00Z", "In progress", "Done"),
            event("2026-10-03T00:00:00Z", "Done", "Done")]
        result = flow(self.facts, self.start, self.end)
        self.assertEqual(result["completion_events"], 1)
        self.assertEqual(result["cycle_time_samples"], 1)

    def test_partial_cycle_samples_do_not_certify_little_law(self):
        self.facts["transitions"] = [
            event("2026-10-01T00:00:00Z", "Ready", "In progress"),
            event("2026-10-02T00:00:00Z", "In progress", "Done"),
            event("2026-10-02T00:00:00Z", "Ready", "Done", 2)]
        result = flow(self.facts, self.start, self.end)
        self.assertEqual(result["throughput"], 2)
        self.assertEqual(result["cycle_time_samples"], 1)
        self.assertFalse(result["little_law_evaluable"])

    def test_cfd_has_explicit_utc_time_and_every_status_even_when_zero(self):
        self.facts["transitions"] = [event("2026-10-01T12:00:00Z", "", "Ready")]
        rows = cfd(self.facts, self.start, self.end)
        self.assertEqual(rows[0]["at_utc"], self.start.isoformat())
        self.assertEqual(rows[0]["Ready"], 0)
        self.assertEqual(rows[1]["Ready"], 1)
        for row in rows:
            for status in ["Backlog", "Ready", "In progress", "Review", "Blocked", "Done", "Unknown"]:
                self.assertIn(status, row)

    def test_cfd_does_not_backdate_the_current_snapshot_across_a_gap(self):
        self.facts["transitions"] = [event("2026-09-28T00:00:00Z", "", "Ready")]
        self.facts["project_items"] = [{"content": {"number": 1}, "status": "Done"}]
        rows = cfd(self.facts, self.start, self.end)
        self.assertEqual(rows[0]["Ready"], 0)
        self.assertEqual(rows[0]["Done"], 0)
        self.assertEqual(rows[0]["Unknown"], 1)

    def test_invalid_windows_and_naive_datetimes_are_rejected(self):
        naive_start = self.start.replace(tzinfo=None)
        for function in (flow, cfd):
            with self.assertRaises(ValueError):
                function(self.facts, self.end, self.start)
            with self.assertRaises(ValueError):
                function(self.facts, naive_start, self.end)

    def test_complete_exposure_supplies_a_checkable_little_law(self):
        self.facts.update(captured_at_utc="2026-10-08T00:00:00Z",
                          project_items=[{"content": {"number": 1}, "status": "Done"}],
                          project_item_metadata=[{"issue": 1, "created_at": "2026-10-01T00:00:00Z"}])
        self.facts["transitions"] = [event("2026-10-01T00:00:00Z", "Ready", "In progress"),
                                    event("2026-10-02T00:00:00Z", "In progress", "Done")]
        result = flow(self.facts, self.start, self.end)
        self.assertTrue(result["little_law_evaluable"])
        self.assertAlmostEqual(result["average_wip"], 1 / 7)
        self.assertEqual(result["little_wip_difference"], 0)

    def test_issue_creation_does_not_backdate_project_membership(self):
        self.facts["issues"] = [{"number": 1, "created_at": "2026-09-01T00:00:00Z"}]
        self.facts["project_item_metadata"] = [{"issue": 1, "created_at": "2026-10-03T00:00:00Z"}]
        self.facts["transitions"] = [event("2026-10-04T00:00:00Z", "", "Ready")]
        rows = cfd(self.facts, self.start, self.end)
        self.assertEqual(rows[1]["tracked_items"], 0)
        self.assertEqual(rows[2]["Unknown"], 1)
        self.assertEqual(rows[3]["Ready"], 1)

    def test_unknown_custom_stage_is_retained_in_the_unknown_band(self):
        self.facts["transitions"] = [event("2026-10-01T00:00:00Z", "", "QA")]
        self.assertEqual(cfd(self.facts, self.start, self.end)[1]["Unknown"], 1)

    def test_duplicate_event_ids_do_not_double_count_exposure(self):
        row = {**event("2026-10-01T00:00:00Z", "", "Ready"), "id": "event-1"}
        self.facts["transitions"] = [row, row]
        result = flow(self.facts, self.start, self.end)
        self.assertEqual(result["data_quality"]["duplicate_events_removed"], 1)
        self.assertEqual(result["observed_status_task_days"]["Ready"], 7)

    def test_future_observations_cannot_be_reported_from_an_old_capture(self):
        self.facts["captured_at_utc"] = "2026-10-02T00:00:00Z"
        with self.assertRaises(ValueError):
            cfd(self.facts, self.start, self.end)

    def test_returning_from_review_keeps_the_current_cycle_start(self):
        self.facts["transitions"] = [event("2026-10-01T00:00:00Z", "Ready", "In progress"),
                                    event("2026-10-02T00:00:00Z", "In progress", "Review"),
                                    event("2026-10-03T00:00:00Z", "Review", "In progress"),
                                    event("2026-10-04T00:00:00Z", "In progress", "Done")]
        self.assertEqual(flow(self.facts, self.start, self.end)["cycle_mean_days"], 3)

    def test_rework_counts_unique_items_and_uses_the_final_cycle(self):
        self.facts["transitions"] = [event("2026-10-01T00:00:00Z", "Ready", "In progress"),
                                    event("2026-10-02T00:00:00Z", "In progress", "Done"),
                                    event("2026-10-03T00:00:00Z", "Done", "In progress"),
                                    event("2026-10-05T00:00:00Z", "In progress", "Done")]
        result = flow(self.facts, self.start, self.end)
        self.assertEqual(result["throughput"], 1)
        self.assertEqual(result["completion_events"], 2)
        self.assertEqual(result["cycle_time_samples"], 1)
        self.assertEqual(result["cycle_mean_days"], 2)

    def test_p85_uses_the_interpolation_from_the_methodology_calc_formula(self):
        self.facts["transitions"] = [
            event("2026-10-01T00:00:00Z", "Ready", "In progress", issue)
            for issue in (1, 2)] + [
            event("2026-10-02T00:00:00Z", "In progress", "Done", 1),
            event("2026-10-04T00:00:00Z", "In progress", "Done", 2)]
        self.assertAlmostEqual(flow(self.facts, self.start, self.end)["cycle_p85_days"], 2.7)

    def test_the_actual_for_test_column_has_known_exposure_and_counts_as_wip(self):
        self.facts.update(captured_at_utc="2026-10-08T00:00:00Z",
                          project_items=[{"content": {"number": 1}, "status": "Done"}],
                          project_item_metadata=[{"issue": 1, "created_at": "2026-10-01T00:00:00Z"}])
        self.facts["transitions"] = [
            event("2026-10-01T00:00:00Z", "Ready", "In progress"),
            event("2026-10-02T00:00:00Z", "In progress", "FOR TEST"),
            event("2026-10-03T00:00:00Z", "FOR TEST", "Done")]
        result = flow(self.facts, self.start, self.end)
        self.assertEqual(result["observed_status_task_days"]["Unknown"], 0)
        self.assertAlmostEqual(result["average_wip"], 2 / 7)
        self.assertEqual(cfd(self.facts, self.start, self.end)[1]["FOR TEST"], 1)

    def test_daily_wip_integrates_intraday_work_that_midnight_cfd_does_not_show(self):
        self.facts.update(captured_at_utc=self.end.isoformat(),
                          project_items=[{"content": {"number": 1}, "status": "Done"}],
                          project_item_metadata=[{"issue": 1, "created_at": self.start.isoformat()}])
        self.facts["transitions"] = [event("2026-10-01T00:00:00Z", "", "Ready"),
                                    event("2026-10-01T09:00:00Z", "Ready", "In progress"),
                                    event("2026-10-01T17:00:00Z", "In progress", "Done")]
        result = flow_details(self.facts, self.start, self.end)
        self.assertAlmostEqual(result["daily_wip"][0]["average_wip"], 8 / 24)
        self.assertTrue(all(r["In progress"] == 0 for r in cfd(self.facts, self.start, self.end)))
        self.assertAlmostEqual(result["items"][0]["status_task_days"]["In progress"], 8 / 24)
        self.assertEqual(sum(result["items"][0]["status_task_days"].values()), 7)
        self.assertEqual(result["items"][0]["completion"]["issue"], 1)

    def test_little_law_uses_consistent_working_day_units_including_cycles(self):
        self.facts.update(captured_at_utc=self.end.isoformat(),
                          project_items=[{"content": {"number": 1}, "status": "Done"}],
                          project_item_metadata=[{"issue": 1, "created_at": "2026-10-02T12:00:00Z"}])
        self.facts["transitions"] = [event("2026-10-02T12:00:00Z", "Ready", "In progress"),
                                    event("2026-10-05T12:00:00Z", "In progress", "Done")]
        result = flow(self.facts, self.start, self.end)
        working = result["working_time"]
        self.assertEqual(result["cycle_mean_days"], 3)
        self.assertEqual(working["working_days"], 5)
        self.assertEqual(working["cycle_mean_days"], 1)
        self.assertAlmostEqual(working["average_wip"], .2)
        self.assertEqual(working["little_wip_difference"], 0)

    def test_weekend_only_window_does_not_divide_by_zero_working_days(self):
        start, end = stamp("2026-10-03T00:00:00Z"), stamp("2026-10-05T00:00:00Z")
        result = flow(self.facts, start, end)["working_time"]
        self.assertEqual(result["working_days"], 0)
        self.assertIsNone(result["average_wip"])
        self.assertIsNone(result["little_expected_wip"])
        self.assertFalse(result["little_law_evaluable"])

    def test_report_package_preserves_source_identity_and_csv_json_agreement(self):
        self.facts["transitions"] = [event("2026-10-01T00:00:00Z", "", "Ready")]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'snapshot.json'
            source.write_text(json.dumps(self.facts))
            output = root / 'report'
            build(source, self.start, self.end, output, plot=False)
            report = json.loads((output / 'flow.json').read_text())
            rows = json.loads((output / 'cfd.json').read_text())
            with (output / 'cfd.csv').open() as stream:
                exported = list(csv.DictReader(stream))
            self.assertEqual(report['source_sha256'], hashlib.sha256(source.read_bytes()).hexdigest())
            self.assertFalse(report['periods_are_confirmed_sprints'])
            self.assertEqual(len(rows), len(exported))
            self.assertEqual([r['at_utc'] for r in rows], [r['at_utc'] for r in exported])
            self.assertEqual([r['Review'] for r in rows], [int(r['Review']) for r in exported])
            for name in ('item-times.csv', 'daily-wip.csv', 'comparison.csv', 'board-policy.json'):
                self.assertTrue((output / name).is_file())
            with (output / 'comparison.csv').open() as stream:
                comparison = list(csv.DictReader(stream))
            self.assertEqual(len(comparison), 1)
            self.assertEqual(comparison[0]['working_days'], '5.0')


if __name__ == "__main__":
    unittest.main()
