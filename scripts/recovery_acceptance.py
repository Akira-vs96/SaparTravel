"""Controlled local API outage, real database restoration and five real probe minutes.

Only a dedicated PostgreSQL *_test database is accepted. Only API/web processes
started by this command are stopped. Existing databases are never overwritten.
"""
from datetime import datetime, timezone
import argparse
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import sys
import tempfile
import time
from urllib.request import urlopen

from scripts.availability_probe import Config, run_probe
from scripts.database_recovery import connection_config, create_backup, restore_drill
from scripts.prepare_catalog_load import test_database_url
from scripts.recovery_report import recovery_report

ROOT = Path(__file__).resolve().parents[1]


def terminate(process):
    if process is None:
        return
    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def wait_ready(url, process):
    for _ in range(100):
        if process.poll() is not None:
            raise RuntimeError("Acceptance child process exited before becoming ready")
        try:
            with urlopen(url, timeout=1) as response:
                if response.status == 200:
                    return
        except OSError:
            pass
        time.sleep(.1)
    raise RuntimeError("Acceptance child process did not become ready")


def execute(*, database_url, output, probe_output, pg_bin, api_port=18011, web_port=18012, interval=60):
    url = test_database_url(database_url)
    if api_port == web_port or not all(1024 <= port <= 65535 for port in (api_port, web_port)):
        raise ValueError("Use two distinct non-privileged local ports")
    # Provisioning belongs to this explicitly selected test DB, never the working .env.
    py = sys.executable
    origin = f"http://127.0.0.1:{web_port}"
    env = {**os.environ, "DATABASE_URL": url, "ENVIRONMENT": "testing", "JWT_SECRET": secrets.token_urlsafe(48),
           "ADMIN_EMAIL": "", "ADMIN_PASSWORD": "", "AUTH_RATE_LIMIT": "20", "SEED_DEMO_DATA": "true",
           "PAYMENT_DEMO_ENABLED": "false", "DEMO_PRIVATE_DATA": "false", "DEMO_MAILBOX_ENABLED": "false",
           "SUPPORT_CALENDAR_FILE": "", "PUBLIC_WEB_URL": origin, "PYTHONPATH": str(ROOT / "backend"),
           "API_PROXY_TARGET": f"http://127.0.0.1:{api_port}", "LOG_LEVEL": "WARNING"}
    processes = []
    api = None
    with tempfile.TemporaryDirectory(prefix="sapar-recovery-") as directory:
        scratch = Path(directory)
        for args in (("-m", "alembic", "-c", str(ROOT / "backend/alembic.ini"), "upgrade", "head"), ("-m", "app.seed")):
            result = subprocess.run([py, *args], env=env, cwd=scratch, capture_output=True, timeout=120)
            if result.returncode:
                raise RuntimeError("Acceptance schema or seed preparation failed")
        points = ["local-a", "local-b", "local-c"]
        deployment = "recovery-" + secrets.token_hex(6)
        subprocess.run([py, "-m", "app.monitoring", "--deployment-id", deployment, "--origin", origin,
                        "--directory", str(scratch / "monitoring"), "--points", *points],
                       cwd=scratch, env=env, check=True, stdout=subprocess.DEVNULL, timeout=90)
        configs = [Config(**json.loads((scratch / "monitoring" / (point + ".json")).read_text())) for point in points]
        credentials = [dict(line.split("=", 1) for line in (scratch / "monitoring" / (point + ".env")).read_text().splitlines()) for point in points]
        webroot = scratch / "web"
        shutil.copytree(ROOT / "frontend/dist", webroot)
        (webroot / ".well-known").mkdir(exist_ok=True)
        shutil.copyfile(scratch / "monitoring/sapartravel-monitoring.json", webroot / ".well-known/sapartravel-monitoring.json")
        log = (scratch / "process.log").open("w")

        def start_api(database):
            current_env = {**env, "DATABASE_URL": database}
            process = subprocess.Popen([py, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(api_port), "--no-access-log"],
                                       cwd=scratch, env=current_env, stdout=log, stderr=subprocess.STDOUT)
            processes.append(process)
            wait_ready(f"http://127.0.0.1:{api_port}/api/v1/health", process)
            return process

        def observe():
            return [run_probe(config, account["SLI_EMAIL"], account["SLI_PASSWORD"])
                    for config, account in zip(configs, credentials)]

        try:
            api = start_api(url)
            web = subprocess.Popen([shutil.which("node"), str(ROOT / "frontend/node_modules/vite/bin/vite.js"), "preview",
                                    "--host", "127.0.0.1", "--port", str(web_port), "--strictPort", "--outDir", str(webroot)],
                                   cwd=ROOT / "frontend", env=env, stdout=log, stderr=subprocess.STDOUT)
            processes.append(web)
            wait_ready(origin, web)
            baseline = observe()
            if not all(row["success"] for row in baseline):
                raise RuntimeError("The complete baseline user scenario did not pass from all local points")
            config = connection_config(url)
            manifest = create_backup(config, scratch / "backups", pg_bin)
            failure_at = datetime.now(timezone.utc)
            terminate(api)
            api = None
            outage = observe()
            if any(row["success"] for row in outage):
                raise RuntimeError("Controlled API outage was not observed")
            first_reaction = datetime.now(timezone.utc)
            restored = restore_drill(config, manifest, failure_at, pg_bin)
            if not restored["passed"]:
                raise RuntimeError("Restored database did not match the backup or meet RPO")
            from sqlalchemy.engine import make_url
            restored_url = make_url(url).set(database=restored["restored_database"]).render_as_string(hide_password=False)
            api = start_api(restored_url)
            records = []
            if interval == 60:
                target = (int(time.time()) // 60 + 1) * 60
            else:
                target = time.time()
            for index in range(5):
                while time.time() < target:
                    time.sleep(min(1, target - time.time()))
                batch = observe()
                records.extend(batch)
                print(f"Recovery observation {index + 1}/5: {sum(row['success'] for row in batch)}/3 points", flush=True)
                target += interval
            rto = recovery_report(records, failure_at=failure_at, deployment_id=deployment, points=points)
            acceptance_profile = interval == 60
            report = {"schema_version": 1, "kind": "sapartravel-api-recovery", "scope": "local-acceptance",
                      "deployment_id": deployment, "points": points, "independent_points": False,
                      "acceptance_profile": acceptance_profile, "api_outage_observed": True,
                      "first_reaction_at_utc": first_reaction.isoformat(), "database": restored,
                      **rto, "accepted": acceptance_profile and restored["passed"] and rto["sli_r_confirmed"] and rto["rto_met"],
                      "limitation": "Three local clients share one host; this is not evidence of independent external monitoring"}
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
            probe_output.parent.mkdir(parents=True, exist_ok=True)
            probe_output.write_text("".join(json.dumps(row, allow_nan=False) + "\n" for row in outage + records))
            return report
        finally:
            terminate(api)
            for process in processes:
                terminate(process)
            log.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--probe-output", type=Path, required=True)
    parser.add_argument("--pg-bin", type=Path, default=Path("/usr/lib/postgresql/17/bin"))
    parser.add_argument("--api-port", type=int, default=18011)
    parser.add_argument("--web-port", type=int, default=18012)
    parser.add_argument("--interval", type=int, choices=(1, 60), default=60, help="1 is smoke only and never confirms SLI-R")
    args = parser.parse_args()
    try:
        report = execute(database_url=os.environ.get("RECOVERY_DATABASE_URL"), output=args.output,
                         probe_output=args.probe_output, pg_bin=args.pg_bin, api_port=args.api_port,
                         web_port=args.web_port, interval=args.interval)
        print("ACCEPTED" if report["accepted"] else "NOT ACCEPTED")
        return 0 if report["accepted"] else 1
    except Exception:
        print("Recovery acceptance failed; no result is certified; credentials and application output are suppressed")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
