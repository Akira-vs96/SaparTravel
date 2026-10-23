"""Transactional adapters for notifications and significant action records."""
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import func, select

from app.domain.engagement import AuditLog, Notification, Review
from app.domain.models import Experience


# Notifications are domain events. Translation stays in the delivery adapter so
# commerce services do not need to know the viewer's language.
EVENT_TRANSLATIONS = {
    "booking.created": ("Booking reserved", "Your places are reserved. Complete the test payment before the reservation expires.", "Бронь жасалды", "Орындарыңыз сақталды. Бронь мерзімі біткенше тест төлемін аяқтаңыз."),
    "booking.expired": ("Reservation expired", "The payment deadline passed. Your reserved places have been released.", "Бронь мерзімі аяқталды", "Төлем мерзімі өтті. Сақталған орындар босатылды."),
    "booking.cancelled": ("Booking cancelled", "Your booking has been cancelled. Check the booking for the refund status and cancellation terms.", "Бронь жойылды", "Бронь жойылды. Қайтарым күйін және бас тарту шарттарын броньдан қараңыз."),
    "booking.completed": ("Trip completed", "Your trip is complete. You can now leave a verified review.", "Сапар аяқталды", "Сапарыңыз аяқталды. Енді расталған пікір қалдыра аласыз."),
    "payment.succeeded": ("Test payment successful", "Your test payment succeeded. Your booking is confirmed. No real money was charged.", "Тест төлемі сәтті өтті", "Тест төлемі сәтті өтті. Бронь расталды. Нақты ақша алынбады."),
    "payment.late": ("Late test payment received", "A late payment result was recorded. Check your booking for confirmation or a compensation refund.", "Кешіккен тест төлемі тіркелді", "Төлемнің кешіккен нәтижесі тіркелді. Растау немесе өтем қайтарымын броньдан қараңыз."),
    "refund.succeeded": ("Test refund completed", "Your test refund succeeded. No real bank operation was performed.", "Тест қайтарымы аяқталды", "Тест қайтарымы сәтті өтті. Нақты банк операциясы жасалмады."),
    "refund.failed": ("Test refund needs attention", "The test refund failed. You can retry an eligible refund from the booking.", "Тест қайтарымына назар аударыңыз", "Тест қайтарымы орындалмады. Рұқсат етілген қайтарымды броньдан қайталауға болады."),
    "refund.pending": ("Test refund pending", "Your test refund is being processed. The current status is available in your booking.", "Тест қайтарымы өңделуде", "Тест қайтарымы өңделуде. Ағымдағы күйін броньдан көре аласыз."),
}


def emit_event(db, user_id, event, title, body, booking_id=None, *, title_en=None, title_kk=None, body_en=None, body_kk=None):
    translated = EVENT_TRANSLATIONS.get(event, (title, body, title, body))
    item = Notification(user_id=user_id, event=event, title=title, body=body, booking_id=booking_id,
                        title_en=title_en or translated[0], title_kk=title_kk or translated[2], body_en=body_en or translated[1], body_kk=body_kk or translated[3])
    db.add(item)
    return item


def audit(db, actor_id, action, resource_type, resource_id=None, details=None):
    db.add(AuditLog(actor_id=actor_id, action=action, resource_type=resource_type,
                    resource_id=resource_id, details=details or {}))


def refresh_review_rating(db, experience_id):
    """Rebuild the catalogue projection from approved, booking-backed reviews."""
    db.flush()
    rating, count = db.execute(select(func.avg(Review.rating), func.count(Review.id)).where(
        Review.experience_id == experience_id, Review.status == "approved",
    )).one()
    item = db.get(Experience, experience_id)
    if item:
        item.rating = Decimal(str(rating or 0)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
        item.review_count = count
