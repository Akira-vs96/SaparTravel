"""Catalog presentation and immutable agreement snapshots.

The normalized translation and collection rows are canonical; Python properties preserve
compatibility with the earlier API without storing repeated JSON or translation columns.
"""
from datetime import date, datetime, timezone
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.domain.models import Booking, Departure, Experience, User
from app.core.clock import business_today, utc_now


def money(value) -> str:
    return format(Decimal(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP), ".2f")


def localized(obj, field: str, lang: str):
    return (getattr(obj, f"{field}_{lang}", None) if lang != "ru" else None) or getattr(obj, field)


def user_data(user: User) -> dict:
    return {"id": user.id, "name": user.name, "email": user.email, "role": user.role}


def cancellation_policy(experience=None, lang="ru") -> dict:
    rules = [{"days_before": rule.days_before, "refund_percent": rule.refund_percent} for rule in experience.cancellation_rules] if experience and experience.cancellation_rules else [
        {"days_before": 7, "refund_percent": 100}, {"days_before": 2, "refund_percent": 80}, {"days_before": 0, "refund_percent": 50}]
    rules = sorted(rules, key=lambda rule: rule["days_before"], reverse=True)
    descriptions = {"ru": "; ".join(f"От {r['days_before']} дн. до начала — {r['refund_percent']}%" for r in rules) + ". При отмене поставщиком — 100%. Учебная политика, не требование закона.",
                    "en": "; ".join(f"At least {r['days_before']} days before — {r['refund_percent']}%" for r in rules) + ". Vendor cancellation: 100%. Educational policy, not a statement of law.",
                    "kk": "; ".join(f"Басталуға {r['days_before']} күн қалғанда — {r['refund_percent']}%" for r in rules) + ". Жеткізуші тоқтатса — 100%. Оқу саясаты, заң талабы емес."}
    return {"version": "demo-v1", "name": {"ru":"Учебные условия отмены","en":"Demo cancellation policy","kk":"Демо тоқтату шарттары"}[lang],
            "educational": True, "rules": rules, "description": descriptions[lang], "translations": descriptions}



def experience_data(experience: Experience, lang: str = "ru") -> dict:
    destination = experience.destination
    return {
        "id": experience.id, "slug": experience.slug,
        "title": localized(experience, "title", lang),
        "destination_slug": destination.slug, "destination": localized(destination, "name", lang),
        "country": localized(destination, "country", lang), "continent": destination.continent,
        "category": experience.category, "duration_days": experience.duration_days,
        "price_from": money(experience.price_from), "currency": experience.currency,
        "rating": float(experience.rating), "review_count": experience.review_count,
        "image_url": experience.image_url, "tags": localized(experience, "tags", lang),
        "description": localized(experience, "description", lang),
        "vendor": {"id": experience.vendor_id, "name": experience.vendor.name},
        "min_participants": experience.min_participants, "max_participants": experience.max_participants,
        "publication_status": experience.publication_status,
    }


def active_booking_condition(at=None):
    at = at or utc_now()
    return or_(Booking.status.in_(("confirmed", "completed")),
               and_(Booking.status == "pending", Booking.expires_at > at))


def reserved_seats(db: Session, departure_id: str, at=None) -> int:
    return db.scalar(select(func.coalesce(func.sum(Booking.travelers_count), 0)).where(
        Booking.departure_id == departure_id, active_booking_condition(at),
    )) or 0



def reservation_counts(db: Session, departure_ids, at=None) -> dict:
    ids = list(departure_ids)
    if not ids:
        return {}
    return dict(db.execute(select(Booking.departure_id, func.sum(Booking.travelers_count)).where(
        Booking.departure_id.in_(ids), active_booking_condition(at),
    ).group_by(Booking.departure_id)).all())

def departure_data(departure: Departure, reserved: int, manage: bool = False) -> dict:
    result = {"id": departure.id, "start_date": departure.start_date.isoformat(),
              "end_date": departure.end_date.isoformat(), "price": money(departure.price), "currency": "KZT",
              "available_seats": max(0, departure.capacity - reserved) if departure.status == "scheduled" else 0,
              "status": departure.status}
    if manage:
        result["capacity"] = departure.capacity
    return result


def experience_detail(db: Session, experience: Experience, lang: str = "ru", manage: bool = False,
                      *, departures=None, reserved_counts=None) -> dict:
    result = experience_data(experience, lang)
    for key in ("itinerary", "included", "excluded"):
        result[key] = localized(experience, key, lang)
    if departures is None:
        query = select(Departure).where(Departure.experience_id == experience.id).order_by(Departure.start_date)
        if not manage:
            query = query.where(Departure.start_date > business_today(), Departure.status == "scheduled")
        departures = db.scalars(query).all()
    counts = reserved_counts if reserved_counts is not None else reservation_counts(db, [item.id for item in departures])
    result["departures"] = [departure_data(item, counts.get(item.id, 0), manage) for item in departures]
    result["gallery"] = [item.url for item in experience.images] or [experience.image_url]
    result["services"] = [{"id": item.id, "name": item.name if manage else localized(item, "name", lang), "name_en": item.name_en,
                           "name_kk": item.name_kk, "price": money(item.price), "currency": "KZT",
                           "per_person": item.per_person, "is_active": item.is_active}
                          for item in experience.services if manage or item.is_active]
    result["cancellation_policy"] = cancellation_policy(experience, lang)
    result["cancellation_rules"] = result["cancellation_policy"]["rules"]
    if manage:
        for key in ("title", "description", "tags", "itinerary", "included", "excluded"):
            for suffix in ("", "_en", "_kk"):
                result[key + suffix] = getattr(experience, key + suffix)
        result.update(destination_id=experience.destination_id, is_published=experience.is_published)
    return result


def booking_snapshot(experience: Experience) -> dict:
    return {lang: {"id": experience.id, "slug": experience.slug, "title": localized(experience, "title", lang),
                   "image_url": experience.image_url, "destination": localized(experience.destination, "name", lang)}
            for lang in ("ru", "kk", "en")}


def payment_data(item) -> dict:
    messages = {"insufficient_funds": "Недостаточно средств на тестовой карте.", "bank_declined": "Банк отклонил тестовую оплату.",
                "provider_unavailable": "Демонстрационный сервис временно недоступен. Попробуйте другую попытку.",
                "authentication_failed": "Подтверждение оплаты не выполнено.", "authentication_expired": "Срок подтверждения истёк.",
                "authentication_cancelled": "Подтверждение отменено.", "outcome_unknown": "Результат пока неизвестен. Выполните сверку.",
                "late_payment_refunded": "Оплата получена после закрытия резерва. Создан полный компенсационный возврат."}
    return {"id": item.id, "booking_id": item.booking_id, "status": item.status, "amount": money(item.amount),
            "currency": item.currency, "masked_card": item.masked_card, "instrument_id": item.instrument_id,
            "error_code": item.error_code, "message": messages.get(item.error_code, "Оплата прошла успешно." if item.status == "succeeded" else ""),
            "requires_action": item.status == "requires_action", "action_expires_at": item.action_expires_at.isoformat() if item.action_expires_at else None,
            "created_at": item.created_at.isoformat(),
            "history": [{"status": e.status, "reason": e.reason, "created_at": e.created_at.isoformat()} for e in item.events]}


def refund_data(item) -> dict:
    return {"id": item.id, "payment_id": item.payment_id, "booking_id": item.booking_id, "status": item.status,
            "amount": money(item.amount), "currency": item.currency, "reason": item.reason,
            "created_at": item.created_at.isoformat(),
            "history": [{"status": e.status, "reason": e.reason, "created_at": e.created_at.isoformat()} for e in item.events]}


def history_reason(reason, lang):
    messages = {
        "Места зарезервированы на время оплаты": ("Places reserved while awaiting payment", "Төлемді күту кезінде орындар сақталды"),
        "Время резерва мест истекло": ("The place reservation expired", "Орындарды сақтау мерзімі аяқталды"),
        "Подтверждено после успешной оплаты": ("Confirmed after successful payment", "Сәтті төлемнен кейін расталды"),
        "Резерв закрыт до получения оплаты": ("The reservation closed before payment was received", "Төлем түскенге дейін бронь жабылды"),
        "Отмена поставщиком или администратором": ("Cancelled by the organizer or administrator", "Ұйымдастырушы немесе әкімші тоқтатты"),
        "Отмена путешественником": ("Cancelled by the traveler", "Саяхатшы бас тартты"),
        "Поездка завершена": ("The trip was completed", "Сапар аяқталды"),
    }
    if lang == "ru" or reason not in messages:
        return reason
    return messages[reason][0 if lang == "en" else 1]


def booking_data(booking: Booking, lang: str = "ru") -> dict:
    succeeded = [item for item in booking.payments if item.status == "succeeded"]
    paid = sum((item.amount for item in succeeded), Decimal(0))
    refunded = sum((item.amount for item in booking.refunds if item.status == "succeeded"), Decimal(0))
    status = booking.status
    expiry = booking.expires_at
    if expiry and expiry.tzinfo is None:
        expiry = expiry.replace(tzinfo=timezone.utc)
    if status == "pending" and expiry and expiry <= utc_now():
        status = "expired"
    last = booking.payments[-1] if booking.payments else None
    payment_status = "refunded" if paid and refunded >= paid else "partially_refunded" if refunded else "paid" if paid else last.status if last else "unpaid"
    snapshot = booking.experience_snapshot.get(lang) or booking.experience_snapshot.get("ru", {})
    return {"id": booking.id, "reference": booking.reference, "status": status, "payment_status": payment_status,
            "travelers_count": booking.travelers_count, "total_amount": money(booking.total_amount),
            "subtotal_amount": money(booking.subtotal_amount), "discount_amount": money(booking.discount_amount),
            "paid_amount": money(paid), "refunded_amount": money(refunded), "currency": booking.currency,
            "contact_name": booking.contact_name, "contact_email": booking.contact_email, "notes": booking.notes,
            "created_at": booking.created_at.isoformat(), "start_date": booking.start_date.isoformat(),
            "end_date": booking.end_date.isoformat(), "expires_at": expiry.isoformat() if expiry else None,
            "departure_id": booking.departure_id, "experience": snapshot,
            "participants": [{"name": item.name} for item in booking.participants],
            "items": [{"id": item.id, "kind": item.kind, "name": snapshot.get("title", item.name) if item.kind == "tour" else snapshot.get("service_names", {}).get(item.service_id, item.name), "quantity": item.quantity,
                       "unit_amount": money(item.unit_amount), "total_amount": money(item.total_amount), "currency": item.currency} for item in booking.items],
            "payments": [payment_data(item) for item in booking.payments], "refunds": [refund_data(item) for item in booking.refunds],
            "history": [{"status": item.status, "reason": history_reason(item.reason, lang), "actor_id": item.actor_id,
                         "actor_name": item.actor.name if item.actor else {"ru": "Система", "en": "System", "kk": "Жүйе"}[lang],
                         "created_at": item.created_at.isoformat()} for item in booking.history],
            "cancellation_policy": {**booking.cancellation_policy, "description": booking.cancellation_policy.get("translations", {}).get(lang, booking.cancellation_policy.get("description", ""))},
            "currency_conversion": ({"original_amount": money(booking.currency_conversion.original_amount), "original_currency": booking.currency_conversion.original_currency,
                                     "equivalent_amount": money(booking.currency_conversion.equivalent_amount), "equivalent_currency": "KZT", "factor": str(booking.currency_conversion.factor),
                                     "rule": booking.currency_conversion.rule} if booking.currency_conversion else None)}
