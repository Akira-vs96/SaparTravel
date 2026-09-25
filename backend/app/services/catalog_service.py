from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domain.models import Booking, Departure, Experience, User


def localized(obj, field: str, lang: str):
    return (getattr(obj, f"{field}_{lang}", None) if lang != "ru" else None) or getattr(obj, field)


def user_data(user: User) -> dict:
    return {"id": user.id, "name": user.name, "email": user.email, "role": user.role}


def experience_data(experience: Experience, lang: str = "ru") -> dict:
    destination = experience.destination
    return {
        "id": experience.id, "slug": experience.slug,
        "title": localized(experience, "title", lang),
        "destination_slug": destination.slug, "destination": localized(destination, "name", lang),
        "country": localized(destination, "country", lang), "continent": destination.continent,
        "category": experience.category, "duration_days": experience.duration_days,
        "price_from": float(experience.price_from), "currency": experience.currency,
        "rating": float(experience.rating), "review_count": experience.review_count,
        "image_url": experience.image_url, "tags": localized(experience, "tags", lang),
        "description": localized(experience, "description", lang),
        "vendor": {"id": experience.vendor_id, "name": experience.vendor.name},
    }


def reserved_seats(db: Session, departure_id: str) -> int:
    return db.scalar(select(func.coalesce(func.sum(Booking.travelers_count), 0)).where(
        Booking.departure_id == departure_id, Booking.status != "cancelled",
    )) or 0


def departure_data(departure: Departure, reserved: int, manage: bool = False) -> dict:
    result = {
        "id": departure.id, "start_date": departure.start_date.isoformat(),
        "end_date": departure.end_date.isoformat(), "price": float(departure.price),
        "available_seats": max(0, departure.capacity - reserved),
    }
    if manage:
        result["capacity"] = departure.capacity
    return result


def experience_detail(db: Session, experience: Experience, lang: str = "ru", manage: bool = False) -> dict:
    result = experience_data(experience, lang)
    for key in ("itinerary", "included", "excluded"):
        result[key] = localized(experience, key, lang)
    query = select(Departure).where(Departure.experience_id == experience.id).order_by(Departure.start_date)
    if not manage:
        query = query.where(Departure.start_date > date.today())
    departures = db.scalars(query).all()
    counts = dict(db.execute(select(Booking.departure_id, func.sum(Booking.travelers_count)).where(
        Booking.departure_id.in_([item.id for item in departures]), Booking.status != "cancelled",
    ).group_by(Booking.departure_id)).all()) if departures else {}
    result["departures"] = [departure_data(item, counts.get(item.id, 0), manage) for item in departures]
    if manage:
        # Management always receives original values, so changing languages cannot overwrite translations.
        for key in ("title", "description", "tags", "itinerary", "included", "excluded"):
            for suffix in ("", "_en", "_kk"):
                result[key + suffix] = getattr(experience, key + suffix)
        result.update(destination_id=experience.destination_id, is_published=experience.is_published)
    return result


def booking_snapshot(experience: Experience) -> dict:
    return {
        lang: {"id": experience.id, "slug": experience.slug, "title": localized(experience, "title", lang),
               "image_url": experience.image_url, "destination": localized(experience.destination, "name", lang)}
        for lang in ("ru", "kk", "en")
    }


def booking_data(booking: Booking, lang: str = "ru") -> dict:
    return {
        "id": booking.id, "reference": booking.reference, "status": booking.status,
        "payment_status": "pay_on_confirmation", "travelers_count": booking.travelers_count,
        "total_amount": float(booking.total_amount), "currency": booking.currency,
        "contact_name": booking.contact_name, "contact_email": booking.contact_email, "notes": booking.notes,
        "created_at": booking.created_at.isoformat(), "start_date": booking.start_date.isoformat(),
        "end_date": booking.end_date.isoformat(), "departure_id": booking.departure_id,
        "experience": booking.experience_snapshot.get(lang) or booking.experience_snapshot["ru"],
    }
