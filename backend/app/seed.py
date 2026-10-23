"""Idempotent initial catalog and explicitly configured administrator.

Run after `alembic upgrade head`. Existing catalog rows and credentials are never overwritten.
"""
from datetime import date, timedelta
import argparse
import json
from pathlib import Path
import secrets

from sqlalchemy import select, text

from app.core.config import get_settings
from app.core.clock import business_today
from app.core.security import password_hash
from app.db import SessionLocal
from app.domain.models import CategoryRecord, Departure, Destination, Experience, ExperienceImage, ExperienceService, User
from app.api.schemas import DestinationInput, ExperienceInput


DESTINATION_FIELDS = set(DestinationInput.model_fields)
EXPERIENCE_FIELDS = (set(ExperienceInput.model_fields) | {"slug", "currency"}) - {"destination_id"}


def seed_data(db, payload: dict) -> None:
    for code, ru, en, kk in (
        ("Nature", "Природа", "Nature", "Табиғат"),
        ("Culture", "Культура", "Culture", "Мәдениет"),
        ("Adventure", "Приключения", "Adventure", "Шытырман"),
        ("Food", "Гастрономия", "Food", "Гастрономия"),
        ("Beach", "Пляж", "Beach", "Жағажай"),
        ("City", "Город", "City", "Қала"),
    ):
        if not db.get(CategoryRecord, code):
            db.add(CategoryRecord(code=code, name_ru=ru, name_en=en, name_kk=kk))
    db.flush()
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
        db.add(ExperienceImage(experience_id=item.id, position=0, url=item.image_url, alt=item.title))
        db.add(ExperienceService(experience_id=item.id, name="Индивидуальный трансфер",
                                 name_en="Private transfer", name_kk="Жеке трансфер",
                                 price=15000, currency="KZT", per_person=False))
        db.add(ExperienceService(experience_id=item.id, name="Обед в пути",
                                 name_en="Lunch on the route", name_kk="Жолдағы түскі ас",
                                 price=5000, currency="KZT", per_person=True))
        for departure in row.get("departures", [
            {"days_from_today": 14, "capacity": 12, "price": row["price_from"]},
            {"days_from_today": 35, "capacity": 12, "price": row["price_from"]},
            {"days_from_today": 63, "capacity": 16, "price": row["price_from"]},
        ]):
            start = business_today() + timedelta(days=departure["days_from_today"])
            db.add(Departure(experience_id=item.id, start_date=start,
                             end_date=start + timedelta(days=item.duration_days - 1),
                             capacity=departure["capacity"], price=departure["price"]))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--extend-departures", action="store_true", help="Add missing future dates; preserve all existing departure dates and bookings")
    args = parser.parse_args()
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
        if args.extend_departures:
            extend_departures(db)
    print("Initial data ready; existing records preserved.")


def extend_departures(db) -> None:
    """Explicitly replenish future availability without moving existing dates."""
    for tour in db.scalars(select(Experience).where(Experience.is_published.is_(True))):
        for offset in (14, 35, 63):
            start = business_today() + timedelta(days=offset)
            exists = db.scalar(select(Departure.id).where(Departure.experience_id == tour.id, Departure.start_date == start))
            if not exists:
                db.add(Departure(experience_id=tour.id, start_date=start,
                                 end_date=start + timedelta(days=tour.duration_days - 1),
                                 capacity=12, price=tour.price_from))


if __name__ == "__main__":
    main()
