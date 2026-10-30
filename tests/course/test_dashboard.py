from html import unescape
import unittest
from unittest.mock import patch

from scripts.course.dashboard import render


class DashboardProjectTests(unittest.TestCase):
    def test_actual_project_snapshot_drives_counts_views_and_feature_links(self):
        snapshot = {"captured_at_utc": "2026-10-31T05:00:00+00:00", "project": {"url": "https://github.com/users/owner/projects/2"},
                    "items": [{"kind": "Feature", "implementation": "Implemented", "verification": "Automated",
                               "title": "Feature <safe>", "content": {"number": 101}, "area": "Catalog", "status": "FOR TEST"}],
                    "issues": [{"state": "open"}], "views": [{"number": 7, "name": "Implemented"}],
                    "audit": {"passed": True, "review_limit_passed": True, "status_counts": {"FOR TEST": 1}}}
        with patch("scripts.course.dashboard.read", side_effect=lambda path: snapshot if path == "docs/projects/evidence/current.json" else {}):
            html = render()
        self.assertIn(snapshot["captured_at_utc"], html)
        self.assertIn("/projects/2/views/7", html)
        self.assertIn("/SaparTravel/issues/101", html)
        self.assertIn("Feature &lt;safe&gt;", html)
        self.assertIn('функций в Project": 1', unescape(html))
        self.assertIn('реализовано функций": 1', unescape(html))
        self.assertEqual(html.count('class="panel"'), 6)

    def test_missing_snapshot_is_not_reported_as_verified_project(self):
        with patch("scripts.course.dashboard.read", return_value=None):
            html = render()
        self.assertIn("исторический снимок", html)
        self.assertIn('полнота Project проверена": "нет данных"', unescape(html))
