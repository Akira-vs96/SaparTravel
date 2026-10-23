"""Transactional booking, seat inventory, payment and refund application services.

Every seat-changing operation locks departure -> booking -> payment. Promo rows
are locked only after the departure, serializing their cross-departure limits.
No remote operation is performed while holding these locks: this demo adapter
only writes local durable operations. Real adapters must use an outbox.
"""
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
import hashlib
import hmac
import json
import secrets

from fastapi import HTTPException
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import lazyload

from app.adapters.demo_payments import TEST_INSTRUMENTS, provider
from app.core.config import get_settings
from app.domain.models import (
    Booking, BookingItem, BookingParticipant, BookingStatusHistory, Departure, Experience,
    PaymentAttempt, PaymentEvent, PromoCode, PromoRedemption, Refund, RefundEvent,
)
from app.services.catalog_service import booking_snapshot, cancellation_policy, localized, reserved_seats


def now():
    from app.core.clock import utc_now
    return utc_now()


def aware(value):
    return value.replace(tzinfo=timezone.utc) if value and value.tzinfo is None else value


def today():
    # Business departure dates use Kazakhstan's calendar, independent of the host timezone.
    from zoneinfo import ZoneInfo
    return now().astimezone(ZoneInfo("Asia/Almaty")).date()


def rounded(value):
    return Decimal(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def emit(db, booking, event, title, body, actor=None):
    from app.services.engagement_service import emit_event, audit
    translations = {
        "booking.created": ("Seats reserved", "Your booking is awaiting payment.", "Орындар сақталды", "Бронь төлемді күтуде."),
        "booking.expired": ("Reservation expired", "The payment deadline passed and the seats are available again.", "Резерв мерзімі аяқталды", "Төлем мерзімі аяқталды, орындар қайта қолжетімді."),
        "booking.cancelled": ("Booking cancelled", "Your booking was cancelled and the seats were released.", "Бронь тоқтатылды", "Бронь тоқтатылып, орындар босатылды."),
        "booking.completed": ("Trip completed", "Thank you for travelling. You can now leave a review.", "Сапар аяқталды", "Саяхат үшін рақмет. Енді пікір қалдыруға болады."),
        "payment.failed": ("Payment declined", "The payment did not complete. You may try another allowed test card.", "Төлем қабылданбады", "Төлем аяқталмады. Басқа рұқсат етілген тест картасын қолданып көріңіз."),
        "payment.pending": ("Payment outcome pending", "The provider result is unknown. Check its status before retrying.", "Төлем нәтижесі күтілуде", "Провайдер нәтижесі белгісіз. Қайталаудан бұрын күйін тексеріңіз."),
        "payment.succeeded": ("Payment received", "Your booking is confirmed.", "Төлем алынды", "Бронь расталды."),
        "payment.late": ("Late payment", "Your reservation had closed. A full compensation refund was created.", "Кешіккен төлем", "Резерв жабылған. Толық өтемақы қайтарымы жасалды."),
        "refund.succeeded": ("Refund completed", "The demo provider confirmed your refund.", "Қаражат қайтарылды", "Демо провайдер қаражат қайтарымын растады."),
        "refund.failed": ("Refund needs another attempt", "The provider could not complete the refund. It can be retried.", "Қайтарымды қайталау қажет", "Провайдер қайтарымды аяқтай алмады. Қайталап көріңіз."),
    }
    en, en_body, kk, kk_body = translations.get(event, ("Booking update", body, "Бронь жаңартылды", body))
    emit_event(db, booking.user_id, event, title, body, booking_id=booking.id,
               title_en=en, title_kk=kk, body_en=en_body, body_kk=kk_body)
    audit(db, actor.id if hasattr(actor, "id") else actor, event, "booking", booking.id, {"reference": booking.reference})


def history(db, booking, actor=None, reason=""):
    db.add(BookingStatusHistory(booking_id=booking.id, actor_id=actor.id if actor else None, status=booking.status, reason=reason))


def lock_departure(db, departure_id):
    return db.scalar(select(Departure).options(lazyload("*")).where(Departure.id == departure_id)
                     .with_for_update(of=Departure).execution_options(populate_existing=True))


def lock_booking(db, booking_id, user=None, manage=False):
    query = select(Booking).options(lazyload("*")).where(Booking.id == booking_id)
    if user:
        if manage and user.role != "admin":
            query = query.join(Departure).join(Experience).where(Experience.vendor_id == user.id)
        elif not manage:
            query = query.where(Booking.user_id == user.id)
    booking = db.scalar(query)
    if not booking:
        raise HTTPException(404, "Бронирование не найдено.")
    lock_departure(db, booking.departure_id)
    return db.scalar(query.with_for_update(of=Booking).execution_options(populate_existing=True))


def expire_if_needed(db, booking):
    if booking.status == "pending" and (not booking.expires_at or aware(booking.expires_at) <= now()):
        booking.status = "expired"
        history(db, booking, reason="Время резерва мест истекло")
        emit(db, booking, "booking.expired", "Резерв истёк", "Время для оплаты истекло; места снова доступны для бронирования.")
        db.flush()
        return True
    return False


def quote_context(db, user, data):
    departure = lock_departure(db, data.departure_id)
    if not departure or not departure.experience.is_published or departure.experience.publication_status != "published":
        raise HTTPException(404, "Заезд не найден или тур снят с публикации.")
    experience = departure.experience
    if departure.status != "scheduled" or departure.start_date <= today():
        raise HTTPException(409, "Бронирование этого заезда уже закрыто.")
    if not experience.min_participants <= data.travelers_count <= experience.max_participants:
        raise HTTPException(422, "Число участников не соответствует ограничениям тура.")
    available = departure.capacity - reserved_seats(db, departure.id, now())
    if data.travelers_count > available:
        raise HTTPException(409, f"Недостаточно свободных мест. Доступно: {max(available, 0)}.")
    if experience.currency != "KZT":
        raise HTTPException(409, "Перед продажей тур должен быть переведён в KZT.")
    selected = [service for service in experience.services if service.id in data.service_ids and service.is_active]
    if len(selected) != len(data.service_ids):
        raise HTTPException(422, "Выбранная услуга недоступна для этого тура.")
    subtotal = departure.price * data.travelers_count + sum((s.price * (data.travelers_count if s.per_person else 1) for s in selected), Decimal(0))
    if subtotal > Decimal("9999999999.99"):
        raise HTTPException(422, "Сумма заказа превышает допустимый денежный лимит. Уменьшите состав заказа.")
    discount = Decimal(0)
    promo = None
    if data.promo_code:
        promo = db.scalar(select(PromoCode).where(PromoCode.code == data.promo_code.upper().strip()).with_for_update())
        if not promo or not promo.is_active or not aware(promo.starts_at) <= now() < aware(promo.ends_at):
            raise HTTPException(409, "Промокод недействителен или срок его действия истёк.")
        if (promo.experience_id and promo.experience_id != experience.id) or (promo.category and promo.category != experience.category) or subtotal < promo.min_amount:
            raise HTTPException(409, "Промокод неприменим к выбранному заказу.")
        # A live reservation holds one redemption; an unpaid expiration/cancellation releases
        # it. A confirmed purchase consumes its use after cancellation/refund;
        # a late, compensated payment that never confirmed a trip does not.
        paid = select(PaymentAttempt.id).where(PaymentAttempt.booking_id == Booking.id, PaymentAttempt.status == "succeeded").exists()
        was_confirmed = select(BookingStatusHistory.id).where(
            BookingStatusHistory.booking_id == Booking.id, BookingStatusHistory.status == "confirmed").exists()
        active_use = or_(Booking.status.in_(("confirmed", "completed")),
                         and_(Booking.status == "pending", Booking.expires_at > now()),
                         and_(Booking.status == "cancelled", paid, was_confirmed))
        usages = select(func.count()).select_from(PromoRedemption).join(Booking).where(PromoRedemption.promo_id == promo.id, active_use)
        count = db.scalar(usages)
        user_count = db.scalar(usages.where(PromoRedemption.user_id == user.id))
        if count >= promo.usage_limit or user_count >= promo.per_user_limit:
            raise HTTPException(409, "Лимит применения промокода исчерпан.")
        discount = rounded(subtotal * promo.value / 100 if promo.kind == "percent" else promo.value)
        if subtotal - discount < Decimal(1):
            raise HTTPException(409, "Промокод оставляет сумму менее 1 ₸. Бесплатные заказы в демонстрационном платёжном сценарии не поддерживаются.")
    return departure, experience, selected, subtotal, discount, promo


def create_booking(db, user, data):
    departure, experience, selected, subtotal, discount, promo = quote_context(db, user, data)
    snapshot = booking_snapshot(experience)
    for language in ("ru", "en", "kk"):
        snapshot[language]["service_names"] = {service.id: localized(service, "name", language) for service in selected}
    booking = Booking(reference="SAP-" + secrets.token_hex(6).upper(), user_id=user.id, departure_id=departure.id,
                      travelers_count=data.travelers_count, subtotal_amount=rounded(subtotal), discount_amount=discount,
                      total_amount=rounded(subtotal-discount), currency="KZT", contact_name=data.contact_name,
                      contact_email=str(data.contact_email).casefold(), notes=data.notes, status="pending",
                      experience_snapshot=snapshot, start_date=departure.start_date, end_date=departure.end_date,
                      cancellation_policy=cancellation_policy(experience), expires_at=now() + timedelta(minutes=get_settings().reservation_minutes))
    db.add(booking)
    db.flush()
    names = [participant.name for participant in data.participants] or [data.contact_name] + [f"Участник {i+1}" for i in range(1, data.travelers_count)]
    for position, name in enumerate(names):
        db.add(BookingParticipant(booking_id=booking.id, position=position, name=name))
    db.add(BookingItem(booking_id=booking.id, kind="tour", name=experience.title, quantity=data.travelers_count,
                       unit_amount=departure.price, total_amount=departure.price * data.travelers_count, currency="KZT"))
    for service in selected:
        quantity = data.travelers_count if service.per_person else 1
        db.add(BookingItem(booking_id=booking.id, service_id=service.id, kind="service", name=service.name,
                           quantity=quantity, unit_amount=service.price, total_amount=service.price * quantity, currency="KZT"))
    if promo:
        db.add(PromoRedemption(promo_id=promo.id, booking_id=booking.id, user_id=user.id, discount_amount=discount))
    history(db, booking, user, "Места зарезервированы на время оплаты")
    emit(db, booking, "booking.created", "Места зарезервированы", f"Бронь {booking.reference} ожидает оплаты.", user)
    db.flush()
    return booking



def quote_booking(db, user, data, lang="ru"):
    from app.services.catalog_service import money
    departure, experience, selected, subtotal, discount, promo = quote_context(db, user, data)
    items = [{"kind": "tour", "name": localized(experience, "title", lang), "quantity": data.travelers_count,
              "unit_amount": money(departure.price), "total_amount": money(departure.price * data.travelers_count), "currency": "KZT"}]
    for service in selected:
        quantity = data.travelers_count if service.per_person else 1
        items.append({"kind": "service", "name": localized(service, "name", lang), "quantity": quantity, "unit_amount": money(service.price),
                      "total_amount": money(service.price * quantity), "currency": "KZT"})
    return {"subtotal_amount": money(subtotal), "discount_amount": money(discount), "total_amount": money(subtotal-discount),
            "currency": "KZT", "items": items, "cancellation_policy": cancellation_policy(experience, lang),
            "available_seats": departure.capacity - reserved_seats(db, departure.id, now()),
            "notice": {"ru": "Расчёт действителен на момент запроса. Цена и места будут проверены при создании бронирования.", "en": "This quote is valid at request time. Price and availability are checked again when booking.", "kk": "Есеп сұрау сәтіне жарамды. Баға мен орындар бронь жасау кезінде қайта тексеріледі."}[lang]}

def require_demo():
    if not get_settings().payment_demo_enabled:
        raise HTTPException(503, "Демонстрационный платёжный провайдер отключён.")


def luhn(number):
    if not number.isascii() or not number.isdigit() or not 13 <= len(number) <= 19:
        return False
    digits = list(map(int, number))
    for index in range(len(digits)-2, -1, -2):
        digits[index] = digits[index] * 2 - (9 if digits[index] > 4 else 0)
    return sum(digits) % 10 == 0


def validate_instrument(data):
    number = data.card_number.replace(" ", "").replace("-", "")
    if not luhn(number):
        raise HTTPException(422, "Некорректный номер тестовой карты или контрольная сумма.")
    instrument = next((item for item in TEST_INSTRUMENTS if item["card_number"] == number), None)
    if not instrument:
        raise HTTPException(422, "Разрешены только документированные тестовые карты. Не вводите реальные банковские данные.")
    current = today()
    if (data.expiry_year, data.expiry_month) < (current.year, current.month):
        raise HTTPException(422, "Срок действия тестовой карты истёк.")
    if len(data.cvc) != 3 or not data.cvc.isascii() or not data.cvc.isdigit():
        raise HTTPException(422, "CVC тестовой карты должен содержать 3 цифры.")
    return instrument


def fingerprint(booking_id, data):
    # Keyed digest enforces payload identity without persisting PAN, CVC, or a reversible
    # tiny CVC hash. The secret is never stored with the digest.
    payload = json.dumps({"booking_id": booking_id, **data.model_dump()}, sort_keys=True)
    return hmac.new(get_settings().jwt_secret.get_secret_value().encode(), payload.encode(), hashlib.sha256).hexdigest()


def payment_event(db, payment, status, reason=""):
    if payment.status == status and payment.id:
        return
    payment.status = status
    db.add(PaymentEvent(payment_id=payment.id, status=status, reason=reason))


def successful_payment(db, booking, payment, actor=None):
    if payment.status == "succeeded":
        return
    # Consuming a reserved promo must serialize with new reservations on
    # other departures, including when expiry passes before this commit.
    db.scalar(select(PromoCode).join(PromoRedemption).where(
        PromoRedemption.booking_id == booking.id).with_for_update(of=PromoCode))
    operation = provider.get_operation(db, payment.provider_operation_id)
    if operation.amount != booking.total_amount or operation.currency != booking.currency:
        raise HTTPException(409, "Параметры операции провайдера не совпадают с бронированием.")
    payment_event(db, payment, "succeeded", "Провайдер подтвердил оплату")
    expire_if_needed(db, booking)
    departure = db.get(Departure, booking.departure_id)
    if booking.status == "pending" and departure.status == "scheduled" and booking.start_date > today():
        # The booking's live reservation already counts towards this total.
        if reserved_seats(db, departure.id, now()) <= departure.capacity:
            booking.status = "confirmed"
            history(db, booking, reason="Подтверждено после успешной оплаты")
            emit(db, booking, "payment.succeeded", "Оплата получена", f"Бронирование {booking.reference} подтверждено.", actor)
            db.flush()
            return
    payment.error_code = "late_payment_refunded"
    if booking.status == "pending":
        booking.status = "expired"
        history(db, booking, reason="Резерв закрыт до получения оплаты")
    create_refund(db, booking, payment, payment.amount, "Компенсация: поздняя оплата после закрытия резерва", "late-"+payment.id)
    emit(db, booking, "payment.late", "Поздняя оплата", "Резерв уже закрыт. Создан полный компенсационный возврат.", actor)


def initiate_payment(db, user, booking_id, data, key):
    require_demo()
    if not key or not 8 <= len(key) <= 100:
        raise HTTPException(422, "Передайте Idempotency-Key длиной 8–100 символов.")
    booking = lock_booking(db, booking_id, user)
    digest = fingerprint(booking_id, data)
    existing = db.scalar(select(PaymentAttempt).where(PaymentAttempt.user_id == user.id, PaymentAttempt.idempotency_key == key))
    if existing:
        if existing.request_fingerprint != digest:
            raise HTTPException(409, "Этот ключ идемпотентности уже использован с другими параметрами.")
        return existing
    if expire_if_needed(db, booking):
        # Persist expiration even when returning a correct conflict.
        db.commit()
    if booking.status != "pending" or booking.currency != "KZT" or booking.start_date <= today():
        raise HTTPException(409, "Оплатить можно только действующую неоплаченную бронь в KZT.")
    unresolved = db.scalar(select(PaymentAttempt.id).where(PaymentAttempt.booking_id == booking.id,
                          PaymentAttempt.status.in_(("succeeded", "unknown", "requires_action", "created"))))
    if unresolved:
        raise HTTPException(409, "Уже существует успешная или незавершённая оплата. Проверьте её состояние.")
    instrument = validate_instrument(data)
    operation = provider.create_payment(db, booking.total_amount, booking.currency, instrument["scenario"])
    payment = PaymentAttempt(booking_id=booking.id, user_id=user.id, idempotency_key=key, request_fingerprint=digest,
                             provider_operation_id=operation.id, instrument_id=instrument["id"], masked_card="•••• " + instrument["card_number"][-4:],
                             status="created", amount=booking.total_amount, currency=booking.currency)
    db.add(payment)
    db.flush()
    db.add(PaymentEvent(payment_id=payment.id, status="created", reason="Создана демонстрационная попытка"))
    scenario = instrument["scenario"]
    if scenario == "success":
        successful_payment(db, booking, payment, user)
    elif scenario == "3ds":
        payment.action_expires_at = now() + timedelta(minutes=5)
        payment_event(db, payment, "requires_action", "Требуется демонстрационное подтверждение 3-D Secure")
    elif scenario.startswith("timeout"):
        payment.error_code = "outcome_unknown"
        payment_event(db, payment, "unknown", "Тайм-аут транспорта; повторное списание заблокировано до сверки")
        emit(db, booking, "payment.pending", "Результат оплаты неизвестен", "Выполните сверку состояния перед повторной попыткой.", user)
    else:
        payment.error_code = scenario
        payment_event(db, payment, "failed", scenario)
        emit(db, booking, "payment.failed", "Оплата отклонена", "Можно повторить оплату другой тестовой картой.", user)
    db.flush()
    return payment


def locked_payment(db, payment_id, user=None):
    payment = db.get(PaymentAttempt, payment_id)
    if not payment:
        raise HTTPException(404, "Попытка оплаты не найдена.")
    booking = lock_booking(db, payment.booking_id, user, manage=bool(user and user.role == "admin"))
    payment = db.scalar(select(PaymentAttempt).options(lazyload("*")).where(PaymentAttempt.id == payment_id).with_for_update().execution_options(populate_existing=True))
    return booking, payment


def confirm_payment(db, user, payment_id, outcome):
    require_demo()
    booking, payment = locked_payment(db, payment_id, user)
    if payment.status != "requires_action":
        return payment
    operation = provider.get_operation(db, payment.provider_operation_id)
    if aware(payment.action_expires_at) <= now():
        outcome = "expired"
    if outcome == "success":
        operation.status = "succeeded"
        successful_payment(db, booking, payment, user)
    else:
        operation.status = "failed"
        payment.error_code = {"failure": "authentication_failed", "expired": "authentication_expired", "cancelled": "authentication_cancelled"}[outcome]
        payment_event(db, payment, "cancelled" if outcome == "cancelled" else "failed", payment.error_code)
        emit(db, booking, "payment.failed", "Подтверждение не завершено", "Оплата не прошла. Разрешена новая попытка до истечения резерва.", user)
    db.flush()
    return payment


def reconcile_payment(db, user, payment_id):
    booking, payment = locked_payment(db, payment_id, user)
    if payment.status not in ("unknown", "created", "requires_action"):
        return payment
    operation = provider.get_operation(db, payment.provider_operation_id)
    if operation.status == "succeeded":
        payment.error_code = ""
        successful_payment(db, booking, payment, user)
    elif operation.status == "failed":
        payment.error_code = "bank_declined"
        payment_event(db, payment, "failed", "Сверка установила отказ провайдера")
        emit(db, booking, "payment.failed", "Оплата отклонена", "Сверка подтвердила отказ. Можно повторить оплату.", user)
    elif payment.status == "requires_action" and aware(payment.action_expires_at) <= now():
        operation.status = "failed"
        payment.error_code = "authentication_expired"
        payment_event(db, payment, "failed", payment.error_code)
    db.flush()
    return payment


def create_refund(db, booking, payment, amount, reason, key, actor=None, scenario="success"):
    existing = db.scalar(select(Refund).where(Refund.idempotency_key == key))
    amount = rounded(amount)
    if existing:
        operation = provider.get_operation(db, existing.provider_operation_id)
        if existing.booking_id != booking.id or existing.amount != amount or existing.reason != reason or operation.scenario != scenario:
            raise HTTPException(409, "Ключ возврата уже использован с другими параметрами.")
        return existing
    if payment.status != "succeeded" or payment.currency != booking.currency:
        raise HTTPException(409, "Нет подходящей успешной оплаты для возврата.")
    committed = db.scalar(select(func.coalesce(func.sum(Refund.amount), 0)).where(Refund.payment_id == payment.id, Refund.status.in_(("pending", "succeeded"))))
    if amount <= 0 or amount + committed > payment.amount:
        raise HTTPException(409, "Сумма возвратов превышает доступную оплаченную сумму.")
    operation = provider.create_refund(db, amount, payment.currency, scenario)
    refund = Refund(booking_id=booking.id, payment_id=payment.id, provider_operation_id=operation.id, idempotency_key=key,
                    amount=amount, currency=payment.currency, reason=reason, status="pending", actor_id=actor.id if actor else None)
    db.add(refund)
    db.flush()
    db.add(RefundEvent(refund_id=refund.id, status="pending", reason=reason))
    apply_refund_state(db, booking, refund, operation.status)
    db.flush()
    return refund


def apply_refund_state(db, booking, refund, status):
    if refund.status == "succeeded" or refund.status == status:
        return
    refund.status = status
    db.add(RefundEvent(refund_id=refund.id, status=status, reason="Результат демонстрационного провайдера"))
    emit(db, booking, "refund." + status, "Возврат выполнен" if status == "succeeded" else "Возврат требует повторной попытки",
         f"Возврат {refund.amount} {refund.currency}: {status}.", refund.actor_id)


def cancel_booking(db, user, booking_id, reason="Отмена путешественником", manage=False, force_full=False):
    booking = lock_booking(db, booking_id, user, manage)
    expire_if_needed(db, booking)
    if booking.status in ("cancelled", "expired"):
        return booking
    if booking.status == "completed" or (not manage and booking.start_date <= today()):
        raise HTTPException(409, "Начавшийся или завершённый тур нельзя отменить самостоятельно.")
    booking.status = "cancelled"
    history(db, booking, user, reason)
    payment = db.scalar(select(PaymentAttempt).where(PaymentAttempt.booking_id == booking.id, PaymentAttempt.status == "succeeded"))
    if payment:
        days_before = (booking.start_date - today()).days
        rules = booking.cancellation_policy.get("rules", cancellation_policy()["rules"])
        percent = 100 if force_full else next((rule["refund_percent"] for rule in sorted(rules, key=lambda rule: rule["days_before"], reverse=True) if days_before >= rule["days_before"]), 50)
        amount = rounded(payment.amount * Decimal(percent) / 100)
        committed = db.scalar(select(func.coalesce(func.sum(Refund.amount), 0)).where(Refund.payment_id == payment.id, Refund.status.in_(("pending", "succeeded"))))
        amount = max(Decimal(0), amount-committed)
        if amount > 0:
            create_refund(db, booking, payment, amount, reason, "cancel-"+booking.id, user)
    emit(db, booking, "booking.cancelled", "Бронирование отменено", f"Бронь {booking.reference} отменена. Места освобождены.", user)
    db.flush()
    return booking


def complete_booking(db, user, booking_id):
    booking = lock_booking(db, booking_id, user, manage=True)
    if booking.status == "completed":
        return booking
    if booking.status != "confirmed" or booking.end_date >= today():
        raise HTTPException(409, "Завершить можно подтверждённый тур только после даты окончания.")
    booking.status = "completed"
    history(db, booking, user, "Поездка завершена")
    emit(db, booking, "booking.completed", "Поездка завершена", "Спасибо за путешествие. Теперь можно оставить отзыв.", user)
    db.flush()
    return booking


def retry_refund(db, user, refund_id):
    refund = db.get(Refund, refund_id)
    if not refund:
        raise HTTPException(404, "Возврат не найден.")
    booking = lock_booking(db, refund.booking_id, user, manage=user.role in ("admin", "vendor"))
    refund = db.scalar(select(Refund).where(Refund.id == refund_id).with_for_update().execution_options(populate_existing=True))
    if refund.status == "succeeded":
        return refund
    if refund.status == "failed":
        committed = db.scalar(select(func.coalesce(func.sum(Refund.amount), 0)).where(Refund.payment_id == refund.payment_id, Refund.status.in_(("pending", "succeeded"))))
        payment = db.get(PaymentAttempt, refund.payment_id)
        if committed + refund.amount > payment.amount:
            raise HTTPException(409, "Доступная сумма уже зарезервирована другим возвратом.")
    operation = provider.get_operation(db, refund.provider_operation_id)
    operation.status = "succeeded"
    apply_refund_state(db, booking, refund, "succeeded")
    db.flush()
    return refund


def process_pending(db):
    """Bounded durable worker sweep; safe with multiple workers via common row locks."""
    expired = reconciled = 0
    ids = list(db.scalars(select(Booking.id).where(Booking.status == "pending", Booking.expires_at <= now()).limit(100)))
    for booking_id in ids:
        booking = lock_booking(db, booking_id)
        expired += int(expire_if_needed(db, booking))
        db.commit()
    ids = list(db.scalars(select(PaymentAttempt.id).where(PaymentAttempt.status.in_(("unknown", "requires_action"))).limit(100)))
    for payment_id in ids:
        reconcile_payment(db, None, payment_id)
        db.commit()
        reconciled += 1
    ids = list(db.scalars(select(Refund.id).where(Refund.status == "pending").limit(100)))
    for refund_id in ids:
        refund = db.get(Refund, refund_id)
        booking = lock_booking(db, refund.booking_id)
        refund = db.scalar(select(Refund).where(Refund.id == refund_id).with_for_update().execution_options(populate_existing=True))
        operation = provider.get_operation(db, refund.provider_operation_id)
        if operation.scenario == "processing":
            operation.status = "succeeded"
        apply_refund_state(db, booking, refund, operation.status)
        db.commit()
    return {"expired": expired, "reconciled": reconciled}
