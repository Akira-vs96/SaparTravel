"""Create private demonstration accounts without shared or public passwords.

Explicit command, never run during application startup. Credentials are written
once to a user-only local file. Repeating the command preserves passwords and
user edits. The reserved catalog account always remains inactive.
"""
import argparse
import json
import os
from pathlib import Path
import secrets

from sqlalchemy import select, text

from app.core.config import get_settings
from app.core.security import password_hash
from app.db import SessionLocal
from app.domain.models import Experience, ExperienceService, User
from app.seed import seed_data


ACCOUNTS = (
    ("demo-admin@example.com", "SaparTravel Demo Admin", "admin"),
    ("mountain-team@example.com", "Sapar Mountain Team", "vendor"),
    ("world-team@example.com", "Sapar World Routes", "vendor"),
    ("demo-traveler@example.com", "Айдана Саяхатшы", "traveler"),
)


def prepare_accounts(db):
    credentials = []
    accounts = {}
    for email, name, role in ACCOUNTS:
        user = db.scalar(select(User).where(User.email == email))
        if user is None:
            password = secrets.token_urlsafe(24)
            user = User(email=email, name=name, role=role, is_active=True,
                        password_hash=password_hash.hash(password))
            db.add(user)
            db.flush()
            credentials.append({"email": email, "password": password, "role": role})
        elif user.role != role or not user.is_active:
            raise RuntimeError(f"Reserved demonstration email already exists with changed permissions: {email}; no changes applied")
        accounts[email] = user
    vendor_ids = [accounts[email].id for email, _, role in ACCOUNTS if role == "vendor"]
    reserved = db.scalar(select(User).where(User.email == "catalog@sapartravel.invalid"))
    if reserved:
        if reserved.is_active:
            raise RuntimeError("Reserved catalog account must remain inactive")
        tours = db.scalars(select(Experience).where(Experience.vendor_id == reserved.id).order_by(Experience.slug)).all()
        for index, tour in enumerate(tours):
            # Enrich only the service-owned catalog being handed over this once.
            # Repeating the command does not recreate options a vendor removed.
            if not tour.services:
                db.add(ExperienceService(experience_id=tour.id, name="Индивидуальный трансфер",
                                         name_en="Private transfer", name_kk="Жеке трансфер",
                                         price=15000, currency="KZT", per_person=False))
                db.add(ExperienceService(experience_id=tour.id, name="Обед в пути",
                                         name_en="Lunch on the route", name_kk="Жолдағы түскі ас",
                                         price=5000, currency="KZT", per_person=True))
            tour.vendor_id = vendor_ids[index % len(vendor_ids)]
    return credentials, accounts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--credentials-file", type=Path, default=Path(".env.demo-credentials.json"))
    args = parser.parse_args()
    settings = get_settings()
    if not settings.demo_private_data or settings.environment not in {"development", "testing"}:
        parser.error("Set DEMO_PRIVATE_DATA=true in a local development/testing environment")
    destination = args.credentials_file.resolve()
    if not destination.parent.is_dir():
        parser.error("Credentials file parent directory must already exist")
    # A pre-existing file is never overwritten, including a symlink.
    descriptor = None
    try:
        descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        if destination.is_symlink() or not destination.is_file() or destination.stat().st_mode & 0o077:
            parser.error("Existing credentials file must be a regular, private (0600) file")
    try:
        with SessionLocal.begin() as db:
            if db.bind.dialect.name == "postgresql":
                db.execute(text("SELECT pg_advisory_xact_lock(7240019401)"))
            seed_data(db, json.loads(Path(__file__).with_name("seed_data.json").read_text(encoding="utf-8")))
            credentials, accounts = prepare_accounts(db)
            if descriptor is None and credentials:
                raise RuntimeError("New accounts require a new --credentials-file path; existing credentials are never overwritten")
            seed_scenarios(db, accounts)
        if descriptor is not None:
            with os.fdopen(descriptor, "w", encoding="utf-8") as output:
                descriptor = None
                json.dump({"notice": "Private synthetic demo. Never publish these credentials.", "accounts": credentials},
                          output, ensure_ascii=False, indent=2)
                output.write("\n")
        print(f"Private demonstration ready. Credentials: {destination}; passwords preserved on repeat runs.")
    except BaseException:
        if descriptor is not None:
            os.close(descriptor)
            destination.unlink(missing_ok=True)
        raise


def seed_scenarios(db, accounts):
    """Create reproducible, linked synthetic examples through domain services."""
    # Imports stay here to keep credential provisioning separate from commerce.
    from datetime import timedelta
    from decimal import Decimal
    from uuid import NAMESPACE_URL, uuid5
    from app.api.schemas import BookingInput
    from app.api.commerce_schemas import PaymentInput
    from app.core.clock import at_time
    from app.domain.models import Booking, Departure, PromoCode, utc_now
    from app.domain.engagement import Review, SavedSearch, SupportTicket, SupportMessage
    from app.services import commerce_service as commerce
    from app.services.engagement_service import emit_event, refresh_review_rating
    def demo_id(name):
        return str(uuid5(NAMESPACE_URL, "sapartravel/private-demo/" + name))
    if not db.get(PromoCode, demo_id("promo")):
        now = utc_now()
        # Never replace a code created independently by a user.
        if not db.scalar(select(PromoCode.id).where(PromoCode.code == "SAPAR10")):
            db.add(PromoCode(id=demo_id("promo"), code="SAPAR10", kind="percent", value=Decimal("10"),
                         currency="KZT", min_amount=Decimal("10000"),
                         starts_at=now - timedelta(days=1), ends_at=now + timedelta(days=365),
                         usage_limit=100, per_user_limit=3, is_active=True))
    if not get_settings().payment_demo_enabled:
        return
    user = accounts["demo-traveler@example.com"]
    admin = accounts["demo-admin@example.com"]
    tours = db.scalars(select(Experience).where(Experience.vendor_id.in_([
        accounts["mountain-team@example.com"].id, accounts["world-team@example.com"].id,
    ])).order_by(Experience.slug)).all()
    if len(tours) < 4:
        return
    current = utc_now()
    completed = []
    for index, kind in enumerate(("completed", "completed-2", "completed-3", "refunded", "confirmed", "pending")):
        reference = "DEMO-" + kind.upper()
        existing = db.scalar(select(Booking).where(Booking.reference == reference))
        if existing:
            if kind.startswith("completed"):
                completed.append(existing)
            continue
        tour = tours[index % len(tours)]
        historical = kind.startswith("completed")
        moment = current - timedelta(days=tour.duration_days + 40) if historical else current
        with at_time(moment):
            start = commerce.today() + timedelta(days=14 if historical else 21+index)
            departure = db.scalar(select(Departure).where(Departure.experience_id == tour.id, Departure.start_date == start))
            if not departure:
                departure = Departure(experience_id=tour.id, start_date=start,
                                      end_date=start + timedelta(days=tour.duration_days-1), capacity=8+index, price=tour.price_from)
                db.add(departure)
                db.flush()
            booking = commerce.create_booking(db, user, BookingInput(
                departure_id=departure.id, travelers_count=2,
                contact_name=user.name, contact_email=user.email,
                participants=[{"name": user.name}, {"name": "Демо участник"}],
                notes="Синтетическая история демонстрационного аккаунта"))
            booking.reference = reference
            db.flush()
            if kind != "pending":
                commerce.initiate_payment(db, user, booking.id, PaymentInput(
                    card_number="4242424242424242", holder_name="DEMO TRAVELER", expiry_month=12,
                    expiry_year=moment.year+2, cvc="123"), "demo-scenario-" + kind)
        if historical:
            commerce.complete_booking(db, db.get(User, tour.vendor_id), booking.id)
            completed.append(booking)
        elif kind == "refunded":
            commerce.cancel_booking(db, user, booking.id, "Демонстрация отмены с полным возвратом")
    for index, booking in enumerate(completed):
        if not db.scalar(select(Review.id).where(Review.booking_id == booking.id)):
            experience_id = booking.departure.experience_id
            db.add(Review(booking_id=booking.id, user_id=user.id, experience_id=experience_id,
                          rating=5 if index != 1 else 4, title="Демонстрационный отзыв о поездке",
                          text="Синтетический отзыв: удобная программа и внимательный организатор. Используется только для демонстрации сервиса.",
                          status="approved", moderated_by=admin.id, moderated_at=current))
            refresh_review_rating(db, experience_id)
    if not db.get(SavedSearch, demo_id("saved-search")):
        db.add(SavedSearch(id=demo_id("saved-search"), user_id=user.id, name="Природа до 300 000 ₸",
                           filters={"category": "Nature", "max_price": "300000", "sort": "price_asc"}))
    if completed and not db.get(SupportTicket, demo_id("ticket")):
        booking = completed[0]
        vendor_id = booking.departure.experience.vendor_id
        ticket = SupportTicket(id=demo_id("ticket"), user_id=user.id, vendor_id=vendor_id,
                               booking_id=booking.id, subject="Документы после поездки", status="resolved")
        db.add(ticket)
        db.flush()
        db.add(SupportMessage(ticket_id=ticket.id, author_id=user.id, author_role="traveler",
                              body="Где скачать подтверждение поездки?"))
        db.add(SupportMessage(ticket_id=ticket.id, author_id=vendor_id, author_role="vendor",
                              body="Подтверждение доступно на странице бронирования. Спасибо за путешествие!"))
        emit_event(db, user.id, "support.reply", "Ответ поддержки", "Организатор ответил на ваше обращение.",
                   booking_id=booking.id, title_en="Support replied", title_kk="Қолдау жауабы",
                   body_en="Your organizer has replied to your support request.", body_kk="Ұйымдастырушы өтінішіңізге жауап берді.")


if __name__ == "__main__":
    main()
