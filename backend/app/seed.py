"""Idempotent initial catalog and explicitly configured administrator.

Run after `alembic upgrade head`. Existing catalog rows and credentials are never overwritten.
"""
from datetime import date, timedelta
import json
from pathlib import Path
import secrets

from sqlalchemy import select, text

from app.core.config import get_settings
from app.core.security import password_hash
from app.db import SessionLocal
from app.domain.models import Departure, Destination, Experience, User


DESTINATION_FIELDS = {column.name for column in Destination.__table__.columns} - {"id"}
EXPERIENCE_FIELDS = {column.name for column in Experience.__table__.columns} - {
    "id", "vendor_id", "destination_id", "created_at",
}


def seed_data(db, payload: dict) -> None:
    owner = db.scalar(select(User).where(User.email == "catalog@sapartravel.invalid"))
    if owner is None:
        owner = User(name="SaparTravel Demo", email="catalog@sapartravel.invalid", role="vendor", is_active=False,
                     password_hash=password_hash.hash(secrets.token_urlsafe(64)))
        db.add(owner)
        db.flush()
    elif owner.is_active:
        raise RuntimeError("The reserved demo catalog account must be inactive")

    for row in payload["destinations"]:
        if not db.scalar(select(Destination.id).where(Destination.slug == row["slug"])):
            db.add(Destination(**{key: value for key, value in row.items() if key in DESTINATION_FIELDS}))
    db.flush()
    destinations = {item.slug: item.id for item in db.scalars(select(Destination))}
    for row in payload["experiences"]:
        # Do not regenerate departures or reset edited titles/statuses on restart.
        if db.scalar(select(Experience.id).where(Experience.slug == row["slug"])):
            continue
        item = Experience(
            **{key: value for key, value in row.items() if key in EXPERIENCE_FIELDS},
            destination_id=destinations[row["destination_slug"]], vendor_id=owner.id,
        )
        db.add(item)
        db.flush()
        for departure in row.get("departures", [
            {"days_from_today": 14, "capacity": 12, "price": row["price_from"]},
            {"days_from_today": 35, "capacity": 12, "price": row["price_from"]},
            {"days_from_today": 63, "capacity": 16, "price": row["price_from"]},
        ]):
            start = date.today() + timedelta(days=departure["days_from_today"])
            db.add(Departure(experience_id=item.id, start_date=start,
                             end_date=start + timedelta(days=item.duration_days - 1),
                             capacity=departure["capacity"], price=departure["price"]))


def main() -> None:
    settings = get_settings()
    with SessionLocal.begin() as db:
        # Two starting workers cannot seed duplicates. The lock is transaction scoped.
        if db.bind.dialect.name == "postgresql":
            db.execute(text("SELECT pg_advisory_xact_lock(7240019401)"))
        if settings.admin_email:
            email = str(settings.admin_email).casefold()
            admin = db.scalar(select(User).where(User.email == email))
            if admin is None:
                db.add(User(name="SaparTravel Admin", email=email, role="admin",
                            password_hash=password_hash.hash(settings.admin_password.get_secret_value())))
                db.flush()
            elif admin.role != "admin" or not admin.is_active:
                raise RuntimeError("ADMIN_EMAIL already belongs to a non-administrator; choose another email")
        if settings.seed_demo_data:
            payload = json.loads(Path(__file__).with_name("seed_data.json").read_text(encoding="utf-8"))
            seed_data(db, payload)
    print("Initial data ready; existing records preserved.")


if __name__ == "__main__":
    main()
