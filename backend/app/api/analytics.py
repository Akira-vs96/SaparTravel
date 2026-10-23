"""Scoped accounting views: orders, provider receipts and refunds stay distinct."""
import csv
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from io import StringIO
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException, Query, Response
from sqlalchemy import func, select

from app.core.security import DbSession, Manager
from app.domain.models import Booking, Departure, Experience, PaymentAttempt, Refund
from app.services.catalog_service import active_booking_condition

router = APIRouter()


def amount(value):
    return format(Decimal(value or 0).quantize(Decimal("0.01")), ".2f")


def bounds(start, end):
    if start and end and start > end:
        raise HTTPException(422, "Дата начала периода должна быть не позже даты окончания.")
    zone = ZoneInfo("Asia/Almaty")
    return (datetime.combine(start, time.min, zone).astimezone(timezone.utc) if start else None,
            datetime.combine(end + timedelta(days=1), time.min, zone).astimezone(timezone.utc) if end else None)


def period(query, column, lower, upper):
    if lower:
        query = query.where(column >= lower)
    if upper:
        query = query.where(column < upper)
    return query


def scope(query, user):
    return query.where(Experience.vendor_id == user.id) if user.role != "admin" else query


@router.get("/manage/analytics")
def analytics(user: Manager, db: DbSession,
              start: date | None = Query(default=None, alias="from"),
              end: date | None = Query(default=None, alias="to")):
    lower, upper = bounds(start, end)
    base = scope(select(Booking.id).join(Departure).join(Experience), user)
    booking_ids = period(base, Booking.created_at, lower, upper)
    bookings_count, travelers_count = db.execute(select(func.count(), func.coalesce(func.sum(Booking.travelers_count), 0)).where(
        Booking.id.in_(booking_ids))).one()
    turnover = db.execute(select(Booking.currency, func.sum(Booking.total_amount)).where(
        Booking.id.in_(booking_ids), Booking.status.in_(("confirmed", "completed"))).group_by(Booking.currency)).all()
    owned_bookings = scope(select(Booking.id).join(Departure).join(Experience), user)
    payments = period(select(PaymentAttempt.currency, func.sum(PaymentAttempt.amount)).where(
        PaymentAttempt.booking_id.in_(owned_bookings), PaymentAttempt.status == "succeeded"), PaymentAttempt.created_at, lower, upper)
    refunds = period(select(Refund.currency, func.sum(Refund.amount)).where(
        Refund.booking_id.in_(owned_bookings), Refund.status == "succeeded"), Refund.created_at, lower, upper)
    paid = dict(db.execute(payments.group_by(PaymentAttempt.currency)).all())
    returned = dict(db.execute(refunds.group_by(Refund.currency)).all())
    sales = dict(turnover)
    currencies = [{"currency": currency, "turnover": amount(sales.get(currency)),
                   "successful_payments": amount(paid.get(currency)), "refunds_amount": amount(returned.get(currency)),
                   "net_received": amount(paid.get(currency, 0)-returned.get(currency, 0))}
                  for currency in sorted(set(sales) | set(paid) | set(returned) | {"KZT"})]
    departures_query = scope(select(Departure.id, Departure.capacity).join(Experience).where(Departure.status == "scheduled"), user)
    if start:
        departures_query = departures_query.where(Departure.start_date >= start)
    if end:
        departures_query = departures_query.where(Departure.start_date <= end)
    departures = db.execute(departures_query).all()
    occupied = db.scalar(select(func.coalesce(func.sum(Booking.travelers_count), 0)).where(
        Booking.departure_id.in_([item.id for item in departures]), active_booking_condition())) or 0
    kzt = next(row for row in currencies if row["currency"] == "KZT")
    return {"bookings_count": bookings_count, "travelers_count": travelers_count,
            "capacity": sum(item.capacity for item in departures),
            "occupied_seats": occupied,
            **{key: value for key, value in kzt.items() if key != "currency"}, "currency": "KZT",
            "currencies": currencies, "platform_revenue": None, "income_model": "no_commission_ledger",
            "period_basis": "bookings and operations: created_at; capacity: departure start_date; timezone: Asia/Almaty"}


def csv_cell(value):
    value = str(value if value is not None else "")
    # Prevent spreadsheet formula execution, including leading whitespace and
    # control characters. csv.writer separately handles quotes/newlines/commas.
    if value.lstrip().startswith(("=", "+", "-", "@")) or value.startswith(("\t", "\r", "\n")):
        return "'" + value
    return value


@router.get("/manage/analytics.csv")
def export_analytics(user: Manager, db: DbSession,
                     start: date | None = Query(default=None, alias="from"),
                     end: date | None = Query(default=None, alias="to")):
    lower, upper = bounds(start, end)
    paid = select(PaymentAttempt.booking_id, func.sum(PaymentAttempt.amount).label("amount")).where(
        PaymentAttempt.status == "succeeded").group_by(PaymentAttempt.booking_id).subquery()
    refunded = select(Refund.booking_id, func.sum(Refund.amount).label("amount")).where(
        Refund.status == "succeeded").group_by(Refund.booking_id).subquery()
    query = select(Booking.reference, Booking.contact_name, Booking.status, Booking.currency, Booking.total_amount,
                   func.coalesce(paid.c.amount, 0), func.coalesce(refunded.c.amount, 0), Booking.start_date,
                   Booking.end_date).join(Departure).join(Experience).outerjoin(paid, paid.c.booking_id == Booking.id).outerjoin(
                       refunded, refunded.c.booking_id == Booking.id)
    query = period(scope(query, user), Booking.created_at, lower, upper).order_by(Booking.created_at.desc()).limit(10000)
    output = StringIO(newline="")
    output.write("\ufeff")
    writer = csv.writer(output)
    writer.writerow(["reference", "contact_name", "status", "currency", "order_amount", "paid", "refunded", "start_date", "end_date"])
    for row in db.execute(query):
        writer.writerow([csv_cell(value) for value in row])
    return Response(output.getvalue(), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": 'attachment; filename="sapartravel-bookings.csv"', "Cache-Control": "no-store"})
