import unittest
from unittest.mock import patch

from scripts.course.github_facts import collect, project_membership


class ProjectCollectionTests(unittest.TestCase):
    @staticmethod
    def reply(*args):
        if args[:2] == ("project", "view"):
            return {"id": "project-target", "url": "https://github.com/users/owner/projects/2"}
        if args[:2] == ("project", "item-list"):
            return {"items": [], "totalCount": 0}
        if args[:2] == ("api", "graphql"):
            if 'node(id:' in args[-1]:
                return {"data": {"node": {"items": {"nodes": [], "pageInfo": {"hasNextPage": False}}}}}
            events = [{"__typename": "ProjectV2ItemStatusChangedEvent", "id": identity,
                       "createdAt": "2026-10-01T00:00:00Z", "previousStatus": "Ready", "status": "Done",
                       "project": {"id": project, "number": 2}}
                      for identity, project in [("foreign-event", "project-other-owner"), ("target-event", "project-target")]]
            return {"data": {"repository": {"issue": {"timelineItems": {
                "nodes": events, "pageInfo": {"hasNextPage": False}}}}}}
        if '/issues?' in args[-1]:
            return [[{"number": 1, "title": "Test issue", "state": "open", "created_at": "2026-10-01T00:00:00Z",
                      "closed_at": None, "labels": [], "html_url": "https://github.com/owner/repo/issues/1"}]]
        if '/actions/runs?' in args[-1]:
            return [{"workflow_runs": []}]
        return [[]]

    def test_projects_with_the_same_number_cannot_mix_owners_histories(self):
        with patch('scripts.course.github_facts.gh', side_effect=self.reply):
            result = collect('owner/repo', 'owner', 2)
        self.assertEqual([r['id'] for r in result['transitions']], ['target-event'])

    def test_repository_only_token_does_not_silently_claim_project_evidence(self):
        with patch('scripts.course.github_facts.gh', side_effect=self.reply) as requests:
            result = collect('owner/repo', 'owner', 2, include_project=False)
        self.assertEqual(result['project_evidence'], 'not_requested')
        self.assertEqual(result['project_item_metadata'], [])
        self.assertFalse(any(call.args[0] == 'project' for call in requests.call_args_list))

    def test_missing_project_cursor_fails_instead_of_certifying_all_members(self):
        responses = [{"id": "project-target", "url": "https://github.com/users/owner/projects/2"},
                     {"data": {"node": {"items": {"nodes": [], "pageInfo": {"hasNextPage": True, "endCursor": None}}}}}]
        with patch('scripts.course.github_facts.gh', side_effect=responses):
            with self.assertRaises(RuntimeError):
                project_membership('owner', 2)
