"""Render user systemd schedules, and optionally enable them with an existing private environment."""
import argparse
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
SCHEDULES = {"probe": "*-*-* *:*:00", "backup": "*-*-* 00,06,12,18:05:00", "age": "hourly", "restore": "*-*-01 04:00:00", "report": "*-*-01 06:00:00"}


def quoted(path):
    value = str(path.resolve())
    if "\n" in value or "\r" in value:
        raise ValueError("Paths must not contain line breaks")
    return '"' + value.replace("%", "%%").replace("\\", "\\\\").replace('"', '\\"') + '"'


def render(destination, environment, *, python=None):
    destination.mkdir(parents=True, exist_ok=True)
    python = python or Path(sys.executable)
    paths = []
    for job, schedule in SCHEDULES.items():
        service = destination / f"sapartravel-{job}.service"
        service.write_text(f"""[Unit]
Description=SaparTravel {job} with explicit operator configuration
StartLimitIntervalSec=0

[Service]
Type=oneshot
WorkingDirectory={quoted(ROOT)[1:-1]}
EnvironmentFile={quoted(environment)[1:-1]}
ExecStart={quoted(python)} -m scripts.ops_jobs {job}
UMask=0077
NoNewPrivileges=true
TimeoutStartSec={"20" if job == "probe" else "1800"}
""")
        timer = destination / f"sapartravel-{job}.timer"
        timer.write_text(f"""[Unit]
Description=Schedule SaparTravel {job}

[Timer]
OnCalendar={schedule}
AccuracySec={"1s" if job == "probe" else "1min"}
Persistent={"false" if job == "probe" else "true"}
Unit=sapartravel-{job}.service

[Install]
WantedBy=timers.target
""")
        paths.extend((service, timer))
    return paths


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--environment-file", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path.home() / ".config/systemd/user")
    parser.add_argument("--enable", choices=tuple(SCHEDULES), nargs="+", default=[])
    args = parser.parse_args()
    if args.enable:
        if not args.environment_file.is_file() or args.environment_file.stat().st_mode & 0o077:
            parser.error("Enabling timers requires an existing private 0600 environment file")
        if args.output.resolve() != (Path.home() / ".config/systemd/user").resolve():
            parser.error("Enable timers only in the user systemd unit directory")
    paths = render(args.output, args.environment_file)
    print(f"Rendered {len(paths)} units; no credentials are copied into unit files")
    if args.enable:
        subprocess.run(["systemctl", "--user", "daemon-reload"], check=True)
        subprocess.run(["systemctl", "--user", "enable", "--now", *[f"sapartravel-{job}.timer" for job in args.enable]], check=True)


if __name__ == "__main__":
    main()
