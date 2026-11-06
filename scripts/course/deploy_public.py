"""Deploy a CI-verified commit on Render Free and record actual GitHub deployments.

Credentials are read from the environment and never written into the receipt.
Only the exact serving commit with a working catalog and SPA passes smoke.
"""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import time
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit
from urllib.request import Request, urlopen

REQUIRED_JOBS = {"backend", "frontend", "browser", "course", "security", "containers"}


class DeploymentError(RuntimeError):
    pass


def now():
    return datetime.now(timezone.utc).isoformat()


def request(url, *, method="GET", data=None, token=None):
    headers = {"Accept": "application/json", "User-Agent": "SaparTravel-deploy"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
        headers["X-GitHub-Api-Version"] = "2022-11-28"
    if data is not None:
        headers["Content-Type"] = "application/json"
    try:
        with urlopen(Request(url, data=json.dumps(data).encode() if data is not None else None,
                             headers=headers, method=method), timeout=30) as response:
            body = response.read(2_000_000)
            if "json" in response.headers.get("Content-Type", ""):
                try:
                    return response.status, json.loads(body)
                except (ValueError, UnicodeError):
                    raise DeploymentError("Invalid JSON response") from None
            return response.status, body.decode("utf-8", errors="replace")
    except HTTPError as error:
        # The hook URL contains a secret key; never include exception strings.
        raise DeploymentError(f"HTTP {error.code}") from None
    except (URLError, OSError, TimeoutError) as error:
        raise DeploymentError(type(error).__name__) from None


class GitHub:
    def __init__(self, repository, token):
        if not re.fullmatch(r"[\w.-]+/[\w.-]+", repository) or not token:
            raise DeploymentError("Set GITHUB_REPOSITORY and GH_TOKEN")
        self.base, self.token = f"https://api.github.com/repos/{repository}", token

    def call(self, path, *, data=None):
        return request(self.base + path, method="POST" if data is not None else "GET",
                       data=data, token=self.token)[1]

    def verify_ci(self, commit):
        runs = self.call(f"/actions/workflows/ci.yml/runs?head_sha={commit}&per_page=100")["workflow_runs"]
        candidates = [row for row in runs if row["head_sha"] == commit and row["head_branch"] == "main"
                      and row["event"] in {"push", "workflow_dispatch"} and row["conclusion"] == "success"]
        for run in sorted(candidates, key=lambda row: row["id"], reverse=True):
            jobs = self.call(f"/actions/runs/{run['id']}/jobs?per_page=100")["jobs"]
            successful = {job["name"] for job in jobs if job["conclusion"] == "success"}
            if REQUIRED_JOBS.issubset(successful):
                return run["id"]
        raise DeploymentError("The exact main commit needs all six successful CI jobs")

    def create_deployment(self, commit, url):
        result = self.call("/deployments", data={"ref": commit, "auto_merge": False, "required_contexts": [],
                           "environment": "public-demo", "production_environment": False,
                           "description": "Render Free: CI-verified application", "payload": {"url": url}})
        return result["id"]

    def status(self, deployment_id, state, url):
        self.call(f"/deployments/{deployment_id}/statuses", data={"state": state,
                  "environment_url": url, "auto_inactive": False,
                  "description": "Exact commit, health, catalog and frontend verified" if state == "success"
                                 else "Render rollout " + state})


def smoke(url, commit):
    try:
        _, release = request(url + "/api/v1/release")
        if not isinstance(release, dict) or release.get("commit") != commit or release.get("frontend") is not True:
            return False
        _, health = request(url + "/api/v1/health")
        _, catalog = request(url + "/api/v1/experiences")
        _, page = request(url + "/forgot-password")
        return (isinstance(health, dict) and health.get("status") == "ok" and isinstance(catalog, dict)
                and bool(catalog.get("items")) and isinstance(page, str) and 'id="root"' in page)
    except DeploymentError:
        return False


def hook_for_commit(hook, commit):
    parts = urlsplit(hook)
    query = parse_qs(parts.query)
    if (parts.scheme != "https" or parts.netloc != "api.render.com" or not parts.path.startswith("/deploy/srv-")
            or not query.get("key") or parts.fragment):
        raise DeploymentError("Set a valid secret Render deploy hook")
    query["ref"] = [commit]
    return urlunsplit(parts._replace(query=urlencode(query, doseq=True)))


def deploy(github, commit, url, hook, receipt, *, timeout=900, pause=10):
    if not re.fullmatch(r"[a-f0-9]{40}", commit):
        raise DeploymentError("Expected a full commit SHA")
    parts = urlsplit(url)
    if parts.scheme != "https" or not parts.hostname or parts.username or parts.password or parts.query or parts.fragment or parts.path:
        raise DeploymentError("PUBLIC_SITE_URL must be an HTTPS origin without a trailing slash")
    pinned_hook = hook_for_commit(hook, commit)
    receipt.update(commit=commit, environment="public-demo", url=url, checked_at_utc=now())
    receipt["ci_run_id"] = github.verify_ci(commit)
    if smoke(url, commit):
        receipt.update(state="already_serving", note="No rollout requested; no deployment counted")
        return
    # An accepted hook is a real rollout attempt, unlike a push or image build.
    status, result = request(pinned_hook, method="POST")
    if status not in {200, 202}:
        raise DeploymentError("Render did not accept the rollout")
    receipt.update(state="in_progress", requested_at_utc=now())
    if isinstance(result, dict):
        render_deploy = result.get("deploy", result)
        receipt["render_deploy_id"] = render_deploy.get("id") if isinstance(render_deploy, dict) else None
    deployment_id = github.create_deployment(commit, url)
    receipt["github_deployment_id"] = deployment_id
    try:
        github.status(deployment_id, "in_progress", url)
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if smoke(url, commit):
                github.status(deployment_id, "success", url)
                receipt.update(state="success", finished_at_utc=now(),
                               smoke=["exact_commit", "health", "catalog", "frontend_deep_link"])
                return
            time.sleep(pause)
        raise DeploymentError("Serving version did not pass smoke within the rollout timeout")
    except DeploymentError:
        receipt.update(state="failure", finished_at_utc=now())
        github.status(deployment_id, "failure", url)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--receipt", type=Path, default=Path("test-results/public-deployment.json"))
    args = parser.parse_args()
    receipt = {}
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    try:
        deploy(GitHub(os.environ.get("GITHUB_REPOSITORY", ""), os.environ.get("GH_TOKEN", "")), args.commit,
               os.environ.get("PUBLIC_SITE_URL", ""), os.environ.get("RENDER_DEPLOY_HOOK_URL", ""), receipt)
    except DeploymentError as error:
        receipt["error"] = str(error)
        raise SystemExit(f"Deployment failed: {error}") from None
    finally:
        args.receipt.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n")
    print(f"Public rollout: {receipt['state']}; {receipt['url']}")


if __name__ == "__main__":
    main()

