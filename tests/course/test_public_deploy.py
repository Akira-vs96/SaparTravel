import json
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError

from scripts.course.deploy_public import DeploymentError, GitHub, REQUIRED_JOBS, deploy, request, smoke

SHA = "a" * 40
URL = "https://sapartravel-test.onrender.com"
HOOK = "https://api.render.com/deploy/srv-example?key=private-test-value"


class PublicDeployTests(unittest.TestCase):
    def test_no_rollout_or_deployment_when_exact_version_is_already_healthy(self):
        github, receipt = Mock(), {}
        with patch("scripts.course.deploy_public.smoke", return_value=True), patch("scripts.course.deploy_public.request") as http:
            deploy(github, SHA, URL, HOOK, receipt)
        github.verify_ci.assert_called_once_with(SHA)
        github.create_deployment.assert_not_called()
        http.assert_not_called()
        self.assertEqual(receipt["state"], "already_serving")

    def test_hook_acceptance_precedes_real_deployment_and_exact_version_smoke(self):
        github, receipt = Mock(), {}
        github.create_deployment.return_value = 42
        github.verify_ci.return_value = 5
        with patch("scripts.course.deploy_public.smoke", side_effect=[False, False, True]), \
                patch("scripts.course.deploy_public.request", return_value=(200, {"deploy": {"id": "dep-1"}})) as http, \
                patch("scripts.course.deploy_public.time.sleep"):
            deploy(github, SHA, URL, HOOK, receipt)
        self.assertIn("ref=" + SHA, http.call_args.args[0])
        self.assertEqual(receipt["render_deploy_id"], "dep-1")
        self.assertEqual(receipt["state"], "success")
        self.assertEqual([call.args[1] for call in github.status.call_args_list], ["in_progress", "success"])
        self.assertNotIn("private-test-value", json.dumps(receipt))

    def test_rejected_hook_never_creates_a_deployment(self):
        github = Mock()
        with patch("scripts.course.deploy_public.smoke", return_value=False), \
                patch("scripts.course.deploy_public.request", side_effect=DeploymentError("HTTP 404")):
            with self.assertRaisesRegex(DeploymentError, "404"):
                deploy(github, SHA, URL, HOOK, {})
        github.create_deployment.assert_not_called()

    def test_timeout_records_a_failure_and_never_success(self):
        github, receipt = Mock(), {}
        with patch("scripts.course.deploy_public.smoke", return_value=False), \
                patch("scripts.course.deploy_public.request", return_value=(202, {})):
            with self.assertRaisesRegex(DeploymentError, "timeout"):
                deploy(github, SHA, URL, HOOK, receipt, timeout=0)
        self.assertEqual(receipt["state"], "failure")
        self.assertEqual(github.status.call_args.args[1], "failure")

    def test_smoke_requires_exact_sha_and_nonempty_catalog(self):
        valid = [(200, {"commit": SHA, "frontend": True}), (200, {"status": "ok"}),
                 (200, {"items": [{"id": 1}]}), (200, '<html><div id="root"></div></html>')]
        with patch("scripts.course.deploy_public.request", side_effect=valid):
            self.assertTrue(smoke(URL, SHA))
        with patch("scripts.course.deploy_public.request", return_value=(200, {"commit": "b" * 40, "frontend": True})):
            self.assertFalse(smoke(URL, SHA))
        valid[2] = (200, {"items": []})
        with patch("scripts.course.deploy_public.request", side_effect=valid):
            self.assertFalse(smoke(URL, SHA))

    def test_ci_must_belong_to_main_commit_and_include_all_six_jobs(self):
        github = GitHub("owner/repo", "test-token")
        run = {"id": 5, "head_sha": SHA, "head_branch": "main", "event": "push", "conclusion": "success"}
        jobs = [{"name": name, "conclusion": "success"} for name in REQUIRED_JOBS]
        with patch.object(github, "call", side_effect=[{"workflow_runs": [run]}, {"jobs": jobs}]):
            self.assertEqual(github.verify_ci(SHA), 5)
        with patch.object(github, "call", side_effect=[{"workflow_runs": [run]}, {"jobs": jobs[:-1]}]):
            with self.assertRaises(DeploymentError):
                github.verify_ci(SHA)
        with patch.object(github, "call", return_value={"workflow_runs": [{**run, "event": "pull_request"}]}):
            with self.assertRaises(DeploymentError):
                github.verify_ci(SHA)

    def test_transport_error_does_not_expose_the_hook_key(self):
        error = HTTPError(HOOK, 404, "private-test-value", {}, None)
        with patch("scripts.course.deploy_public.urlopen", side_effect=error):
            with self.assertRaises(DeploymentError) as raised:
                request(HOOK, method="POST")
        self.assertEqual(str(raised.exception), "HTTP 404")


if __name__ == "__main__":
    unittest.main()
