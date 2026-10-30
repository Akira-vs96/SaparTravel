"""Prepare exactly 500 tours in an empty, explicitly selected PostgreSQL *_test DB.

The database must already exist. No application's DATABASE_URL or .env is used.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import tempfile

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url

ROOT = Path(__file__).resolve().parents[1]
TOUR_COUNT = 500


def test_database_url(raw: str | None) -> str:
    """Validate before importing any application module or opening a connection."""
    if not raw:
        raise ValueError("Set CATALOG_LOAD_DATABASE_URL explicitly; DATABASE_URL is never a fallback")
    try:
        url = make_url(raw)
    except Exception:
        raise ValueError("Invalid CATALOG_LOAD_DATABASE_URL") from None
    if url.drivername in {"postgres", "postgresql"}:
        url = url.set(drivername="postgresql+psycopg")
    if url.drivername != "postgresql+psycopg" or not (url.database or "").endswith("_test"):
        raise ValueError("Catalog load preparation requires PostgreSQL with a database name ending in _test")
    # libpq options could redirect the connection to a different database/service.
    if url.query:
        raise ValueError("Connection URL query parameters are not supported for this destructive-test guard")
    return url.render_as_string(hide_password=False)


def build_payload(source: dict) -> dict:
    result = {"destinations": deepcopy(source["destinations"]), "experiences": []}
    templates = source["experiences"]
    if not templates:
        raise ValueError("Seed catalog has no tour templates")
    for index in range(TOUR_COUNT):
        tour = deepcopy(templates[index % len(templates)])
        tour["slug"] = f"catalog-load-{index:04d}"
        for suffix in ("", "_en", "_kk"):
            tour["title" + suffix] = f"{tour.get('title' + suffix, tour['title'])} [SLI-L {index:04d}]"
        tour["is_published"] = True
        tour["publication_status"] = "published"
        tour["review_count"] = 0
        # Fixed relative dates; the UTC preparation timestamp is recorded in the manifest.
        tour["departures"] = [
            {"days_from_today": offset, "capacity": 20, "price": tour["price_from"]}
            for offset in (14, 35, 63)
        ]
        result["experiences"].append(tour)
    return result


def assert_empty_database(url: str) -> None:
    engine = create_engine(url)
    try:
        with engine.connect() as connection:
            # Never clean or overwrite an existing catalog, even in a *_test database.
            for name in inspect(connection).get_table_names():
                if name == "alembic_version":
                    continue
                quoted = engine.dialect.identifier_preparer.quote(name)
                if connection.scalar(text(f"SELECT EXISTS (SELECT 1 FROM {quoted} LIMIT 1)")):
                    raise ValueError("Selected test database is not empty; create a new dedicated *_test database")
    finally:
        engine.dispose()


def prepare_worker(manifest_path: Path) -> None:
    url = test_database_url(os.environ.get("CATALOG_LOAD_DATABASE_URL"))
    assert_empty_database(url)
    completed = subprocess.run(
        [sys.executable, "-m", "alembic", "-c", str(ROOT / "backend/alembic.ini"), "upgrade", "head"],
        capture_output=True, text=True, check=False,
    )
    if completed.returncode:
        # Do not forward DB connection errors or configuration values containing credentials.
        raise RuntimeError("Migration failed; inspect the dedicated test database and migration configuration")
    from sqlalchemy import func, select
    from app.db import SessionLocal, engine
    from app.domain.models import Experience
    from app.seed import seed_data

    payload = build_payload(json.loads((ROOT / "backend/app/seed_data.json").read_text(encoding="utf-8")))
    try:
        with SessionLocal.begin() as session:
            seed_data(session, payload)
            session.flush()
            count = session.scalar(select(func.count()).select_from(Experience))
            if count != TOUR_COUNT:
                raise RuntimeError("Prepared catalog does not contain exactly 500 tours")
        manifest = {
            "schema_version": 1, "scenario": "SLI-L", "tours": TOUR_COUNT,
            "prepared_at_utc": datetime.now(timezone.utc).isoformat(),
            "database_name": make_url(url).database,
            "fixture_sha256": hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest(),
            "slug_prefix": "catalog-load-", "departures_per_tour": 3,
        }
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    finally:
        engine.dispose()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=Path("test-results/catalog-load-fixture.json"))
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    try:
        url = test_database_url(os.environ.get("CATALOG_LOAD_DATABASE_URL"))
        if args.worker:
            prepare_worker(args.manifest)
            return 0
        manifest = args.manifest.resolve()
        env = {
            **os.environ, "CATALOG_LOAD_DATABASE_URL": url, "DATABASE_URL": url,
            "ENVIRONMENT": "testing", "JWT_SECRET": secrets.token_urlsafe(48),
            "ADMIN_EMAIL": "", "ADMIN_PASSWORD": "", "SEED_DEMO_DATA": "false",
            "AUTH_RATE_LIMIT": "20", "PAYMENT_DEMO_ENABLED": "false",
            "DEMO_MAILBOX_ENABLED": "false", "DEMO_PRIVATE_DATA": "false",
            "PYTHONPATH": str(ROOT / "backend"),
        }
        # Settings.env_file is relative to cwd: isolation prevents reading the working .env.
        with tempfile.TemporaryDirectory(prefix="sapar-catalog-load-") as directory:
            result = subprocess.run(
                [sys.executable, str(Path(__file__).resolve()), "--worker", "--manifest", str(manifest)],
                cwd=directory, env=env, check=False,
            )
        if result.returncode:
            return result.returncode
        print(f"Prepared {TOUR_COUNT} test tours; manifest: {manifest}")
        return 0
    except Exception as error:
        # Database/library errors can contain the full DSN; expose only explicit safe messages.
        message = str(error) if isinstance(error, (ValueError, RuntimeError)) else type(error).__name__
        print(f"Catalog preparation failed: {message}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
