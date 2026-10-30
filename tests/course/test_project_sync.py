import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts.course.project_sync import audit, graphql, managed_body, project_readme, publish_overview, resolve_cards, status_body, stored_value, update_fields, validate_plan


class ProjectRegisterTests(unittest.TestCase):
    def setUp(self):
        self.plan = json.loads((Path(__file__).resolve().parents[2] / "docs/projects/plan.json").read_text())

    def test_register_has_real_sources_and_all_fifteen_labs(self):
        self.assertEqual(validate_plan(self.plan), [])
        labs = {card["key"] for card in self.plan["cards"] if card["fields"]["Kind"] == "Lab"}
        self.assertEqual(labs, {f"LAB-{n:02d}" for n in range(1, 16)})

    def test_refresh_preserves_reporter_description_and_is_repeatable(self):
        card = self.plan["cards"][0]
        original = "Шаги пользователя\n\n![Снимок](https://example.com/screenshot.png)"
        first = managed_body(original, card, self.plan)
        self.assertTrue(first.startswith(original + "\n\n"))
        self.assertEqual(managed_body(first, card, self.plan), first)
        changed = copy.deepcopy(card)
        changed["summary"] = "Новая проверенная информация"
        updated = managed_body(first, changed, self.plan)
        self.assertIn(original, updated)
        self.assertIn(changed["summary"], updated)
        self.assertNotIn(card["summary"], updated)

    def test_incomplete_managed_section_is_never_silently_overwritten(self):
        card = self.plan["cards"][0]
        with self.assertRaises(ValueError):
            managed_body(f"User text\n<!-- sapar-project:{card['key']} -->", card, self.plan)

    def test_duplicate_remote_marker_cannot_create_or_edit_a_third_issue(self):
        card = self.plan["cards"][0]
        remote = {"issues": [{"number": card["issue"], "body": ""},
                             {"number": 9999, "body": f"<!-- sapar-project:{card['key']} -->"}]}
        with self.assertRaises(ValueError):
            resolve_cards({"cards": [card]}, remote)

    def test_done_cannot_be_inferred_from_automated_checks(self):
        plan = copy.deepcopy(self.plan)
        plan["cards"][0]["fields"]["Status"] = "Done"
        self.assertTrue(any("closure evidence" in row for row in validate_plan(plan)))

    def test_incomplete_readback_and_unmanaged_cards_fail_audit(self):
        plan = copy.deepcopy(self.plan)
        plan["cards"] = [plan["cards"][0]]
        plan["views"] = []
        plan.pop("readme_path", None)
        card = plan["cards"][0]
        remote = {"issues": [{"number": card["issue"], "body": managed_body(None, card, plan)}],
                  "items": [{"content": {"number": card["issue"]}, "status": "Ready"},
                            {"content": {"number": 9999}, "status": "Review"}],
                  "fields": [{"name": name} for name in plan["fields"]], "views": []}
        result = audit(plan, remote)
        self.assertFalse(result["passed"])
        self.assertEqual(result["unmanaged_issues"], [9999])
        self.assertIn(f"value:{card['key']}:Implementation", result["pending_changes"])

    def test_partial_graphql_result_does_not_count_as_success(self):
        class Response:
            returncode = 0
            stdout = '{"data": {"m0": null}, "errors": [{"message": "failure"}]}'
        with patch("scripts.course.project_sync.subprocess.run", return_value=Response()):
            with self.assertRaises(RuntimeError):
                graphql("mutation{test}")

    def test_source_must_stay_inside_repository(self):
        plan = copy.deepcopy(self.plan)
        with tempfile.TemporaryDirectory() as directory:
            plan["cards"][0]["sources"] = [str(Path(directory) / "outside.md")]
            self.assertTrue(any("unsafe source" in row for row in validate_plan(plan)))

    def test_repeated_overview_publication_does_not_create_a_second_update(self):
        plan = {**self.plan, "readme_path": "docs/project-board-workflow.md"}
        remote = {"items": [], "views": [], "project": {"id": "test-project"}, "status_updates": []}
        remote["project"]["readme"] = project_readme(plan, remote)
        remote["status_updates"] = [{"id": "existing-status", "body": status_body(plan, remote), "status": "AT_RISK"}]
        with patch("scripts.course.project_sync.graphql") as mutation:
            publish_overview(plan, remote)
        mutation.assert_not_called()

    def test_partial_field_batch_is_completed_by_smaller_idempotent_requests(self):
        with patch("scripts.course.project_sync.graphql", side_effect=[RuntimeError("partial response"), {}, {}]) as request:
            update_fields(["first", "second", "third", "fourth"])
        self.assertEqual(request.call_count, 3)
        self.assertIn("first", request.call_args_list[1].args[0])
        self.assertIn("second", request.call_args_list[1].args[0])
        self.assertIn("third", request.call_args_list[2].args[0])
        self.assertIn("fourth", request.call_args_list[2].args[0])

    def test_persistent_single_field_failure_is_never_counted_as_success(self):
        with patch("scripts.course.project_sync.graphql", side_effect=RuntimeError("unavailable")):
            with self.assertRaises(RuntimeError):
                update_fields(["only-field"])

    def test_wsjf_projection_obeys_github_decimal_limit_without_changing_source(self):
        raw = 29 / 3
        self.assertEqual(stored_value(raw, {"type": "NUMBER"}), 9.66666667)
        self.assertEqual(raw, 29 / 3)
        self.assertEqual(stored_value("2026-11-06", {"type": "DATE"}), "2026-11-06")
