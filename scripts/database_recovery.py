"""Verified PostgreSQL backups and restore drills; never overwrite a database.

Connection secrets are read only from BACKUP_DATABASE_URL or
RESTORE_ADMIN_DATABASE_URL, never from the application's .env or command line.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import time
from urllib.parse import unquote, urlsplit

import psycopg
from psycopg import sql


class RecoveryError(Exception):
    """Fixed diagnostics which cannot disclose connection secrets or row values."""


def utc_now():
    return datetime.now(timezone.utc)


def timestamp(value):
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if result.tzinfo is None:
            raise ValueError
        return result.astimezone(timezone.utc)
    except (ValueError, TypeError, AttributeError):
        raise RecoveryError("Timestamp must include its timezone") from None


def connection_config(raw, *, restore=False):
    try:
        url = urlsplit((raw or "").replace("postgresql+psycopg://", "postgresql://", 1))
        database = unquote(url.path.removeprefix("/"))
        if (url.scheme not in {"postgresql", "postgres"} or not url.hostname
                or not database or "/" in database or url.query or url.fragment):
            raise ValueError
        if restore and not database.endswith("_test"):
            raise RecoveryError("Restore administrator must connect to a dedicated *_test database")
        return {"host": url.hostname, "port": url.port or 5432, "dbname": database,
                "user": unquote(url.username or ""), "password": unquote(url.password or ""),
                "connect_timeout": 5, "application_name": "sapartravel-recovery"}
    except (ValueError, TypeError):
        raise RecoveryError("Set an explicit PostgreSQL URL without query parameters") from None


def tool_environment(config, database=None):
    # Do not inherit libpq service/options/target parameters from the operator's shell.
    env = {key: value for key, value in os.environ.items() if not key.startswith("PG")}
    env.update(PGHOST=config["host"], PGPORT=str(config["port"]),
               PGDATABASE=database or config["dbname"], PGUSER=config["user"],
               PGPASSWORD=config["password"], PGCONNECT_TIMEOUT="5", PGAPPNAME="sapartravel-recovery")
    return env


def executable(name, bin_dir):
    path = str(bin_dir / name) if bin_dir else shutil.which(name)
    if not path or not Path(path).is_file():
        raise RecoveryError("Required PostgreSQL client executable is unavailable")
    return path


def digest_file(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")


def fingerprint(connection):
    """Hash every public table in one consistent snapshot, independent of row order."""
    connection.execute("SET TIME ZONE 'UTC'")
    names = [row[0] for row in connection.execute(
        "SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename")]
    if "alembic_version" not in names:
        raise RecoveryError("Source must contain a migrated application schema")
    tables = {}
    for name in names:
        digest = hashlib.sha256()
        count = 0
        query = sql.SQL('SELECT row_to_json(source)::text FROM {} AS source '
                        'ORDER BY row_to_json(source)::text COLLATE "C"').format(sql.Identifier("public", name))
        with connection.cursor(name="recovery_rows") as cursor:
            cursor.execute(query)
            for (row,) in cursor:
                # Row boundaries cannot be confused with text inside JSON strings.
                digest.update(row.encode("utf-8") + b"\n")
                count += 1
        tables[name] = {"rows": count, "sha256": digest.hexdigest()}
    revisions = [row[0] for row in connection.execute("SELECT version_num FROM alembic_version ORDER BY version_num")]
    return {"tables": tables, "alembic_revisions": revisions}


def run_tool(command, config, *, output=None, database=None):
    try:
        result = subprocess.run(command, env=tool_environment(config, database),
                                stdin=subprocess.DEVNULL, stdout=output or subprocess.PIPE,
                                stderr=subprocess.PIPE, timeout=900, check=False)
    except (OSError, subprocess.TimeoutExpired):
        raise RecoveryError("PostgreSQL client failed or exceeded the 15 minute tool deadline") from None
    if result.returncode:
        raise RecoveryError("PostgreSQL client failed; no archive or restoration is certified")


def create_backup(config, directory, bin_dir=None):
    directory.mkdir(parents=True, exist_ok=True)
    archive = directory / ("sapartravel-" + utc_now().strftime("%Y%m%dT%H%M%SZ")
                           + "-" + secrets.token_hex(4) + ".dump")
    # This lower bound precedes the exported MVCC snapshot and is conservative for RPO.
    snapshot_at = utc_now()
    with psycopg.connect(**config) as connection:
        connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        snapshot = connection.execute("SELECT pg_export_snapshot()").fetchone()[0]
        contents = fingerprint(connection)
        fd = os.open(archive, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as output:
            run_tool([executable("pg_dump", bin_dir), "--format=custom", "--no-password",
                      "--snapshot=" + snapshot], config, output=output)
    if not archive.stat().st_size:
        raise RecoveryError("Backup archive is empty")
    manifest = {"schema_version": 1, "kind": "sapartravel-backup", "archive": archive.name,
                "snapshot_lower_bound_utc": snapshot_at.isoformat(),
                "completed_at_utc": utc_now().isoformat(), "sha256": digest_file(archive),
                "bytes": archive.stat().st_size, "contents": contents,
                "snapshot_method": "pg_export_snapshot; pg_dump and fingerprints share one MVCC snapshot"}
    manifest_path = archive.with_suffix(".dump.json")
    write_json(manifest_path, manifest)
    return manifest_path


def verified_manifest(path):
    data = json.loads(path.read_text())
    if (data.get("schema_version") != 1 or data.get("kind") != "sapartravel-backup"
            or not isinstance(data.get("archive"), str) or Path(data["archive"]).name != data["archive"]
            or not isinstance(data.get("contents"), dict) or not data["contents"].get("tables")
            or not data["contents"].get("alembic_revisions")):
        raise RecoveryError("Invalid backup manifest")
    timestamp(data["snapshot_lower_bound_utc"])
    archive = path.parent / data["archive"]
    if archive.stat().st_size != data["bytes"] or digest_file(archive) != data["sha256"]:
        raise RecoveryError("Backup archive checksum or size does not match its manifest")
    return data, archive


def data_age(manifest, moment):
    age = (moment - timestamp(manifest["snapshot_lower_bound_utc"])).total_seconds()
    if age < 0:
        raise RecoveryError("Backup snapshot is later than the declared failure/check time")
    return age


def restore_drill(config, manifest_path, failure_at, bin_dir=None):
    manifest, archive = verified_manifest(manifest_path)
    loss = data_age(manifest, failure_at)
    started = time.monotonic()
    database = "sapar_recovery_" + secrets.token_hex(8) + "_test"
    # CREATE DATABASE refuses an existing name. There is deliberately no DROP or --clean.
    with psycopg.connect(**config, autocommit=True) as admin:
        admin.execute(sql.SQL("CREATE DATABASE {} TEMPLATE template0").format(sql.Identifier(database)))
    run_tool([executable("pg_restore", bin_dir), "--no-password", "--exit-on-error",
              "--no-owner", "--no-privileges", "--dbname=" + database, str(archive)], config,
             database=database)
    with psycopg.connect(**{**config, "dbname": database}) as restored:
        restored.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        contents = fingerprint(restored)
    elapsed = time.monotonic() - started
    matched = contents == manifest["contents"]
    return {"schema_version": 1, "kind": "sapartravel-restore-drill", "scope": "isolated-database",
            "failure_simulated_at_utc": failure_at.isoformat(), "finished_at_utc": utc_now().isoformat(),
            "restored_database": database, "archive_sha256": manifest["sha256"],
            "data_matches_snapshot": matched, "table_count": len(contents["tables"]),
            "row_count": sum(table["rows"] for table in contents["tables"].values()),
            "restored_data_point_lower_bound_utc": manifest["snapshot_lower_bound_utc"],
            "data_loss_upper_bound_seconds": loss, "rpo_target_seconds": 86400,
            "rpo_met": loss <= 86400, "restore_duration_seconds": round(elapsed, 3),
            "restore_within_15_minutes": elapsed <= 900,
            "sli_r_confirmed": False,
            "sli_r_limitation": "No API outage or five consecutive successful SLI-A minutes measured",
            "passed": matched and loss <= 86400 and elapsed <= 900}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pg-bin", type=Path, help="Directory containing matching PostgreSQL clients")
    commands = parser.add_subparsers(dest="command", required=True)
    backup = commands.add_parser("backup")
    backup.add_argument("--directory", type=Path, default=Path("backups"))
    restore = commands.add_parser("restore")
    restore.add_argument("--manifest", type=Path, required=True)
    restore.add_argument("--failure-at", help="Timezone-aware simulated failure; defaults to now")
    restore.add_argument("--output", type=Path, required=True)
    age = commands.add_parser("age")
    age.add_argument("--manifest", type=Path, required=True)
    age.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "backup":
            path = create_backup(connection_config(os.environ.get("BACKUP_DATABASE_URL")), args.directory, args.pg_bin)
            print(f"Verified snapshot metadata saved: {path}")
            return 0
        if args.command == "restore":
            config = connection_config(os.environ.get("RESTORE_ADMIN_DATABASE_URL"), restore=True)
            report = restore_drill(config, args.manifest,
                                   timestamp(args.failure_at) if args.failure_at else utc_now(), args.pg_bin)
        else:
            manifest, _ = verified_manifest(args.manifest)
            moment = utc_now()
            seconds = data_age(manifest, moment)
            report = {"kind": "sapartravel-backup-age", "checked_at_utc": moment.isoformat(),
                      "age_upper_bound_seconds": seconds, "fresh": seconds <= 86400,
                      "passed": seconds <= 86400, "restoration_verified": False}
        write_json(args.output, report)
        print("PASS" if report["passed"] else "FAIL")
        return 0 if report["passed"] else 1
    except (RecoveryError, OSError, ValueError, KeyError, TypeError, psycopg.Error) as error:
        print(str(error) if isinstance(error, RecoveryError) else
              "Recovery check failed; no result is certified. Connection and row details are suppressed.")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
