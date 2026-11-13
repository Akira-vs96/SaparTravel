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
from app.domain.models import Booking, CategoryRecord, Experience, PaymentAttempt, PromoCode, Refund
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


@router.get("/bookings/{booking_id}/cancellation-quote")
def cancellation_quote(booking_id: str, user: CurrentUser, db: DbSession):
    item = commerce.lock_booking(db, booking_id, user)
    return commerce.cancellation_quote(db, item)


@router.get("/manage/bookings/{booking_id}/cancellation-quote")
def manager_cancellation_quote(booking_id: str, user: Manager, db: DbSession):
    item = commerce.lock_booking(db, booking_id, user, manage=True)
    return commerce.cancellation_quote(db, item, force_full=True)


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
        item = commerce.cancel_booking(db, user, booking_id, data.reason, manage=True, force_full=True)
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
    validate_promo_scope(db, data)
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
    validate_promo_scope(db, data)
    for field, value in data.model_dump().items():
        setattr(item, field, value.upper() if field == "code" else value)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Некорректные параметры промокода.") from None
    return promo_data(item)


def validate_promo_scope(db, data):
    if data.category and not db.get(CategoryRecord, data.category):
        raise HTTPException(422, "Категория не найдена.")
    if data.experience_id and not db.get(Experience, data.experience_id):
        raise HTTPException(422, "Тур не найден.")


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
    snapshot = data["experience"]
    items = "".join(
        f"""<tr><td>{escape(str(entry["name"]))}</td>
        <td class="number">{entry["quantity"]}</td>
        <td class="number">{money(entry["total_amount"])} {escape(entry["currency"])}</td></tr>"""
        for entry in data["items"]
    )
    participants = "".join(
        f"<li>{escape(str(participant['name']))}</li>"
        for participant in data["participants"]
    )
    document = f'''<!doctype html>
<html lang="{lang}">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>SaparTravel · {escape(item.reference)}</title>
  <style>
    :root {{ color-scheme: light; --ink:#173d35; --muted:#718078; --line:#dfe6df; --accent:#ed795d; --soft:#f3f6f1; }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; background:#eef2ed; color:var(--ink); font:14px/1.55 Arial, sans-serif; }}
    .sheet {{ max-width:860px; margin:40px auto; padding:48px; background:#fff; box-shadow:0 12px 40px rgba(23,61,53,.12); }}
    .top {{ display:flex; justify-content:space-between; gap:24px; align-items:flex-start; border-bottom:1px solid var(--line); padding-bottom:28px; }}
    .brand {{ color:var(--ink); font-size:25px; font-weight:800; letter-spacing:-.04em; }}
    .brand span {{ color:var(--accent); }}
    .eyebrow {{ color:var(--muted); font-size:11px; font-weight:700; letter-spacing:.12em; text-transform:uppercase; }}
    h1 {{ margin:34px 0 8px; font-size:34px; letter-spacing:-.04em; }}
    h2 {{ margin:0 0 8px; font-size:20px; }}
    p {{ margin:6px 0; }}
    .reference {{ text-align:right; }}
    .badge {{ display:inline-block; margin-top:10px; padding:6px 11px; border-radius:999px; background:#e4f2e8; color:#237044; font-size:12px; font-weight:700; }}
    .hero {{ display:grid; grid-template-columns:1.4fr 1fr; gap:18px; margin:28px 0; }}
    .card {{ border:1px solid var(--line); border-radius:14px; padding:20px; }}
    .muted {{ color:var(--muted); }}
    .facts {{ display:grid; grid-template-columns:1fr 1fr; gap:14px 24px; margin-top:16px; }}
    .fact strong {{ display:block; margin-top:2px; }}
    table {{ width:100%; margin-top:14px; border-collapse:collapse; }}
    th,td {{ padding:12px 8px; border-bottom:1px solid var(--line); text-align:left; }}
    th {{ color:var(--muted); font-size:11px; text-transform:uppercase; letter-spacing:.08em; }}
    .number {{ text-align:right; white-space:nowrap; }}
    .total {{ display:flex; justify-content:space-between; align-items:center; margin-top:18px; padding-top:18px; border-top:2px solid var(--ink); font-size:22px; font-weight:800; }}
    .notice {{ margin-top:28px; padding:16px 18px; border-radius:12px; background:var(--soft); color:#53645c; }}
    ul {{ margin:8px 0 0; padding-left:20px; }}
    footer {{ display:flex; justify-content:space-between; gap:20px; margin-top:36px; padding-top:18px; border-top:1px solid var(--line); color:var(--muted); font-size:11px; }}
    @media (max-width:650px) {{ body {{ background:#fff; }} .sheet {{ margin:0; padding:24px; box-shadow:none; }} .top,.hero,footer {{ display:block; }} .reference {{ margin-top:18px; text-align:left; }} .facts {{ grid-template-columns:1fr; }} h1 {{ font-size:28px; }} }}
    @media print {{ body {{ background:#fff; }} .sheet {{ margin:0; max-width:none; padding:0; box-shadow:none; }} }}
  </style>
</head>
<body>
  <main class="sheet">
    <header class="top">
      <div><div class="brand">sapar<span>travel</span>.</div><p class="eyebrow">{title}</p></div>
      <div class="reference"><div class="eyebrow">Booking reference</div><strong>{escape(item.reference)}</strong><div class="badge">Confirmed</div></div>
    </header>
    <h1>{escape(str(snapshot.get("title", "")))}</h1>
    <p class="muted">{escape(str(snapshot.get("destination", snapshot.get("country", ""))))}</p>
    <section class="hero">
      <div class="card"><div class="eyebrow">Trip dates</div><h2>{item.start_date.isoformat()} — {item.end_date.isoformat()}</h2><p class="muted">{data["travelers_count"]} traveler(s)</p></div>
      <div class="card"><div class="eyebrow">Contact</div><strong>{escape(data["contact_name"])}</strong><p class="muted">{escape(data["contact_email"])}</p></div>
    </section>
    <section class="card">
      <div class="eyebrow">Travelers</div><ul>{participants}</ul>
    </section>
    <section class="card" style="margin-top:18px">
      <div class="eyebrow">Booking summary</div>
      <table><thead><tr><th>Item</th><th class="number">Qty</th><th class="number">Amount</th></tr></thead><tbody>{items}</tbody></table>
      <div class="total"><span>Total</span><span>{money(data["total_amount"])} {escape(item.currency)}</span></div>
    </section>
    <div class="notice"><strong>{escape(notice)}</strong><p>{escape(data["cancellation_policy"].get("description", ""))}</p></div>
    <footer><span>SaparTravel · {escape(item.reference)}</span><span>Keep this confirmation for your records</span></footer>
  </main>
</body>
</html>'''
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
