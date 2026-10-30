"""Reconcile the actual GitHub Project with a reviewed, evidence-backed work register."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PLAN = ROOT / "docs/projects/plan.json"


def gh(*args):
    result = subprocess.run(["gh", *args], capture_output=True, text=True, timeout=120)
    if result.returncode:
        raise RuntimeError(f"GitHub operation failed: {' '.join(args[:2])}; no credentials were logged")
    return json.loads(result.stdout) if result.stdout.strip().startswith(("{", "[")) else result.stdout.strip()


def graphql(query, variables=None):
    result = subprocess.run(["gh", "api", "graphql", "--input", "-"],
                            input=json.dumps({"query": query, "variables": variables or {}}),
                            capture_output=True, text=True, timeout=120)
    if result.returncode:
        raise RuntimeError("GitHub GraphQL request failed; no response bodies or credentials were logged")
    value = json.loads(result.stdout)
    if value.get("errors"):
        raise RuntimeError("GitHub returned an incomplete Project result")
    return value["data"]


def marker(key):
    return f"<!-- sapar-project:{key} -->"


def managed_body(original, card, plan):
    """Replace our own section; preserve the reporter's original description."""
    start, end = marker(card["key"]), "<!-- /sapar-project -->"
    base = (original or "").strip()
    if start in base:
        pattern = re.escape(start) + r".*?" + re.escape(end)
        base, count = re.subn(pattern, "", base, flags=re.S)
        if count != 1:
            raise ValueError("A managed issue section is duplicated or incomplete")
        base = base.strip()
    links = "\n".join(f"- [{path}]({plan['source_url']}/{path})" for path in card["sources"])
    criteria = "\n".join(f"- {text}" for text in card["acceptance"])
    fields = card["fields"]
    section = (f"{start}\n## Состояние и подтверждения — {plan['as_of']}\n\n{card['summary']}\n\n"
               f"Реализация: **{fields['Implementation']}**. Проверка: **{fields['Verification']}**. "
               f"Статус Project: **{fields['Status']}**.\n\n"
               f"Контакт для передачи: {fields['Owner']}. Поле Owner не удостоверяет авторство кода "
               "или проведённую независимую приёмку. Размер — оценка, а не фактические часы.\n\n"
               f"### Критерии проверки\n\n{criteria}\n\n### Реализация и проверки\n\n{links}\n\n"
               f"Зависимости / следующий шаг: {fields['Dependencies']}\n\n"
               f"Связанные ЛЗ: {fields['Lab']}. Risk ID: {fields['Risk ID']}.\n\n"
               f"[Проверенный CI]({plan['ci_url']}) · [Доска]({plan['project_url']})\n{end}")
    return (base + "\n\n" if base else "") + section + "\n"


def validate_plan(plan, root=ROOT):
    errors, keys, issues = [], set(), set()
    for card in plan["cards"]:
        if card["key"] in keys or not re.fullmatch(r"[A-Z0-9-]+", card["key"]):
            errors.append(f"Invalid/duplicate key: {card['key']}")
        keys.add(card["key"])
        if card.get("issue") in issues:
            errors.append(f"Duplicate existing issue: {card['issue']}")
        if card.get("issue"):
            issues.add(card["issue"])
        if len(card.get("acceptance", [])) < 2:
            errors.append(f"Positive and negative/limitation criteria required: {card['key']}")
        for source in card["sources"]:
            path = root / source
            if not path.resolve().is_relative_to(root.resolve()) or not path.is_file():
                errors.append(f"Missing/unsafe source: {source}")
        for name in plan["required_fields"]:
            if not card["fields"].get(name):
                errors.append(f"Missing {name}: {card['key']}")
        for name, value in card["fields"].items():
            spec = plan["fields"].get(name, {})
            if spec.get("options") and value not in spec["options"]:
                errors.append(f"Unknown {name}: {value}")
        if card["fields"]["Status"] == "Done" and not card.get("preserve_closed"):
            errors.append(f"Done needs existing closure evidence: {card['key']}")
    return errors


def read_remote(plan):
    owner, number, repo = plan["owner"], str(plan["number"]), plan["repository"]
    project = gh("project", "view", number, "--owner", owner, "--format", "json")
    fields = gh("project", "field-list", number, "--owner", owner, "--format", "json", "--limit", "100")["fields"]
    result = gh("project", "item-list", number, "--owner", owner, "--format", "json", "--limit", "1000")
    if result["totalCount"] != len(result["items"]):
        raise ValueError("Project item collection is incomplete")
    issues = [{key: row.get(key) for key in ("number", "node_id", "title", "body", "state", "html_url", "created_at", "updated_at", "closed_at")}
              for page in gh("api", "--paginate", "--slurp", f"repos/{repo}/issues?state=all&per_page=100")
              for row in page if "pull_request" not in row]
    metadata = graphql('query($id:ID!){node(id:$id){... on ProjectV2{views(first:100){nodes{id name number layout filter '
                       'configuration{visibleFields(first:50){nodes{... on ProjectV2Field{id name} '
                       '... on ProjectV2SingleSelectField{id name} ... on ProjectV2IterationField{id name}}}}}} '
                       'statusUpdates(first:30){nodes{id body createdAt status}}}}}', {"id": project["id"]})["node"]
    return {"captured_at_utc": datetime.now(timezone.utc).isoformat(), "project": project, "fields": fields,
            "items": result["items"], "issues": issues, "views": metadata["views"]["nodes"],
            "status_updates": metadata["statusUpdates"]["nodes"]}


def resolve_cards(plan, remote):
    resolved, used = [], set()
    for card in plan["cards"]:
        candidates = [r for r in remote["issues"] if r["number"] == card.get("issue") or marker(card["key"]) in (r.get("body") or "")]
        if len(candidates) > 1:
            raise ValueError(f"Duplicate issue identity: {card['key']}")
        issue = candidates[0] if candidates else None
        if issue and issue["number"] in used:
            raise ValueError("An issue is mapped to multiple work items")
        if issue:
            used.add(issue["number"])
        resolved.append((card, issue))
    return resolved


def field_key(name):
    return name[0].lower() + name[1:]


def stored_value(value, spec):
    # Observed GitHub validation: NUMBER fields accept at most eight decimal places.
    # Keep the full WSJF calculation in the source register, round only its projection.
    return round(value, 8) if spec["type"] == "NUMBER" else value


def status_body(plan, remote):
    counts = Counter(row.get("status", "Unknown") for row in remote["items"])
    features = [row for row in remote["items"] if row.get("kind") == "Feature"]
    implemented = sum(row.get("implementation") == "Implemented" for row in features)
    views = "\n".join(f"- [{row['name']}]({plan['project_url']}/views/{row['number']})" for row in remote["views"])
    rows = "\n".join(f"| [#{row['content']['number']} {row['title']}](https://github.com/{plan['repository']}/issues/{row['content']['number']}) | {row.get('implementation', '')} | {row.get('verification', '')} |"
                     for row in features)
    return ("<!-- sapar-project-status -->\n"
            f"## Состояние SaparTravel — {plan['as_of']}\n\n"
            "**Жёлтый / AT_RISK:** реализация и автоматические проверки подтверждены; "
            "независимая приёмка и внешние сервисы ещё требуют решений.\n\n"
            f"- **Вехи:** {len(remote['items'])} работ; {implemented}/{len(features)} функций реализованы; "
            "15 карточек ЛЗ с отчётами; существующие закрытия issues сохранены.\n"
            f"- **Поток:** {json.dumps(dict(counts), ensure_ascii=False)}. "
            "Переклассификация очереди не является ростом throughput или измерением двух спринтов.\n"
            f"- **Надёжность:** [CI {plan['verified_source_commit'][:7]}]({plan['ci_url']}) успешен; "
            "96 серверных тестов и восемь браузерных наборов. Зарегистрированных production deployments нет; DORA не подменяется CI.\n"
            "- **Деньги:** план и резерв — в финансовой модели ЛЗ8; подтверждённого факта платежей/трудозатрат нет.\n"
            "- **Риски:** открыты #39 (количество туристов) и #40 (редактура KK); "
            "зелёные тесты не закрывают эти пользовательские замечания.\n"
            "- **Зависимости:** SMTP-доступы, банковский провайдер, внешний UAT и эксплуатационная среда "
            "выделены отдельными карточками. Следующая предложенная проверка — 06.11.2026.\n\n"
            "**Нужно решение:** назначить принимающего и сроки UAT, предоставить настройки SMTP/среду, "
            "подтвердить календарь поддержки и объём банковской интеграции. "
            "По умолчанию продолжаются внутренние проверки; внешняя приёмка и эксплуатационный SLA не объявляются принятыми.\n\n"
            f"### Представления\n\n{views}\n\n### Функции сайта\n\n"
            f"| Функция | Реализация | Проверка |\n|---|---|---|\n{rows}\n\n"
            f"[Правила и источники]({plan['source_url']}/docs/project-board-workflow.md) · "
            f"[Реестр]({plan['source_url']}/docs/projects/plan.json)")


def project_readme(plan, remote):
    source = ROOT / plan["readme_path"]
    def absolute(match):
        label, target = match.group(1), match.group(2).strip("<>")
        if "://" in target or target.startswith("#"):
            return match.group(0)
        path = (source.parent / target).resolve().relative_to(ROOT.resolve()).as_posix()
        return f"[{label}]({plan['source_url']}/{path})"
    policy = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", absolute, source.read_text())
    return status_body(plan, remote) + "\n\n---\n\n" + policy


def publish_overview(plan, remote):
    body = status_body(plan, remote)
    readme = project_readme(plan, remote)
    if remote["project"].get("readme") != readme:
        graphql('mutation($input:UpdateProjectV2Input!){updateProjectV2(input:$input){projectV2{id}}}',
                {"input": {"projectId": remote["project"]["id"], "readme": readme,
                           "shortDescription": "Функции сайта, проверки, лабораторные, зависимости и портфель WSJF с источниками"}})
    previous = [row for row in remote["status_updates"] if "<!-- sapar-project-status -->" in (row.get("body") or "")]
    if len(previous) > 1:
        raise ValueError("Duplicate managed Project status updates")
    if not previous:
        graphql('mutation($input:CreateProjectV2StatusUpdateInput!){createProjectV2StatusUpdate(input:$input){statusUpdate{id}}}',
                {"input": {"projectId": remote["project"]["id"], "body": body, "status": "AT_RISK"}})
    elif previous[0]["body"] != body or previous[0]["status"] != "AT_RISK":
        graphql('mutation($input:UpdateProjectV2StatusUpdateInput!){updateProjectV2StatusUpdate(input:$input){statusUpdate{id}}}',
                {"input": {"statusUpdateId": previous[0]["id"], "body": body, "status": "AT_RISK"}})
    print("Published Project README and status update", flush=True)


def expected_changes(plan, remote):
    changes = []
    fields = {r["name"] for r in remote["fields"]}
    changes.extend(f"field:{name}" for name in plan["fields"] if name not in fields)
    items = {(r.get("content") or {}).get("number"): r for r in remote["items"]}
    for card, issue in resolve_cards(plan, remote):
        if issue is None:
            changes.append(f"issue:{card['key']}")
            continue
        if managed_body(issue.get("body"), card, plan) != issue.get("body"):
            changes.append(f"description:{card['key']}")
        item = items.get(issue["number"])
        if item is None:
            changes.append(f"membership:{card['key']}")
            continue
        if card.get("preserve_closed") and issue["state"] != "closed":
            changes.append(f"closure-evidence:{card['key']}")
        for name, value in card["fields"].items():
            value = stored_value(value, plan["fields"][name])
            if item.get(field_key(name)) != value:
                changes.append(f"value:{card['key']}:{name}")
    views = {r["name"]: r for r in remote["views"]}
    for spec in plan["views"]:
        view = views.get(spec["name"])
        if view is None or view["layout"] != spec["layout"] or view["filter"] != spec["filter"]:
            changes.append(f"view:{spec['name']}")
        elif [r["name"] for r in view["configuration"]["visibleFields"]["nodes"]] != spec["visible"]:
            changes.append(f"view-fields:{spec['name']}")
    if plan.get("readme_path"):
        if remote["project"].get("readme") != project_readme(plan, remote):
            changes.append("project-readme")
        statuses = [row for row in remote["status_updates"] if "<!-- sapar-project-status -->" in (row.get("body") or "")]
        if len(statuses) != 1 or statuses[0]["body"] != status_body(plan, remote) or statuses[0]["status"] != "AT_RISK":
            changes.append("project-status-update")
    return changes


def save_body(text, operation):
    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", encoding="utf-8") as stream:
        stream.write(text)
        stream.flush()
        return operation(stream.name)


def update_fields(mutations):
    """Only field setters are idempotent: a timed-out batch can partially commit."""
    try:
        return graphql("mutation{" + " ".join(f"m{i}:{value}" for i, value in enumerate(mutations)) + "}")
    except RuntimeError:
        if len(mutations) <= 1:
            raise
        middle = len(mutations) // 2
        print(f"Retrying {len(mutations)} idempotent field setters in smaller batches", flush=True)
        update_fields(mutations[:middle])
        update_fields(mutations[middle:])


def apply_plan(plan, remote):
    owner, number, repo = plan["owner"], str(plan["number"]), plan["repository"]
    present = {r["name"] for r in remote["fields"]}
    for name, spec in plan["fields"].items():
        if name not in present:
            args = ["project", "field-create", number, "--owner", owner, "--name", name,
                    "--data-type", spec["type"], "--format", "json"]
            if spec.get("options"):
                args.extend(["--single-select-options", ",".join(spec["options"])])
            gh(*args)
            print(f"Created field: {name}", flush=True)
    for card, issue in resolve_cards(plan, remote):
        if card.get("preserve_closed") and (not issue or issue["state"] != "closed"):
            raise ValueError("Existing closure evidence changed; no issue is automatically closed")
        body = managed_body(issue.get("body") if issue else None, card, plan)
        if issue is None:
            url = save_body(body, lambda path: gh("issue", "create", "--repo", repo, "--title", card["title"],
                                                 "--body-file", path, "--assignee", owner,
                                                 "--label", card.get("label", "enhancement")))
            issue = {"number": int(url.rsplit("/", 1)[-1]), "html_url": url}
            print(f"Created {card['key']}: #{issue['number']}", flush=True)
        elif body != issue.get("body"):
            graphql('mutation($input:UpdateIssueInput!){updateIssue(input:$input){issue{id}}}',
                    {"input": {"id": issue["node_id"], "body": body}})
        if not any((item.get("content") or {}).get("number") == issue["number"] for item in remote["items"]):
            gh("project", "item-add", number, "--owner", owner, "--url", issue["html_url"], "--format", "json")
    remote = read_remote(plan)
    fields = {r["name"]: r for r in remote["fields"]}
    items = {(r.get("content") or {}).get("number"): r for r in remote["items"]}
    mutations = []
    for card, issue in resolve_cards(plan, remote):
        item = items[issue["number"]]
        for name, expected in card["fields"].items():
            expected = stored_value(expected, plan["fields"][name])
            if item.get(field_key(name)) == expected:
                continue
            field = fields[name]
            spec = plan["fields"][name]
            if spec["type"] == "SINGLE_SELECT":
                value = {"singleSelectOptionId": next(row["id"] for row in field["options"] if row["name"] == expected)}
            else:
                value = {{"NUMBER": "number", "DATE": "date"}.get(spec["type"], "text"): expected}
            encoded = "{" + ",".join(key + ":" + json.dumps(value) for key, value in value.items()) + "}"
            mutations.append('updateProjectV2ItemFieldValue(input:{projectId:' + json.dumps(remote["project"]["id"])
                             + ',itemId:' + json.dumps(item["id"]) + ',fieldId:' + json.dumps(field["id"])
                             + ',value:' + encoded + '}){projectV2Item{id}}')
    for offset in range(0, len(mutations), 20):
        batch = mutations[offset:offset + 20]
        update_fields(batch)
        print(f"Updated Project fields: {min(offset + 20, len(mutations))}/{len(mutations)}", flush=True)
    views = {r["name"]: r for r in remote["views"]}
    for spec in plan["views"]:
        view = views.get(spec["name"])
        config = {"visibleFieldIds": [fields[name]["id"] for name in spec["visible"]]}
        if (view is not None and view["layout"] == spec["layout"] and view["filter"] == spec["filter"]
                and [row["id"] for row in view["configuration"]["visibleFields"]["nodes"]] == config["visibleFieldIds"]):
            continue
        if view is None:
            created = graphql('mutation($input:CreateProjectV2ViewInput!){createProjectV2View(input:$input){projectV2View{id}}}',
                              {"input": {"projectId": remote["project"]["id"], "name": spec["name"], "layout": spec["layout"], "configuration": config}})
            view = created["createProjectV2View"]["projectV2View"]
        graphql('mutation($input:UpdateProjectV2ViewInput!){updateProjectV2View(input:$input){projectV2View{id}}}',
                {"input": {"viewId": view["id"], "name": spec["name"], "layout": spec["layout"], "filter": spec["filter"], "configuration": config}})
        print(f"Saved view: {spec['name']}", flush=True)
    return read_remote(plan)


def audit(plan, remote):
    changes = expected_changes(plan, remote)
    mapped = {issue["number"] for _, issue in resolve_cards(plan, remote) if issue}
    unmanaged = [r.get("content", {}).get("number") for r in remote["items"] if r.get("content", {}).get("number") not in mapped]
    counts = Counter(r.get("status", "Unknown") for r in remote["items"])
    return {"passed": not changes and not unmanaged, "pending_changes": changes, "unmanaged_issues": unmanaged,
            "items": len(remote["items"]), "views": len(remote["views"]), "status_counts": dict(counts),
            "implementation_counts": dict(Counter(r.get("implementation", "Unknown") for r in remote["items"])),
            "kind_counts": dict(Counter(r.get("kind", "Unknown") for r in remote["items"])),
            "review_limit": 3, "review_limit_passed": counts["Review"] <= 3,
            "meaning": "Administrative reconciliation is not historical delivery, independent acceptance, or measured flow improvement"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, default=DEFAULT_PLAN)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--apply", action="store_true", help="Apply the explicit register; default is read-only")
    parser.add_argument("--check", action="store_true", help="Fail if the remote Project differs from the register")
    args = parser.parse_args()
    plan = json.loads(args.plan.read_text())
    errors = validate_plan(plan)
    if errors:
        raise SystemExit("\n".join(errors))
    remote = read_remote(plan)
    if args.apply:
        remote = apply_plan(plan, remote)
        if plan.get("readme_path"):
            publish_overview(plan, remote)
            remote = read_remote(plan)
    result = {**remote, "audit": audit(plan, remote), "plan_date": plan["as_of"],
              "verified_source_commit": plan["verified_source_commit"], "ci_url": plan["ci_url"]}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    summary = {key: value for key, value in result["audit"].items() if key != "pending_changes"}
    summary["pending_changes_count"] = len(result["audit"]["pending_changes"])
    print(json.dumps(summary, ensure_ascii=False))
    if args.check and not result["audit"]["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
