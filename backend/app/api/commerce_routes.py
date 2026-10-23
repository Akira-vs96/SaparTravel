"""HTTP contracts for checkout, payment attempts, refunds and booking documents."""
from datetime import datetime, timedelta, timezone
from html import escape
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Header, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.api.schemas import BookingInput, BookingStatusInput, Language
from app.api.commerce_schemas import CancellationInput, ConfirmationInput, PaymentInput, PromoInput, RefundInput
from app.adapters.demo_payments import TEST_INSTRUMENTS
from app.core.security import Admin, CurrentUser, DbSession, Manager
from app.domain.models import Booking, PaymentAttempt, PromoCode, Refund
from app.services.catalog_service import booking_data, money, payment_data, refund_data
from app.services import commerce_service as commerce

router = APIRouter()


def refreshed_booking(db, item):
    db.expire(item)
    return booking_data(item)


@router.post("/bookings/quote")
def booking_quote(data: BookingInput, user: CurrentUser, db: DbSession, lang: Language = "ru"):
    result = commerce.quote_booking(db, user, data, lang)
    db.commit()  # Release inventory and promo locks; no reservation is created.
    return result


@router.post("/bookings", status_code=201)
def create_booking(data: BookingInput, user: CurrentUser, db: DbSession, lang: Language = "ru"):
    item = commerce.create_booking(db, user, data)
    db.commit()
    db.expire(item)
    return booking_data(item, lang)


@router.get("/bookings")
def bookings(user: CurrentUser, db: DbSession, lang: Language = "ru"):
    rows = db.scalars(select(Booking).where(Booking.user_id == user.id).order_by(Booking.created_at.desc())).all()
    # Availability already excludes expired reservations even before this housekeeping runs.
    for item in rows:
        if item.status == "pending" and (not item.expires_at or commerce.aware(item.expires_at) <= commerce.now()):
            item = commerce.lock_booking(db, item.id, user)
            commerce.expire_if_needed(db, item)
    db.commit()
    return {"items": [booking_data(item, lang) for item in rows]}


@router.get("/bookings/{booking_id}")
def booking_detail(booking_id: str, user: CurrentUser, db: DbSession, lang: Language = "ru"):
    item = commerce.lock_booking(db, booking_id, user)
    commerce.expire_if_needed(db, item)
    db.commit()
    db.expire(item)
    return booking_data(item, lang)


@router.post("/bookings/{booking_id}/cancel")
def cancel_booking(booking_id: str, user: CurrentUser, db: DbSession, data: CancellationInput | None = None, lang: Language = "ru"):
    item = commerce.cancel_booking(db, user, booking_id, data.reason if data else "Отмена путешественником")
    db.commit()
    db.expire(item)
    return booking_data(item, lang)


@router.get("/payments/test-instruments")
def test_instruments(user: CurrentUser):
    commerce.require_demo()
    current = commerce.today()
    return {"notice": "Тестовая оплата. Деньги не списываются", "items": [
        {**item, "masked_card": "•••• " + item["card_number"][-4:], "expiry_month": current.month,
         "expiry_year": current.year + 2, "cvc": "123"} for item in TEST_INSTRUMENTS]}


@router.post("/bookings/{booking_id}/payments")
def pay(booking_id: str, data: PaymentInput, user: CurrentUser, db: DbSession,
        idempotency_key: Annotated[str | None, Header()] = None):
    try:
        item = commerce.initiate_payment(db, user, booking_id, data, idempotency_key)
        db.commit()
    except IntegrityError:
        db.rollback()
        # A key reused concurrently across different departures is guarded by its DB unique
        # constraint; replay it only after checking the exact fingerprint and owner.
        item = db.scalar(select(PaymentAttempt).where(PaymentAttempt.user_id == user.id, PaymentAttempt.idempotency_key == idempotency_key))
        if not item or item.request_fingerprint != commerce.fingerprint(booking_id, data):
            raise HTTPException(409, "Ключ идемпотентности уже используется другой операцией.") from None
    db.expire(item)
    return payment_data(item)


@router.get("/payments/{payment_id}")
def payment_detail(payment_id: str, user: CurrentUser, db: DbSession):
    _, item = commerce.locked_payment(db, payment_id, user)
    return payment_data(item)


@router.post("/payments/{payment_id}/confirm")
def confirm(payment_id: str, data: ConfirmationInput, user: CurrentUser, db: DbSession):
    item = commerce.confirm_payment(db, user, payment_id, data.outcome)
    db.commit()
    db.expire(item)
    return payment_data(item)


@router.post("/payments/{payment_id}/reconcile")
def reconcile(payment_id: str, user: CurrentUser, db: DbSession):
    item = commerce.reconcile_payment(db, user, payment_id)
    db.commit()
    db.expire(item)
    return payment_data(item)


@router.post("/refunds/{refund_id}/retry")
def retry_refund(refund_id: str, user: CurrentUser, db: DbSession):
    item = commerce.retry_refund(db, user, refund_id)
    db.commit()
    db.expire(item)
    return refund_data(item)


@router.get("/manage/payments")
def manage_payments(user: Admin, db: DbSession):
    return {"items": [payment_data(item) for item in db.scalars(select(PaymentAttempt).order_by(PaymentAttempt.created_at.desc()).limit(1000))]}


@router.get("/manage/refunds")
def manage_refunds(user: Admin, db: DbSession):
    return {"items": [refund_data(item) for item in db.scalars(select(Refund).order_by(Refund.created_at.desc()).limit(1000))]}


@router.post("/manage/bookings/{booking_id}/refunds", status_code=201)
def create_refund(booking_id: str, data: RefundInput, user: Admin, db: DbSession,
                  idempotency_key: Annotated[str | None, Header()] = None):
    commerce.require_demo()
    if not idempotency_key or not 8 <= len(idempotency_key) <= 100:
        raise HTTPException(422, "Передайте ключ идемпотентности длиной 8–100 символов.")
    booking = commerce.lock_booking(db, booking_id, user, manage=True)
    payment = db.scalar(select(PaymentAttempt).where(PaymentAttempt.booking_id == booking.id, PaymentAttempt.status == "succeeded"))
    if not payment:
        raise HTTPException(409, "У брони нет успешной оплаты.")
    item = commerce.create_refund(db, booking, payment, data.amount, data.reason, idempotency_key, user, data.scenario)
    db.commit()
    db.expire(item)
    return refund_data(item)


@router.get("/manage/bookings/{booking_id}")
def manage_booking_detail(booking_id: str, user: Manager, db: DbSession, lang: Language = "ru"):
    item = commerce.lock_booking(db, booking_id, user, manage=True)
    commerce.expire_if_needed(db, item)
    db.commit()
    db.expire(item)
    return booking_data(item, lang)


@router.patch("/manage/bookings/{booking_id}")
def manage_booking(booking_id: str, data: BookingStatusInput, user: Manager, db: DbSession, lang: Language = "ru"):
    if data.status == "cancelled":
        item = commerce.cancel_booking(db, user, booking_id, "Отмена поставщиком или администратором", manage=True, force_full=True)
    elif data.status == "completed":
        item = commerce.complete_booking(db, user, booking_id)
    else:
        item = commerce.lock_booking(db, booking_id, user, manage=True)
        if item.status != "confirmed":
            raise HTTPException(409, "Бронирование подтверждается только после успешной оплаты.")
    db.commit()
    db.expire(item)
    return booking_data(item, lang)


def promo_data(item):
    return {"id": item.id, "code": item.code, "kind": item.kind, "value": money(item.value), "currency": "KZT",
            "min_amount": money(item.min_amount), "starts_at": item.starts_at.isoformat(), "ends_at": item.ends_at.isoformat(),
            "usage_limit": item.usage_limit, "per_user_limit": item.per_user_limit, "is_active": item.is_active,
            "experience_id": item.experience_id, "category": item.category}


@router.get("/manage/promocodes")
def promocodes(user: Admin, db: DbSession):
    return {"items": [promo_data(item) for item in db.scalars(select(PromoCode).order_by(PromoCode.code))]}


@router.post("/manage/promocodes", status_code=201)
def create_promo(data: PromoInput, user: Admin, db: DbSession):
    item = PromoCode(**{**data.model_dump(), "code": data.code.upper()})
    db.add(item)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Промокод уже существует или область действия не найдена.") from None
    return promo_data(item)


@router.put("/manage/promocodes/{promo_id}")
def update_promo(promo_id: str, data: PromoInput, user: Admin, db: DbSession):
    item = db.get(PromoCode, promo_id, with_for_update=True)
    if not item:
        raise HTTPException(404, "Промокод не найден.")
    for field, value in data.model_dump().items():
        setattr(item, field, value.upper() if field == "code" else value)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Некорректные параметры промокода.") from None
    return promo_data(item)


@router.get("/bookings/{booking_id}/confirmation")
def confirmation(booking_id: str, user: CurrentUser, db: DbSession, lang: Language = "ru"):
    item = commerce.lock_booking(db, booking_id, user)
    if item.status not in ("confirmed", "completed"):
        raise HTTPException(409, "Подтверждение доступно после оплаты.")
    data = booking_data(item, lang)
    title = {"ru": "Подтверждение бронирования", "en": "Booking confirmation", "kk": "Броньды растау"}[lang]
    notice = {"ru": "Демонстрационное подтверждение. Тестовая оплата. Деньги не списываются.",
              "en": "Demonstration confirmation. Test payment. No money is charged.",
              "kk": "Демонстрациялық растау. Сынақ төлемі. Ақша алынбайды."}[lang]
    document = f'''<!doctype html><html lang="{lang}"><meta charset="utf-8"><title>{escape(item.reference)}</title>
    <style>body{{font:18px system-ui;max-width:800px;margin:60px auto;padding:24px;color:#153f37}}h1{{font-size:28px}}</style>
    <h1>SaparTravel · {title}</h1><h2>{escape(item.reference)}</h2><h3>{escape(data["experience"]["title"])}</h3>
    <p>{item.start_date.isoformat()} — {item.end_date.isoformat()}</p><p>{escape(item.contact_name)} · {item.travelers_count}</p>
    <p>{money(item.total_amount)} {escape(item.currency)}</p><p>{escape(data['cancellation_policy'].get("description", ""))}</p>
    <p>{notice}</p></html>'''
    return Response(document, media_type="text/html", headers={"Content-Disposition": f'attachment; filename="{item.reference}.html"', "Cache-Control": "no-store"})


def ics_escape(value):
    return value.replace("\\", "\\\\").replace("\n", "\\n").replace(";", "\\;").replace(",", "\\,").replace("\r", "")


@router.get("/bookings/{booking_id}/calendar.ics")
def calendar(booking_id: str, user: CurrentUser, db: DbSession, lang: Language = "ru"):
    item = commerce.lock_booking(db, booking_id, user)
    if item.status not in ("confirmed", "completed"):
        raise HTTPException(409, "Календарь доступен для подтверждённой поездки.")
    details = item.experience_snapshot.get(lang) or item.experience_snapshot["ru"]
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//SaparTravel//Demo Travel//RU", "CALSCALE:GREGORIAN", "BEGIN:VEVENT",
             f"UID:{item.id}@sapartravel.demo", f"DTSTAMP:{commerce.now().strftime('%Y%m%dT%H%M%SZ')}",
             f"DTSTART;VALUE=DATE:{item.start_date.strftime('%Y%m%d')}",
             f"DTEND;VALUE=DATE:{(item.end_date + timedelta(days=1)).strftime('%Y%m%d')}",
             f"SUMMARY:{ics_escape(details['title'])}", f"DESCRIPTION:{ics_escape('SaparTravel ' + item.reference)}", "END:VEVENT", "END:VCALENDAR"]
    # RFC 5545 folds long lines by UTF-8 octets without splitting a character.
    folded = []
    for line in lines:
        current = ""
        for char in line:
            if len((current+char).encode("utf-8")) > 74:
                folded.append(current)
                current = " "
            current += char
        folded.append(current)
    return Response("\r\n".join(folded)+"\r\n", media_type="text/calendar", headers={"Content-Disposition": f'attachment; filename="{item.reference}.ics"', "Cache-Control": "no-store"})
