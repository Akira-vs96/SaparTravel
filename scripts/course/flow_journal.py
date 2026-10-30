"""Record actual transitions now, anchored to an immutable Project snapshot."""
import argparse
import copy
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import uuid

from scripts.course.metrics import IN_PROGRESS, STATUSES, WIP, stamp

EVENTS_FILE = "events.jsonl"


def _now():
    return datetime.now(timezone.utc)


def _digest(value):
    raw = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()


def initialize(snapshot, directory):
    raw = snapshot.read_bytes()
    facts = json.loads(raw)
    if facts.get("project_evidence") != "requested" or facts.get("project_items_truncated"):
        raise ValueError("A complete current Project snapshot is required")
    if stamp(facts["captured_at_utc"]) > _now():
        raise ValueError("A future snapshot cannot establish an observation baseline")
    directory.mkdir(parents=True, exist_ok=True)
    if any(directory.iterdir()):
        raise ValueError("The journal directory must be empty; existing observations are never overwritten")
    config = {"schema_version": 1, "baseline_snapshot": os.path.relpath(snapshot.resolve(), directory.resolve()),
              "baseline_sha256": hashlib.sha256(raw).hexdigest(),
              "observation_started_at_utc": stamp(facts["captured_at_utc"]).isoformat(),
              "initialized_at_utc": _now().isoformat(),
              "scope": "Fixed baseline issue cohort; manual observations are separate from GitHub history"}
    (directory / "journal.json").write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n")
    (directory / EVENTS_FILE).touch()
    return config


def _baseline(directory):
    config = json.loads((directory / "journal.json").read_text())
    raw = (directory / config["baseline_snapshot"]).read_bytes()
    if hashlib.sha256(raw).hexdigest() != config["baseline_sha256"]:
        raise ValueError("The immutable baseline snapshot has changed")
    original = json.loads(raw)
    facts = {key: copy.deepcopy(original.get(key, [])) for key in ("project_items", "project_item_metadata")}
    facts.update(repository=original["repository"], project=original["project"],
                 project_evidence="manual_journal", captured_at_utc=config["observation_started_at_utc"],
                 observation_started_at_utc=config["observation_started_at_utc"],
                 membership_scope=config["scope"], transitions=[],
                 issues=[{"number": item["number"]} for item in original.get("issues", [])])
    for item in facts["project_items"]:
        content = item.get("content") or {}
        if content.get("type", "Issue") != "Issue" or content.get("repository", facts["repository"]) != facts["repository"]:
            continue
        facts["transitions"].append({"id": "baseline:" + item["id"], "issue": content["number"],
                                    "at": config["observation_started_at_utc"], "from": "", "to": item["status"],
                                    "source": "snapshot_observation"})
    return config, facts


def _items(facts):
    return {item["content"]["number"]: item for item in facts["project_items"]
            if (item.get("content") or {}).get("type", "Issue") == "Issue"
            and (item.get("content") or {}).get("repository", facts["repository"]) == facts["repository"]}


def _check_transition(facts, row):
    items = _items(facts)
    item = items.get(row["issue"])
    if item is None or item.get("status") != row["from"]:
        raise ValueError("Issue or previous status does not match the recorded state")
    if row["to"] not in STATUSES or row["to"] == "Unknown" or row["to"] == row["from"]:
        raise ValueError("Expected a real transition to a configured status")
    review = sum(item.get("status") == "Review" for item in items.values())
    new_start = row["to"] == IN_PROGRESS and row["from"] not in WIP
    if (new_start or row["to"] == "Review") and review >= 3:
        raise ValueError("Review WIP is full; resolve existing review before pulling more work")
    if row["to"] == IN_PROGRESS:
        if not row.get("owner"):
            raise ValueError("A confirmed work owner is required when work starts")
        active = sum(item.get("status") == IN_PROGRESS
                     and (item.get("owner") or "").strip().casefold() == row["owner"].casefold()
                     for item in items.values())
        if active >= 2:
            raise ValueError("The owner already has two tasks in progress")


def _apply(facts, row):
    if not row.get("actor") or not row.get("reference"):
        raise ValueError("Every observation needs an actor and evidence reference")
    at = stamp(row["at"])
    if at < stamp(facts["captured_at_utc"]) or at > _now():
        raise ValueError("Observations cannot move time backwards or claim a future event")
    if row["kind"] == "transition":
        _check_transition(facts, row)
        item = _items(facts)[row["issue"]]
        item["status"] = row["to"]
        if row.get("owner"):
            item["owner"] = row["owner"]
        facts["transitions"].append({"id": row["id"], "issue": row["issue"], "at": row["at"],
                                    "from": row["from"], "to": row["to"],
                                    "actor": row["actor"], "reference": row["reference"], "source": "manual_journal"})
    elif row["kind"] != "checkpoint":
        raise ValueError("Unknown observation kind")
    facts["captured_at_utc"] = at.isoformat()


def _replay(directory, stream):
    config, facts = _baseline(directory)
    previous, ids = config["baseline_sha256"], set()
    stream.seek(0)
    for line in stream:
        row = json.loads(line)
        digest = row.pop("sha256")
        if row["previous_sha256"] != previous or _digest(row) != digest or row["id"] in ids:
            raise ValueError("Journal history was changed or duplicated")
        _apply(facts, row)
        previous = digest
        ids.add(row["id"])
    return facts, previous


def record(directory, *, actor, reference, issue=None, status=None, owner=None):
    """Timestamp a factual transition or an explicit end-of-window checkpoint."""
    with (directory / EVENTS_FILE).open("a+", encoding="utf-8") as stream:
        fcntl.flock(stream, fcntl.LOCK_EX)
        facts, previous = _replay(directory, stream)
        row = {"id": str(uuid.uuid4()), "kind": "transition" if issue is not None else "checkpoint",
               "at": _now().isoformat(), "actor": actor.strip(), "reference": reference.strip(),
               "previous_sha256": previous}
        if issue is not None:
            item = _items(facts).get(issue)
            row.update(issue=issue, to=status, owner=owner.strip() if owner else None,
                       **{"from": item.get("status") if item else None})
        _apply(facts, row)
        row["sha256"] = _digest(row)
        stream.seek(0, os.SEEK_END)
        stream.write(json.dumps(row, ensure_ascii=False) + "\n")
        stream.flush()
        os.fsync(stream.fileno())
    return row


def export(directory, output):
    with (directory / EVENTS_FILE).open(encoding="utf-8") as stream:
        fcntl.flock(stream, fcntl.LOCK_SH)
        facts, last = _replay(directory, stream)
    facts["journal"] = {"last_sha256": last, "scope": "Statements by the recorded actors; hashes do not certify human identity or a meeting"}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(facts, ensure_ascii=False, indent=2) + "\n")
    return facts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True)
    commands = parser.add_subparsers(dest="command", required=True)
    init = commands.add_parser("init")
    init.add_argument("--snapshot", type=Path, required=True)
    transition = commands.add_parser("transition")
    transition.add_argument("--issue", type=int, required=True)
    transition.add_argument("--to", required=True, choices=[s for s in STATUSES if s != "Unknown"])
    transition.add_argument("--owner")
    checkpoint = commands.add_parser("checkpoint")
    for command in (transition, checkpoint):
        command.add_argument("--actor", required=True)
        command.add_argument("--reference", required=True)
    commands.add_parser("export").add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "init":
            initialize(args.snapshot, args.directory)
        elif args.command == "export":
            facts = export(args.directory, args.output)
            print("Exported observations through " + facts["captured_at_utc"])
        else:
            row = record(args.directory, actor=args.actor, reference=args.reference,
                         issue=getattr(args, "issue", None), status=getattr(args, "to", None),
                         owner=getattr(args, "owner", None))
            print("Recorded " + row["kind"] + " at " + row["at"])
    except (OSError, KeyError, ValueError) as error:
        raise SystemExit(str(error)) from None


if __name__ == "__main__":
    main()
