"""Single-run jobs for systemd timers; secrets come only from the operator environment."""
import argparse
from datetime import datetime, timedelta, timezone
import fcntl
import json
import os
from pathlib import Path
import shutil
from zoneinfo import ZoneInfo

from scripts.availability_probe import Config, run_probe
from scripts.availability_report import aggregate
from scripts.monthly_service_report import build_report
from scripts.database_recovery import (connection_config, create_backup, data_age,
                                       restore_drill, verified_manifest, write_json)


def latest_backup(directory):
    candidates = sorted(directory.glob("sapartravel-*.dump.json"), reverse=True)
    if not candidates:
        raise ValueError("No backup manifest is available")
    # The newest failed or corrupted copy must not be hidden by choosing an older one.
    manifest, _ = verified_manifest(candidates[0])
    return candidates[0], manifest


def copy_backup(manifest_path, destination):
    manifest, archive = verified_manifest(manifest_path)
    destination.mkdir(parents=True, exist_ok=True, mode=0o700)
    if destination.resolve() == archive.parent.resolve():
        raise ValueError("The second backup destination must differ from the first")
    for source in (archive, manifest_path):
        target = destination / source.name
        with source.open("rb") as incoming, target.open("xb") as outgoing:
            os.chmod(target, 0o600)
            shutil.copyfileobj(incoming, outgoing)
            outgoing.flush()
            os.fsync(outgoing.fileno())
    verified_manifest(destination / manifest_path.name)
    return manifest["sha256"]


def run_job(command):
    directory = Path(os.environ.get("BACKUP_DIRECTORY", "backups"))
    reports = Path(os.environ.get("OPS_REPORT_DIRECTORY", "test-results/ops"))
    pg_bin = Path(os.environ["PG_BIN_DIRECTORY"]) if os.environ.get("PG_BIN_DIRECTORY") else None
    now = datetime.now(timezone.utc)
    stamp = now.strftime("%Y%m%dT%H%M%S.%fZ")
    if command == "report":
        local = now.astimezone(ZoneInfo("Asia/Almaty"))
        previous = local.replace(day=1) - timedelta(days=1)
        month = previous.strftime("%Y-%m")
        source = Path(os.environ["MONTHLY_INPUT_DIRECTORY"])
        deployment = json.loads((source / "deployment.json").read_text())
        agreement_path = source / ("agreement-" + month + ".json")
        agreement = json.loads(agreement_path.read_text()) if agreement_path.exists() else None
        records = []
        for path in sorted((source / "observations").glob("*.jsonl")):
            for line in path.read_text().splitlines():
                try:
                    records.append(json.loads(line))
                except ValueError:
                    records.append(None)
        availability = aggregate(records, month=month, points=deployment["points"], deployment_id=deployment["deployment_id"],
                                 scope=deployment["scope"], agreement=agreement)
        support_path = source / ("support-" + month + ".json")
        support = json.loads(support_path.read_text()) if support_path.exists() else None
        recoveries = [json.loads(path.read_text()) for path in (source / "recoveries").glob("*.json")]
        report = build_report(availability=availability, support=support, recoveries=recoveries, agreement=agreement)
        write_json(reports / ("service-" + month + "-" + stamp + ".json"), report)
        return report["status"] == "complete_evidence"
    if command == "probe":
        config = Config(**json.loads(Path(os.environ["SLI_CONFIG"]).read_text()))
        observation = run_probe(config, os.environ.get("SLI_EMAIL", ""), os.environ.get("SLI_PASSWORD", ""))
        path = Path(os.environ["SLI_LOG"])
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        with os.fdopen(fd, "a") as output:
            output.write(json.dumps(observation, allow_nan=False) + "\n")
        return observation["success"]
    if command == "backup":
        config = connection_config(os.environ.get("BACKUP_DATABASE_URL"))
        manifest = create_backup(config, directory, pg_bin)
        second = os.environ.get("BACKUP_COPY_DIRECTORY")
        copied = bool(second)
        if copied:
            copy_backup(manifest, Path(second))
        write_json(reports / ("backup-" + stamp + ".json"), {"kind": "scheduled-backup", "completed_at_utc": now.isoformat(),
                   "manifest": manifest.name, "second_copy_verified": copied, "passed": True})
        return True
    manifest_path, manifest = latest_backup(directory)
    if command == "age":
        age = data_age(manifest, now)
        passed = age <= 86400
        write_json(reports / ("age-" + stamp + ".json"), {"kind": "scheduled-backup-age", "checked_at_utc": now.isoformat(),
                   "age_upper_bound_seconds": age, "rpo_target_seconds": 86400, "passed": passed})
        return passed
    config = connection_config(os.environ.get("RESTORE_ADMIN_DATABASE_URL"), restore=True)
    report = restore_drill(config, manifest_path, now, pg_bin)
    write_json(reports / ("restore-" + stamp + ".json"), report)
    return report["passed"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("probe", "backup", "age", "restore", "report"))
    args = parser.parse_args()
    lock_path = Path(os.environ.get("OPS_LOCK_DIRECTORY", "/tmp/sapartravel-ops-locks"))
    try:
        lock_path.mkdir(parents=True, exist_ok=True, mode=0o700)
        # One environment/unit per probe host; a missed run remains a missing observation.
        with (lock_path / (args.command + ".lock")).open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            passed = run_job(args.command)
        print(json.dumps({"event": "ops." + args.command, "passed": passed, "timestamp_utc": datetime.now(timezone.utc).isoformat()}))
        return 0 if passed else 1
    except Exception as error:
        print(json.dumps({"event": "ops." + args.command, "passed": False, "error_type": type(error).__name__}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
