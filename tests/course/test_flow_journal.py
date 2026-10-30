"""Integrity, WIP and real-time boundaries of the Lab 9 manual journal."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts.course.flow_journal import export, initialize, record
from scripts.course.metrics import flow, stamp


class FlowJournalTests(unittest.TestCase):
    def setUp(self):
        self.scratch = tempfile.TemporaryDirectory()
        self.addCleanup(self.scratch.cleanup)
        self.root = Path(self.scratch.name)
        self.source = self.root / "github.json"
        self.directory = self.root / "journal"
        self.start = stamp("2026-11-02T00:00:00Z")
        self.end = stamp("2026-11-09T00:00:00Z")
        facts = {"repository": "owner/repo", "project": {"id": "project"},
                 "project_evidence": "requested", "captured_at_utc": self.start.isoformat(),
                 "project_items": [{"id": f"item-{n}", "content": {"number": n}, "status": "Ready"} for n in (1, 2, 3, 4)],
                 "project_item_metadata": [{"issue": n, "created_at": self.start.isoformat()} for n in (1, 2, 3, 4)]}
        self.source.write_text(json.dumps(facts))
        with patch("scripts.course.flow_journal._now", return_value=self.start):
            initialize(self.source, self.directory)

    def record_at(self, instant, **kwargs):
        with patch("scripts.course.flow_journal._now", return_value=stamp(instant)):
            return record(self.directory, actor="dev", reference="fixture: observed work", **kwargs)

    def export_at(self, instant):
        with patch("scripts.course.flow_journal._now", return_value=stamp(instant)):
            return export(self.directory, self.root / "export.json")

    def test_observed_journal_drives_full_cycle_metrics_without_backdating(self):
        self.record_at("2026-11-02T12:00:00Z", issue=1, status="In progress", owner="dev")
        self.record_at("2026-11-03T12:00:00Z", issue=1, status="FOR TEST")
        self.record_at("2026-11-04T12:00:00Z", issue=1, status="Review")
        self.record_at("2026-11-05T12:00:00Z", issue=1, status="Done")
        self.record_at(self.end.isoformat())
        facts = self.export_at(self.end.isoformat())
        result = flow(facts, self.start, self.end)
        self.assertEqual(result["throughput"], 1)
        self.assertEqual(result["cycle_mean_days"], 3)
        self.assertTrue(result["data_quality"]["coverage_complete"])
        self.assertEqual(result["little_wip_difference"], 0)
        earlier = stamp("2026-11-01T00:00:00Z")
        with self.assertRaisesRegex(ValueError, "first real observation"):
            flow(facts, earlier, self.end)

    def test_review_limit_blocks_new_work_and_releases_only_after_actual_exit(self):
        for issue in (1, 2, 3):
            self.record_at("2026-11-02T12:00:00Z", issue=issue, status="Review")
        with self.assertRaisesRegex(ValueError, "Review WIP"):
            self.record_at("2026-11-02T13:00:00Z", issue=4, status="In progress", owner="dev")
        self.record_at("2026-11-02T13:00:00Z", issue=1, status="Done")
        self.record_at("2026-11-02T14:00:00Z", issue=4, status="In progress", owner="dev")
        self.assertEqual(self.export_at(self.end.isoformat())["project_items"][3]["status"], "In progress")

    def test_resolving_existing_review_into_rework_is_allowed_at_a_full_queue(self):
        for issue in (1, 2, 3):
            self.record_at("2026-11-02T12:00:00Z", issue=issue, status="Review")
        self.record_at("2026-11-02T13:00:00Z", issue=1, status="In progress", owner="dev")
        self.assertEqual(self.export_at(self.end.isoformat())["project_items"][0]["status"], "In progress")

    def test_third_task_for_one_owner_is_rejected_without_writing_an_event(self):
        for issue in (1, 2):
            self.record_at("2026-11-02T12:00:00Z", issue=issue, status="In progress", owner="dev")
        before = (self.directory / "events.jsonl").read_bytes()
        with self.assertRaisesRegex(ValueError, "two tasks"):
            self.record_at("2026-11-02T13:00:00Z", issue=3, status="In progress", owner=" DEV ")
        self.assertEqual((self.directory / "events.jsonl").read_bytes(), before)

    def test_changed_baseline_or_journal_history_is_not_silently_accepted(self):
        self.record_at("2026-11-02T12:00:00Z", issue=1, status="In progress", owner="dev")
        path = self.directory / "events.jsonl"
        original = path.read_text()
        path.write_text(original.replace('"to": "In progress"', '"to": "Done"'))
        instant = self.end.isoformat()
        with self.assertRaisesRegex(ValueError, "changed or duplicated"):
            self.export_at(instant)
        path.write_text(original)
        self.source.write_text(self.source.read_text() + " ")
        with self.assertRaisesRegex(ValueError, "baseline snapshot has changed"):
            self.export_at(instant)

    def test_export_does_not_claim_observation_after_the_last_record(self):
        self.record_at("2026-11-02T12:00:00Z", issue=1, status="Review")
        facts = self.export_at(self.end.isoformat())
        self.assertEqual(stamp(facts["captured_at_utc"]), stamp("2026-11-02T12:00:00Z"))
        with self.assertRaisesRegex(ValueError, "beyond the evidence capture"):
            flow(facts, self.start, self.end)

    def test_unattributed_event_and_start_without_owner_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "actor and evidence"):
            record(self.directory, actor="", reference="", issue=1, status="Review")
        with self.assertRaisesRegex(ValueError, "confirmed work owner"):
            self.record_at("2026-11-02T12:00:00Z", issue=1, status="In progress")

    def test_reinitialization_preserves_the_existing_journal(self):
        self.record_at("2026-11-02T12:00:00Z", issue=1, status="Review")
        before = (self.directory / "events.jsonl").read_bytes()
        with patch("scripts.course.flow_journal._now", return_value=self.start):
            with self.assertRaisesRegex(ValueError, "never overwritten"):
                initialize(self.source, self.directory)
        self.assertEqual((self.directory / "events.jsonl").read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
