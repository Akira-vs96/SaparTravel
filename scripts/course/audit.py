"""Validate course evidence structure separately from completion of human coursework."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import unicodedata
from xml.etree import ElementTree
from zipfile import BadZipFile, ZipFile

ROOT = Path(__file__).resolve().parents[2]
STATUSES = {"verified", "documented", "partial", "requires-human", "blocked"}


def source_paragraphs(source):
    """One-based nonempty OOXML paragraphs, including table text and tracked edits."""
    with ZipFile(source) as archive:
        document = ElementTree.fromstring(archive.read("word/document.xml"))
    values = ["".join(row.itertext()).strip() for row in document.findall(".//{http://schemas.openxmlformats.org/wordprocessingml/2006/main}p")]
    return [row for row in values if row]


def _normalise(value):
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", value))


def audit(manifest, root=ROOT):
    errors, pending = [], []
    statuses = Counter()
    labs = manifest.get("labs", [])
    if [r.get("number") for r in labs] != list(range(1, 16)):
        errors.append("The manifest must contain each lab 1 through 15 exactly once")
    source = root / manifest["source"]["path"]
    if not source.is_file() or hashlib.sha256(source.read_bytes()).hexdigest() != manifest["source"]["sha256"]:
        errors.append("The methodology source is missing or changed")
    paragraphs = None
    if any("source_paragraph" in row for lab in labs for row in lab.get("steps", [])):
        try:
            paragraphs = source_paragraphs(source)
        except (OSError, BadZipFile, KeyError, ElementTree.ParseError):
            errors.append("Cannot read methodology OOXML paragraphs")
    ids = set()
    for lab in labs + [{"number": "administration", "steps": manifest.get("administration", [])}]:
        if lab["number"] == "administration" and not lab["steps"]:
            continue
        if not lab.get("steps"):
            errors.append(f"Lab {lab['number']} has no methodology steps")
        if lab["number"] != "administration" and not (root / lab["report"]).is_file():
            errors.append(f"Lab {lab['number']} report is missing")
        for entry in lab.get("artifacts", []):
            if not isinstance(entry, dict) or not isinstance(entry.get("path"), str):
                errors.append(f"Invalid artifact entry in lab {lab['number']}")
                continue
            path = root / entry["path"]
            if not path.resolve().is_relative_to(root.resolve()) or not path.exists():
                errors.append(f"Missing or unsafe lab artifact: {entry['path']}")
        for row in lab["steps"]:
            if "source_paragraph" in row and paragraphs is not None:
                position = row["source_paragraph"]
                if type(position) is not int or not 1 <= position <= len(paragraphs) or _normalise(row["text"]) not in _normalise(paragraphs[position - 1]):
                    errors.append(f"Requirement does not match its original methodology paragraph: {row['id']}")
            if row["id"] in ids or row.get("status") not in STATUSES:
                errors.append(f"Invalid or duplicate requirement {row['id']}")
            ids.add(row["id"])
            statuses[row["status"]] += 1
            for name in row.get("evidence", []):
                path = root / name
                if not path.resolve().is_relative_to(root.resolve()) or not path.exists():
                    errors.append(f"Missing or unsafe evidence path: {row['id']} / {name}")
            if row["status"] == "verified" and not row.get("evidence"):
                errors.append(f"Verified requirement has no evidence: {row['id']}")
            if row.get("requires_people") and row["status"] == "verified" and not row.get("human_confirmation"):
                errors.append(f"Human event cannot be certified by generated code: {row['id']}")
            if row.get("requires_people") and row["status"] == "documented" and not row.get("human_confirmation"):
                pending.append({"id": row["id"], "status": "requires-human", "reason": "A prepared document does not certify this human event"})
            if row["status"] not in {"verified", "documented"}:
                pending.append({"id": row["id"], "status": row["status"], "reason": row["note"]})
    return {"generated_at_utc": datetime.now(timezone.utc).isoformat(), "structure_valid": not errors,
            "course_complete": not errors and not pending,
            "labs": len(labs), "requirements": len(ids), "status_counts": dict(statuses),
            "errors": errors, "pending_requirements": pending,
            "meaning": "A valid evidence package does not imply customer acceptance or completed human exercises"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=ROOT / "docs/labs/manifest.json")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--require-complete", action="store_true")
    args = parser.parse_args()
    result = audit(json.loads(args.manifest.read_text()))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({k: result[k] for k in ("structure_valid", "course_complete", "labs", "requirements", "status_counts")}, ensure_ascii=False))
    raise SystemExit(0 if result["structure_valid"] and (not args.require_complete or result["course_complete"]) else 1)


if __name__ == "__main__":
    main()
