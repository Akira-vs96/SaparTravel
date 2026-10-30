"""Owned resources, verified-trip reviews and administrative operations."""
from zoneinfo import ZoneInfo
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, Response
from pydantic import Field, StringConstraints, field_validator, model_validator
from typing import Annotated
from sqlalchemy import func, or_, select, update
from sqlalchemy.exc import IntegrityError

from app.api.schemas import InputModel, Language, Name, Role
from app.core.security import Admin, CurrentUser, DbSession, Manager
from app.domain.engagement import AuditLog, Notification, PasswordReset, Review, SavedSearch, SupportMessage, SupportTicket, UserAccessBoundary
from app.domain.models import Booking, CategoryRecord, Departure, Experience, User, utc_now
from app.services.catalog_service import user_data
from app.services.engagement_service import audit, emit_event, refresh_review_rating
from app.services import support_service

router = APIRouter()
TextBody = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=5000)]


class SavedSearchInput(InputModel):
    name: Name
    filters: dict[str, str | int | float | bool | None] = Field(max_length=20)

    @field_validator("filters")
    @classmethod
    def valid_filters(cls, values):
        allowed = {"q", "destination", "continent", "category", "min_price", "max_price", "duration_min", "duration_max", "travelers_count", "travelers", "participants", "page", "page_size", "start_date", "end_date", "date_from", "date_to", "sort", "lang"}
        if set(values) - allowed:
            raise ValueError("Неизвестный параметр поиска")
        for key, value in values.items():
            if isinstance(value, str) and len(value) > 200:
                raise ValueError("Значение параметра слишком длинное")
            if isinstance(value, float) and (value != value or abs(value) == float("inf")):
                raise ValueError("Число должно быть конечным")
        return values


class TicketInput(InputModel):
    subject: Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=180)]
    body: TextBody
    booking_id: str | None = Field(default=None, min_length=1, max_length=36)
    priority: Literal["P1", "P2", "P3"] = "P3"


class MessageInput(InputModel):
    body: TextBody
    acknowledge: bool = False


class TicketPriorityInput(InputModel):
    priority: Literal["P1", "P2", "P3"]


class TicketStatusInput(InputModel):
    status: Literal["open", "in_progress", "resolved", "closed"]


class ReviewInput(InputModel):
    booking_id: str = Field(min_length=1, max_length=36)
    rating: int = Field(ge=1, le=5, strict=True)
    title: Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=180)]
    text: Annotated[str, StringConstraints(strip_whitespace=True, min_length=10, max_length=5000)]


class ReviewModerationInput(InputModel):
    status: Literal["pending", "approved", "rejected"]


class UserPatch(InputModel):
    role: Role | None = None
    is_active: bool | None = None
    name: Name | None = None

    @model_validator(mode="after")
    def valid_patch(self):
        if not self.model_fields_set or any(getattr(self, key) is None for key in self.model_fields_set):
            raise ValueError("Передайте изменяемые поля без null")
        return self


def columns(item, names):
    return {name: (getattr(item, name).isoformat() if hasattr(getattr(item, name), "isoformat") else getattr(item, name)) for name in names}


def notification_data(item, lang="ru"):
    result = columns(item, ("id", "event", "booking_id", "is_read", "created_at", "title", "body", "title_en", "title_kk", "body_en", "body_kk"))
    if lang != "ru":
        result["title"] = getattr(item, "title_" + lang) or item.title
        result["body"] = getattr(item, "body_" + lang) or item.body
    return result


@router.get("/notifications")
def notifications(user: CurrentUser, db: DbSession, lang: Language = "ru", limit: int = Query(default=50, ge=1, le=100), offset: int = Query(default=0, ge=0, le=1000000)):
    query = select(Notification).where(Notification.user_id == user.id)
    items = db.scalars(query.order_by(Notification.created_at.desc(), Notification.id).offset(offset).limit(limit)).all()
    unread = db.scalar(select(func.count()).select_from(Notification).where(Notification.user_id == user.id, Notification.is_read.is_(False)))
    return {"items": [notification_data(item, lang) for item in items], "unread_count": unread}


@router.post("/notifications/read-all", status_code=204)
def read_all_notifications(user: CurrentUser, db: DbSession):
    db.execute(update(Notification).where(Notification.user_id == user.id, Notification.is_read.is_(False)).values(is_read=True))
    db.commit()
    return Response(status_code=204)


@router.post("/notifications/{notification_id}/read")
def read_notification(notification_id: str, user: CurrentUser, db: DbSession, lang: Language = "ru"):
    item = db.scalar(select(Notification).where(Notification.id == notification_id, Notification.user_id == user.id))
    if not item:
        raise HTTPException(404, "Уведомление не найдено.")
    item.is_read = True
    db.commit()
    return notification_data(item, lang)


def search_data(item):
    return columns(item, ("id", "name", "filters", "created_at"))


@router.get("/saved-searches")
def saved_searches(user: CurrentUser, db: DbSession):
    items = db.scalars(select(SavedSearch).where(SavedSearch.user_id == user.id).order_by(SavedSearch.created_at.desc()).limit(100))
    return {"items": [search_data(item) for item in items]}


@router.post("/saved-searches", status_code=201)
def save_search(data: SavedSearchInput, user: CurrentUser, db: DbSession):
    # Serialize the per-account limit so concurrent submissions cannot bypass it.
    db.scalar(select(User.id).where(User.id == user.id).with_for_update())
    count = db.scalar(select(func.count()).select_from(SavedSearch).where(SavedSearch.user_id == user.id))
    if count >= 100:
        raise HTTPException(409, "Можно сохранить не более 100 поисков.")
    item = SavedSearch(user_id=user.id, name=data.name, filters=data.filters)
    db.add(item)
    db.commit()
    return search_data(item)


@router.delete("/saved-searches/{search_id}", status_code=204)
def delete_search(search_id: str, user: CurrentUser, db: DbSession):
    item = db.scalar(select(SavedSearch).where(SavedSearch.id == search_id, SavedSearch.user_id == user.id))
    if not item:
        raise HTTPException(404, "Сохранённый поиск не найден.")
    db.delete(item)
    db.commit()
    return Response(status_code=204)


def ticket_query(user):
    query = select(SupportTicket)
    if user.role == "admin":
        return query
    if user.role == "vendor":
        return query.where(or_(SupportTicket.user_id == user.id, SupportTicket.vendor_id == user.id))
    return query.where(SupportTicket.user_id == user.id)


def find_ticket(db, ticket_id, user, lock=False):
    query = ticket_query(user).where(SupportTicket.id == ticket_id)
    if lock:
        query = query.with_for_update().execution_options(populate_existing=True)
    item = db.scalar(query)
    if not item:
        raise HTTPException(404, "Обращение не найдено.")
    return item


def ticket_data(item):
    result = columns(item, ("id", "user_id", "booking_id", "subject", "status", "created_at", "updated_at",
                            "priority", "response_due_at", "first_response_at", "first_response_by"))
    result["response_working_minutes"] = round(item.response_working_seconds / 60, 4) if item.response_working_seconds is not None else None
    result["response_overdue"] = bool(item.response_due_at and item.first_response_at is None
                                      and support_service.aware(item.response_due_at) < utc_now())
    result["can_acknowledge"] = item.first_response_at is None
    return result


def message_data(item):
    return {**columns(item, ("id", "author_id", "author_role", "body", "created_at")), "author_name": item.author.name}


def ticket_alert(db, ticket, actor, event):
    # Deliver to the customer when staff replies, otherwise to the assigned
    # supplier and active administrators. Do not expose other customers' tickets.
    recipients = {ticket.user_id} if actor.id != ticket.user_id else set(db.scalars(select(User.id).where(User.role == "admin", User.is_active.is_(True))))
    if actor.id == ticket.user_id and ticket.vendor_id:
        recipients.add(ticket.vendor_id)
    recipients.discard(actor.id)
    for recipient in recipients:
        emit_event(db, recipient, event, "Обновление обращения", f"Обращение «{ticket.subject}» обновлено.", ticket.booking_id,
                   title_en="Support request updated", body_en=f"Your request “{ticket.subject}” has an update.",
                   title_kk="Қолдау өтініші жаңартылды", body_kk=f"«{ticket.subject}» өтініші жаңартылды.")


@router.get("/support/tickets")
def tickets(user: CurrentUser, db: DbSession, limit: int = Query(default=50, ge=1, le=100), offset: int = Query(default=0, ge=0, le=1000000), status: Literal["open", "in_progress", "resolved", "closed"] | None = None):
    query = ticket_query(user)
    if status:
        query = query.where(SupportTicket.status == status)
    items = db.scalars(query.order_by(SupportTicket.updated_at.desc(), SupportTicket.id).offset(offset).limit(limit))
    return {"items": [ticket_data(item) for item in items]}


@router.post("/support/tickets", status_code=201)
def create_ticket(data: TicketInput, user: CurrentUser, db: DbSession):
    vendor_id = None
    if data.booking_id:
        booking = db.scalar(select(Booking).where(Booking.id == data.booking_id, Booking.user_id == user.id))
        if not booking:
            raise HTTPException(404, "Бронирование не найдено.")
        vendor_id = booking.departure.experience.vendor_id
    item = SupportTicket(user_id=user.id, vendor_id=vendor_id, booking_id=data.booking_id,
                         subject=data.subject.strip(), priority=data.priority, created_at=utc_now())
    try:
        support_service.set_deadline(item)
    except (ValueError, OSError, KeyError, TypeError):
        raise HTTPException(503, "Календарь поддержки временно недоступен.") from None
    db.add(item)
    db.flush()
    db.add(SupportMessage(ticket_id=item.id, author_id=user.id, author_role=user.role, body=data.body))
    ticket_alert(db, item, user, "support.created")
    audit(db, user.id, "support.created", "support_ticket", item.id)
    db.commit()
    return ticket_data(item)


@router.get("/support/tickets/{ticket_id}")
def ticket_detail(ticket_id: str, user: CurrentUser, db: DbSession):
    item = find_ticket(db, ticket_id, user)
    count = db.scalar(select(func.count()).select_from(SupportMessage).where(SupportMessage.ticket_id == item.id))
    messages = list(db.scalars(select(SupportMessage).where(SupportMessage.ticket_id == item.id)
                              .order_by(SupportMessage.created_at.desc(), SupportMessage.id.desc()).limit(100)))
    return {**ticket_data(item), "messages": [message_data(message) for message in reversed(messages)],
            "messages_total": count, "has_more_messages": count > len(messages)}


@router.get("/support/tickets/{ticket_id}/messages")
def ticket_messages(ticket_id: str, user: CurrentUser, db: DbSession,
                    limit: int = Query(default=100, ge=1, le=100), offset: int = Query(default=0, ge=0, le=1000000)):
    item = find_ticket(db, ticket_id, user)
    count = db.scalar(select(func.count()).select_from(SupportMessage).where(SupportMessage.ticket_id == item.id))
    messages = db.scalars(select(SupportMessage).where(SupportMessage.ticket_id == item.id)
                         .order_by(SupportMessage.created_at, SupportMessage.id).offset(offset).limit(limit))
    return {"items": [message_data(message) for message in messages], "total": count, "offset": offset, "limit": limit}


@router.post("/support/tickets/{ticket_id}/messages", status_code=201)
def add_message(ticket_id: str, data: MessageInput, user: CurrentUser, db: DbSession):
    item = find_ticket(db, ticket_id, user, lock=True)
    if item.status == "closed":
        raise HTTPException(409, "Сначала откройте закрытое обращение.")
    if data.acknowledge:
        staff = user.role == "admin" or (user.role == "vendor" and item.vendor_id == user.id)
        if not staff or item.user_id == user.id:
            raise HTTPException(403, "Реакцию фиксирует ответственный сотрудник поддержки.")
        if len(data.body.strip()) < 20:
            raise HTTPException(422, "Сообщите принятие обращения и следующий шаг: не менее 20 символов.")
        try:
            support_service.acknowledge(item, user)
        except ValueError:
            raise HTTPException(503, "Календарь поддержки не покрывает время реакции.") from None
        audit(db, user.id, "support.acknowledged", "support_ticket", item.id)
    message = SupportMessage(ticket_id=item.id, author_id=user.id, author_role=user.role, body=data.body)
    item.updated_at = utc_now()
    if item.status == "resolved" and item.user_id == user.id:
        item.status = "open"
    db.add(message)
    ticket_alert(db, item, user, "support.message")
    audit(db, user.id, "support.message", "support_ticket", item.id)
    db.commit()
    return message_data(message)


@router.patch("/support/tickets/{ticket_id}/priority")
def ticket_priority(ticket_id: str, data: TicketPriorityInput, user: Manager, db: DbSession):
    item = find_ticket(db, ticket_id, user, lock=True)
    if item.user_id == user.id or (user.role != "admin" and item.vendor_id != user.id):
        raise HTTPException(403, "Приоритет проверяет ответственный сотрудник.")
    if item.first_response_at is not None:
        raise HTTPException(409, "Приоритет первой реакции уже зафиксирован.")
    previous = item.priority
    if item.response_calendar:
        proposed = support_service.response_deadline(item.created_at, data.priority, item.response_calendar)
        if (item.response_due_at and support_service.aware(item.response_due_at) <= utc_now()
                and proposed > support_service.aware(item.response_due_at)):
            raise HTTPException(409, "Нельзя переносить уже нарушенный срок первой реакции.")
    item.priority = data.priority
    if item.response_calendar:
        support_service.set_deadline(item, item.response_calendar)
    audit(db, user.id, "support.priority", "support_ticket", item.id, {"from": previous, "to": data.priority})
    db.commit()
    return ticket_data(item)


@router.get("/manage/support-metrics")
def support_metrics(user: Manager, db: DbSession, month: str = Query(pattern=r"^\d{4}-\d{2}$")):
    try:
        start, end = support_service.month_window(month)
    except ValueError:
        raise HTTPException(422, "Укажите существующий месяц YYYY-MM.") from None
    query = select(SupportTicket).where(or_(
        (SupportTicket.response_due_at >= start) & (SupportTicket.response_due_at < end),
        (SupportTicket.response_due_at.is_(None)) & (SupportTicket.created_at >= start) & (SupportTicket.created_at < end)))
    if user.role != "admin":
        query = query.where(SupportTicket.vendor_id == user.id, SupportTicket.user_id != user.id)
    return support_service.response_report(db.scalars(query), month)


@router.get("/manage/support-metrics/evidence")
def support_metric_evidence(user: Manager, db: DbSession, month: str = Query(pattern=r"^\d{4}-\d{2}$")):
    try:
        start, end = support_service.month_window(month)
    except ValueError:
        raise HTTPException(422, "Укажите существующий месяц YYYY-MM.") from None
    query = select(SupportTicket).where(SupportTicket.response_due_at >= start, SupportTicket.response_due_at < end)
    if user.role != "admin":
        query = query.where(SupportTicket.vendor_id == user.id, SupportTicket.user_id != user.id)
    return {"month": month, "items": [{**columns(item, ("id", "priority", "created_at", "response_due_at", "first_response_at")),
                                       "response_working_seconds": item.response_working_seconds,
                                       "calendar_id": (item.response_calendar or {}).get("id")}
                                      for item in db.scalars(query.order_by(SupportTicket.response_due_at))]}


@router.patch("/support/tickets/{ticket_id}/status")
def update_ticket_status(ticket_id: str, data: TicketStatusInput, user: CurrentUser, db: DbSession):
    item = find_ticket(db, ticket_id, user, lock=True)
    staff = user.role == "admin" or (user.role == "vendor" and item.vendor_id == user.id and item.user_id != user.id)
    if not staff and data.status not in {"open", "closed"}:
        raise HTTPException(403, "Этот статус может установить только сотрудник поддержки.")
    if item.status != data.status:
        item.status = data.status
        item.updated_at = utc_now()
        ticket_alert(db, item, user, "support.status")
        audit(db, user.id, "support.status", "support_ticket", item.id, {"status": data.status})
        db.commit()
    return ticket_data(item)


def review_data(item, private=False):
    result = {**columns(item, ("id", "rating", "title", "text", "created_at")),
              "author_name": item.author.name, "verified_trip": True}
    if private:
        result.update(columns(item, ("booking_id", "experience_id", "status", "moderated_at")))
    return result


@router.get("/experiences/{experience_id}/reviews")
def public_reviews(experience_id: str, db: DbSession, limit: int = Query(default=30, ge=1, le=100), offset: int = Query(default=0, ge=0, le=1000000)):
    if not db.scalar(select(Experience.id).where(Experience.id == experience_id, Experience.is_published.is_(True))):
        raise HTTPException(404, "Тур не найден.")
    base = select(Review).where(Review.experience_id == experience_id, Review.status == "approved")
    items = db.scalars(base.order_by(Review.created_at.desc(), Review.id).offset(offset).limit(limit))
    rating, count = db.execute(select(func.avg(Review.rating), func.count()).where(Review.experience_id == experience_id, Review.status == "approved")).one()
    return {"items": [review_data(item) for item in items], "rating": round(float(rating or 0), 1), "review_count": count}


@router.get("/reviews/mine")
def own_reviews(user: CurrentUser, db: DbSession, limit: int = Query(default=100, ge=1, le=100), offset: int = Query(default=0, ge=0, le=1000000)):
    rows = db.scalars(select(Review).where(Review.user_id == user.id).order_by(Review.created_at.desc(), Review.id).offset(offset).limit(limit))
    return {"items": [review_data(item, True) for item in rows]}


@router.post("/reviews", status_code=201)
def create_review(data: ReviewInput, user: CurrentUser, db: DbSession):
    booking = db.scalar(select(Booking).where(Booking.id == data.booking_id, Booking.user_id == user.id))
    if not booking:
        raise HTTPException(404, "Бронирование не найдено.")
    if booking.status != "completed" or booking.end_date >= utc_now().astimezone(ZoneInfo("Asia/Almaty")).date():
        raise HTTPException(409, "Отзыв доступен только после завершённой поездки.")
    if db.scalar(select(Review.id).where(Review.booking_id == booking.id)):
        raise HTTPException(409, "Для этого бронирования уже оставлен отзыв.")
    item = Review(booking_id=booking.id, user_id=user.id, experience_id=booking.departure.experience_id,
                  rating=data.rating, title=data.title.strip(), text=data.text.strip())
    db.add(item)
    try:
        db.flush()
        audit(db, user.id, "review.created", "review", item.id)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Для этого бронирования уже оставлен отзыв.") from None
    return review_data(item, True)


@router.get("/manage/reviews")
def manage_reviews(user: Manager, db: DbSession, status: Literal["pending", "approved", "rejected"] | None = None, limit: int = Query(default=50, ge=1, le=100), offset: int = Query(default=0, ge=0, le=1000000)):
    query = select(Review).join(Experience, Experience.id == Review.experience_id)
    if user.role != "admin":
        query = query.where(Experience.vendor_id == user.id)
    if status:
        query = query.where(Review.status == status)
    items = db.scalars(query.order_by(Review.created_at.desc(), Review.id).offset(offset).limit(limit))
    return {"items": [review_data(item, True) for item in items]}


@router.patch("/admin/reviews/{review_id}")
def moderate_review(review_id: str, data: ReviewModerationInput, user: Admin, db: DbSession):
    # Lock the catalogue row first to serialize rating rebuilds for the same tour.
    existing = db.get(Review, review_id)
    if not existing:
        raise HTTPException(404, "Отзыв не найден.")
    db.scalar(select(Experience.id).where(Experience.id == existing.experience_id).with_for_update())
    item = db.scalar(select(Review).where(Review.id == review_id).with_for_update(of=Review).execution_options(populate_existing=True))
    item.status = data.status
    item.moderated_by = user.id
    item.moderated_at = utc_now()
    refresh_review_rating(db, item.experience_id)
    audit(db, user.id, "review.moderated", "review", item.id, {"status": data.status})
    db.commit()
    return review_data(item, True)


@router.get("/admin/users")
def users(user: Admin, db: DbSession, role: Role | None = None, limit: int = Query(default=100, ge=1, le=100), offset: int = Query(default=0, ge=0, le=1000000)):
    query = select(User)
    if role:
        query = query.where(User.role == role)
    rows = db.scalars(query.order_by(User.created_at.desc(), User.id).offset(offset).limit(limit))
    return {"items": [{**user_data(item), "is_active": item.is_active, "created_at": item.created_at.isoformat()} for item in rows]}


@router.patch("/admin/users/{user_id}")
def update_user(user_id: str, data: UserPatch, user: Admin, db: DbSession):
    # A PostgreSQL advisory transaction lock serializes changes to the active
    # administrator set, including promotions, so the final admin is preserved.
    if db.bind.dialect.name == "postgresql":
        from sqlalchemy import text
        db.execute(text("SELECT pg_advisory_xact_lock(732918145)"))
    admins = db.scalars(select(User).where(User.role == "admin", User.is_active.is_(True)).order_by(User.id).with_for_update()).all()
    db.refresh(user)
    if user.role != "admin" or not user.is_active:
        raise HTTPException(403, "Доступно только администратору.")
    target = db.get(User, user_id, populate_existing=True, with_for_update=True)
    if not target:
        raise HTTPException(404, "Пользователь не найден.")
    values = data.model_dump(exclude_unset=True)
    removing_admin = target.role == "admin" and target.is_active and (values.get("role", target.role) != "admin" or not values.get("is_active", target.is_active))
    if removing_admin and len(admins) <= 1:
        raise HTTPException(409, "Нельзя изменить или заблокировать последнего активного администратора.")
    if values.get("is_active") is False:
        db.execute(update(PasswordReset).where(PasswordReset.user_id == target.id, PasswordReset.used_at.is_(None)).values(used_at=utc_now()))
        boundary = db.get(UserAccessBoundary, target.id)
        if boundary:
            boundary.invalidated_at = utc_now()
        else:
            db.add(UserAccessBoundary(user_id=target.id, invalidated_at=utc_now()))
    for key, value in values.items():
        setattr(target, key, value)
    audit(db, user.id, "user.updated", "user", target.id, {key: value for key, value in values.items() if key != "name"})
    db.commit()
    return {**user_data(target), "is_active": target.is_active}


@router.get("/admin/vendors")
def vendors(user: Admin, db: DbSession, limit: int = Query(default=100, ge=1, le=100), offset: int = Query(default=0, ge=0, le=1000000)):
    counts = dict(db.execute(select(Experience.vendor_id, func.count()).group_by(Experience.vendor_id)).all())
    rows = db.scalars(select(User).where(User.role == "vendor").order_by(User.name, User.id).offset(offset).limit(limit))
    return {"items": [{**user_data(item), "is_active": item.is_active, "tour_count": counts.get(item.id, 0)} for item in rows]}


@router.get("/admin/audit")
def audit_log(user: Admin, db: DbSession, limit: int = Query(default=50, ge=1, le=100), offset: int = Query(default=0, ge=0, le=1000000), action: str | None = Query(default=None, max_length=100)):
    query = select(AuditLog)
    if action:
        query = query.where(AuditLog.action == action)
    rows = db.scalars(query.order_by(AuditLog.created_at.desc(), AuditLog.id).offset(offset).limit(limit))
    return {"items": [columns(item, ("id", "actor_id", "action", "resource_type", "resource_id", "details", "created_at")) for item in rows]}


class CategoryInput(InputModel):
    code: str = Field(min_length=2, max_length=30, pattern=r"^[A-Za-z][A-Za-z0-9_-]+$")
    name_ru: Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=100)]
    name_en: Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=100)]
    name_kk: Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=100)]


class CategoryPatch(InputModel):
    name_ru: Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=100)] | None = None
    name_en: Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=100)] | None = None
    name_kk: Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=100)] | None = None

    @model_validator(mode="after")
    def no_null(self):
        if not self.model_fields_set or any(getattr(self, key) is None for key in self.model_fields_set):
            raise ValueError("Передайте изменяемые поля без null")
        return self


def category_data(item, lang="ru", count=0):
    return {"code": item.code, "name": getattr(item, "name_" + lang),
            "name_ru": item.name_ru, "name_en": item.name_en, "name_kk": item.name_kk, "tour_count": count}


@router.get("/categories")
def categories(db: DbSession, lang: Language = "ru", limit: int = Query(default=100, ge=1, le=100), offset: int = Query(default=0, ge=0, le=1000000)):
    counts = dict(db.execute(select(Experience.category, func.count()).where(
        Experience.is_published.is_(True), Experience.is_monitoring.is_(False)).group_by(Experience.category)).all())
    rows = db.scalars(select(CategoryRecord).order_by(CategoryRecord.code).offset(offset).limit(limit))
    return {"items": [category_data(item, lang, counts.get(item.code, 0)) for item in rows]}


@router.post("/admin/categories", status_code=201)
def create_category(data: CategoryInput, user: Admin, db: DbSession):
    if db.get(CategoryRecord, data.code):
        raise HTTPException(409, "Категория с таким кодом уже существует.")
    item = CategoryRecord(**data.model_dump())
    db.add(item)
    audit(db, user.id, "category.created", "category", item.code)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Категория с таким кодом уже существует.") from None
    return category_data(item)


@router.patch("/admin/categories/{code}")
def update_category(code: str, data: CategoryPatch, user: Admin, db: DbSession):
    item = db.get(CategoryRecord, code, with_for_update=True)
    if not item:
        raise HTTPException(404, "Категория не найдена.")
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(item, key, value)
    audit(db, user.id, "category.updated", "category", item.code)
    db.commit()
    return category_data(item)


@router.delete("/admin/categories/{code}", status_code=204)
def delete_category(code: str, user: Admin, db: DbSession):
    item = db.get(CategoryRecord, code, with_for_update=True)
    if not item:
        raise HTTPException(404, "Категория не найдена.")
    if db.scalar(select(Experience.id).where(Experience.category == code).limit(1)):
        raise HTTPException(409, "Категория используется турами и не может быть удалена.")
    db.delete(item)
    audit(db, user.id, "category.deleted", "category", code)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Категория используется турами и не может быть удалена.") from None
    return Response(status_code=204)
