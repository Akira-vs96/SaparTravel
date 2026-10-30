"""Read-only GitHub evidence collection. Credentials stay inside the gh process."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import subprocess


def gh(*args):
    result = subprocess.run(["gh", *args], capture_output=True, text=True, timeout=120)
    if result.returncode:
        raise RuntimeError("GitHub request failed; check gh authentication and repository access")
    value = json.loads(result.stdout)
    if isinstance(value, dict) and value.get("errors"):
        raise RuntimeError("GitHub returned incomplete GraphQL evidence")
    return value


def pages(endpoint):
    return [row for page in gh("api", "--paginate", "--slurp", endpoint) for row in page]


def collect(repo, owner, project, *, include_project=True):
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo):
        raise ValueError("Expected owner/repository")
    repository_owner, name = repo.split("/")
    raw_issues = pages(f"repos/{repo}/issues?state=all&per_page=100")
    issues = [{"number": r["number"], "title": r["title"], "body": r.get("body") or "",
               "state": r["state"], "created_at": r["created_at"], "closed_at": r["closed_at"],
               "labels": [label["name"] for label in r["labels"]], "url": r["html_url"]}
              for r in raw_issues if "pull_request" not in r]
    runs = [r for page in gh("api", "--paginate", "--slurp", f"repos/{repo}/actions/runs?per_page=100")
            for r in page["workflow_runs"]]
    runs = [{key: r.get(key) for key in ("id", "name", "event", "head_sha", "head_branch", "status",
                                       "conclusion", "created_at", "updated_at", "run_started_at", "html_url")}
            for r in runs]
    items = gh("project", "item-list", str(project), "--owner", owner, "--format", "json", "--limit", "1000") if include_project else {"items": [], "totalCount": 0}
    transitions = []
    truncated = []
    # Per-issue pagination preserves the actual transition timestamps and statuses.
    for issue in issues if include_project else []:
        cursor = None
        while True:
            after = ',after:' + json.dumps(cursor) if cursor else ''
            query = ('{repository(owner:' + json.dumps(repository_owner) + ',name:' + json.dumps(name)
                     + '){issue(number:' + str(issue["number"]) + '){timelineItems(first:100' + after
                     + '){pageInfo{hasNextPage endCursor} nodes{__typename ... on ProjectV2ItemStatusChangedEvent'
                     + '{createdAt previousStatus status project{number url}}}}}}}')
            timeline = gh("api", "graphql", "-f", "query=" + query)["data"]["repository"]["issue"]["timelineItems"]
            for event in timeline["nodes"]:
                if event.get("__typename") == "ProjectV2ItemStatusChangedEvent" and (event.get("project") or {}).get("number") == project:
                    transitions.append({"issue": issue["number"], "at": event["createdAt"],
                                        "from": event["previousStatus"], "to": event["status"]})
            if not timeline["pageInfo"]["hasNextPage"]:
                break
            cursor = timeline["pageInfo"]["endCursor"]
    commits = pages(f"repos/{repo}/commits?per_page=100")
    commit_dates = {r["sha"]: r["commit"]["committer"]["date"] for r in commits}
    deployments = []
    for deployment in pages(f"repos/{repo}/deployments?per_page=100"):
        statuses = pages(f"repos/{repo}/deployments/{deployment['id']}/statuses?per_page=100")
        terminal = next((r for r in statuses if r["state"] in {"success", "failure", "error"}), None)
        deployments.append({"id": deployment["id"], "sha": deployment["sha"],
                            "environment": deployment["environment"], "created_at": deployment["created_at"],
                            "finished_at": terminal["created_at"] if terminal else None,
                            "state": terminal["state"] if terminal else None,
                            "commit_at": commit_dates.get(deployment["sha"])})
    return {"schema_version": 1, "repository": repo,
            "captured_at_utc": datetime.now(timezone.utc).isoformat(),
            "sources": [f"https://github.com/{repo}/issues", f"https://github.com/{repo}/actions",
                        f"https://github.com/users/{owner}/projects/{project}"],
            "issues": issues, "runs": runs, "project_items": items["items"],
            "project_items_truncated": items["totalCount"] > len(items["items"]),
            "project_evidence": "requested" if include_project else "not_requested",
            "transitions": sorted(transitions, key=lambda r: r["at"]),
            "truncated_timelines": truncated, "deployments": deployments}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default="Akira-vs96/SaparTravel")
    parser.add_argument("--owner", default="Akira-vs96")
    parser.add_argument("--project", type=int, default=2)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--skip-project", action="store_true", help="For status drafts using a read-only repository token")
    args = parser.parse_args()
    try:
        result = collect(args.repo, args.owner, args.project, include_project=not args.skip_project)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
        print(f"Collected {len(result['issues'])} issues, {len(result['runs'])} CI runs and {len(result['deployments'])} deployments")
    except (OSError, ValueError, RuntimeError, KeyError):
        raise SystemExit("Evidence collection failed; no credentials or remote response bodies are logged") from None


if __name__ == "__main__":
    main()
