"""Run real scanners against Git history and the files eligible for version control."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile
from urllib.request import urlopen, urlretrieve

ROOT = Path(__file__).resolve().parents[2]
VERSIONS = {"gitleaks": "8.30.1", "trivy": "0.76.1"}


def install(name, directory):
    version = VERSIONS[name]
    repository = "gitleaks/gitleaks" if name == "gitleaks" else "aquasecurity/trivy"
    filename = f"gitleaks_{version}_linux_x64.tar.gz" if name == "gitleaks" else f"trivy_{version}_Linux-64bit.tar.gz"
    prefix = f"https://github.com/{repository}/releases/download/v{version}/"
    target = directory / filename
    urlretrieve(prefix + filename, target)
    checksum_name = f"{name}_{version}_checksums.txt"
    with urlopen(prefix + checksum_name, timeout=30) as response:
        checksums = response.read().decode()
    expected = next(line.split()[0] for line in checksums.splitlines() if line.split()[-1] == filename)
    if hashlib.sha256(target.read_bytes()).hexdigest() != expected:
        raise ValueError("Scanner checksum mismatch")
    with tarfile.open(target) as archive:
        member = next(m for m in archive.getmembers() if m.name == name)
        (directory / name).write_bytes(archive.extractfile(member).read())
    (directory / name).chmod(0o755)
    return directory / name


def public_export(directory):
    result = subprocess.run(["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
                            cwd=ROOT, check=True, capture_output=True)
    for name in set(os.fsdecode(result.stdout).split("\0")) - {""}:
        source = ROOT / name
        if source.is_file() and source.resolve().is_relative_to(ROOT) and not source.is_symlink():
            target = directory / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)


def run(output, binaries=None):
    output.mkdir(parents=True, exist_ok=True)
    summary = {"captured_at_utc": datetime.now(timezone.utc).isoformat(), "versions": VERSIONS,
               "scope": "Git history and tracked/nonignored working files; private ignored environments are not exported",
               "checks": []}
    with tempfile.TemporaryDirectory(prefix="sapar-security-") as scratch:
        scratch = Path(scratch)
        executables = {name: Path(binaries) / name if binaries else install(name, scratch) for name in VERSIONS}
        export = scratch / "public"
        export.mkdir()
        public_export(export)
        commands = {
            "git-secrets": [str(executables["gitleaks"]), "git", "--redact", "--no-banner",
                            "--gitleaks-ignore-path", str(ROOT / ".gitleaksignore"),
                            "--report-format", "json", "--report-path", str(output / "git-secrets.json"), str(ROOT)],
            "working-files-secrets": [str(executables["gitleaks"]), "dir", "--redact", "--no-banner",
                                      "--report-format", "json", "--report-path", str(output / "working-files-secrets.json"), str(export)],
            "dependencies": [str(executables["trivy"]), "fs", "--quiet", "--scanners", "vuln",
                             "--severity", "HIGH,CRITICAL", "--format", "json", "--exit-code", "1",
                             "--output", str(output / "dependencies.json"), str(export)],
        }
        for name, command in commands.items():
            result = subprocess.run(command, cwd=ROOT, capture_output=True, timeout=420)
            # Neither scanner output nor matched secrets enter the console or summary.
            summary["checks"].append({"name": name, "exit_code": result.returncode})
        # Normalize ephemeral paths in public vulnerability evidence.
        report = output / "dependencies.json"
        if report.exists():
            content = report.read_text().replace(str(export), "public-working-tree")
            report.write_text(content)
    summary["passed"] = all(row["exit_code"] == 0 for row in summary["checks"])
    (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-directory", type=Path, required=True)
    parser.add_argument("--binaries-directory", type=Path)
    args = parser.parse_args()
    try:
        summary = run(args.output_directory.resolve(), args.binaries_directory)
        print(json.dumps(summary))
        raise SystemExit(0 if summary["passed"] else 1)
    except (OSError, ValueError, StopIteration, subprocess.SubprocessError):
        raise SystemExit("Scanner execution failed; no clean result is certified") from None


if __name__ == "__main__":
    main()
