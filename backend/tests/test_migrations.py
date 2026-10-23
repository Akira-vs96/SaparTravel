"""Exercise real migration history with existing USD deals on PostgreSQL."""
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import os
from pathlib import Path
import subprocess
import sys
from uuid import uuid4

import pytest
from sqlalchemy import MetaData, create_engine, select, text

from app.db import engine


@pytest.mark.postgres
def test_migration_from_mvp_preserves_historical_deals_and_normalizes_catalog():
    if engine.dialect.name != "postgresql":
        pytest.skip("Migration transfer requires PostgreSQL")
    name = "sapar_migration_" + uuid4().hex + "_test"
    admin = create_engine(engine.url, isolation_level="AUTOCOMMIT")
    migrated = create_engine(engine.url.set(database=name))
    with admin.connect() as connection:
        connection.execute(text(f'CREATE DATABASE "{name}"'))
    env = {**os.environ, "DATABASE_URL": engine.url.set(database=name).render_as_string(hide_password=False)}
    backend = Path(__file__).resolve().parents[1]

    def alembic(*arguments):
        completed = subprocess.run([sys.executable, "-m", "alembic", *arguments], cwd=backend,
                                   env=env, capture_output=True, text=True, timeout=90)
        assert completed.returncode == 0, completed.stdout + completed.stderr

    try:
        alembic("upgrade", "0001")
        meta = MetaData()
        meta.reflect(bind=migrated)
        now = datetime.now(timezone.utc)
        start = date.today() + timedelta(days=30)
        with migrated.begin() as db:
            db.execute(meta.tables["users"].insert(), {"id": "legacy-user", "name": "Legacy traveler",
                       "email": "legacy@example.com", "password_hash": "unusable-old-fixture-hash", "role": "vendor",
                       "is_active": True, "created_at": now})
            destination = {"id": "legacy-destination", "slug": "legacy-almaty", "continent": "Asia", "image_url": "https://example.com/lake.jpg"}
            for suffix, title in (("", "Алматы"), ("_en", "Almaty"), ("_kk", "Алматы")):
                destination.update({"name"+suffix: title, "country"+suffix: "Kazakhstan", "description"+suffix: "Legacy destination description"})
            db.execute(meta.tables["destinations"].insert(), destination)
            tour = {"id": "legacy-tour", "slug": "legacy-lakes", "vendor_id": "legacy-user", "destination_id": "legacy-destination",
                    "category": "Nature", "duration_days": 2, "price_from": Decimal("249.90"), "currency": "USD", "rating": Decimal("4.8"),
                    "review_count": 47, "image_url": "https://example.com/lake.jpg", "is_published": True, "created_at": now}
            for suffix, title in (("", "Озёра Алматы"), ("_en", "Almaty lakes"), ("_kk", "Алматы көлдері")):
                tour.update({"title"+suffix: title, "description"+suffix: "A preserved legacy description",
                             "tags"+suffix: ["Lake"], "included"+suffix: ["Guide"], "excluded"+suffix: ["Flights"],
                             "itinerary"+suffix: [{"day": 1, "title": title, "description": "Meet at the lake"}]})
            db.execute(meta.tables["experiences"].insert(), tour)
            db.execute(meta.tables["departures"].insert(), {"id": "legacy-departure", "experience_id": "legacy-tour", "start_date": start,
                       "end_date": start+timedelta(days=1), "capacity": 12, "price": Decimal("275.55")})
            db.execute(meta.tables["favorites"].insert(), {"user_id": "legacy-user", "experience_id": "legacy-tour", "created_at": now})
            for status in ("pending", "confirmed", "cancelled", "completed"):
                db.execute(meta.tables["bookings"].insert(), {"id": status, "reference": "LEGACY-"+status, "user_id": "legacy-user",
                           "departure_id": "legacy-departure", "status": status, "travelers_count": 2,
                           "total_amount": Decimal("551.10"), "currency": "USD", "contact_name": "Old Name",
                           "contact_email": "legacy@example.com", "notes": "Preserve this note", "experience_snapshot": {"ru": {"title": "Agreed title"}},
                           "start_date": start, "end_date": start+timedelta(days=1), "created_at": now})
                db.execute(meta.tables["booking_status_history"].insert(), {"id": "history-"+status, "booking_id": status,
                           "actor_id": "legacy-user", "status": status, "created_at": now})
        alembic("upgrade", "head")
        alembic("check")
        current = MetaData()
        current.reflect(bind=migrated)
        with migrated.connect() as db:
            bookings = db.execute(select(current.tables["bookings"])).mappings().all()
            assert len(bookings) == 4
            assert {row["status"] for row in bookings} == {"pending", "confirmed", "cancelled", "completed"}
            assert all(row["currency"] == "USD" and row["total_amount"] == Decimal("551.10") for row in bookings)
            assert all(row["experience_snapshot"]["ru"]["title"] == "Agreed title" for row in bookings)
            assert db.scalar(text("SELECT count(*) FROM payment_attempts")) == 0
            assert db.scalar(text("SELECT count(*) FROM booking_status_history")) == 4
            assert db.scalar(text("SELECT count(*) FROM favorites")) == 1
            assert db.scalar(text("SELECT count(*) FROM currency_conversion_records WHERE booking_id IS NOT NULL")) == 4
            assert db.scalar(text("SELECT price_from FROM experiences")) == Decimal("124950.00")
            assert db.scalar(text("SELECT price FROM departures")) == Decimal("137775.00")
            assert db.scalar(text("SELECT currency FROM experiences")) == "KZT"
            assert db.scalar(text("SELECT title FROM experience_translations WHERE language = 'en'")) == "Almaty lakes"
            assert db.scalar(text("SELECT count(*) FROM itinerary_translations")) == 3
            assert db.scalar(text("SELECT count(*) FROM catalog_lines")) == 9
            assert db.scalar(text("SELECT review_count FROM experiences")) == 0
            assert "itinerary" not in current.tables["experiences"].c
    finally:
        migrated.dispose()
        with admin.connect() as connection:
            connection.execute(text(f'DROP DATABASE "{name}"'))
        admin.dispose()
