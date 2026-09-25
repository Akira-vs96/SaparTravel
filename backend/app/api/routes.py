from datetime import date, timedelta
from math import ceil
import re
import secrets
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import cast, func, or_, select, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import lazyload

from app.api.schemas import (
    BookingInput, BookingStatusInput, Category, Continent, DepartureInput, DestinationInput, DestinationPatch, ExperienceInput,
    ExperiencePatch, Language, LoginInput, ProfileInput, RegisterInput, RoleInput,
)
from app.core.security import Admin, CurrentUser, DbSession, DUMMY_HASH, Manager, check_auth_rate, password_hash, token_for
from app.domain.models import Booking, BookingStatusHistory, Departure, Destination, Experience, Favorite, User
from app.services.catalog_service import (
    booking_data, booking_snapshot, departure_data, experience_data, experience_detail,
    localized, reserved_seats, user_data,
)

router = APIRouter()


def missing(message: str = "Запись не найдена."):
    raise HTTPException(404, message)


def auth_response(user: User) -> dict:
    return {"access_token": token_for(user), "token_type": "bearer", "user": user_data(user)}


@router.get("/health")
def health(db: DbSession) -> dict:
    try:
        db.execute(text("SELECT 1"))
    except SQLAlchemyError:
        raise HTTPException(503, "База данных временно недоступна.") from None
    return {"status": "ok", "service": "sapartravel-api", "database": "ok"}


@router.post("/auth/register", status_code=201, dependencies=[Depends(check_auth_rate)])
def register(data: RegisterInput, db: DbSession):
    email = str(data.email).casefold()
    if db.scalar(select(User.id).where(User.email == email)):
        raise HTTPException(409, "Аккаунт с таким адресом уже существует.")
    user = User(name=data.name, email=email, password_hash=password_hash.hash(data.password), role="traveler")
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Аккаунт с таким адресом уже существует.") from None
    return auth_response(user)


@router.post("/auth/login", dependencies=[Depends(check_auth_rate)])
def login(data: LoginInput, db: DbSession):
    user = db.scalar(select(User).where(User.email == str(data.email).casefold()))
    valid = password_hash.verify(data.password, user.password_hash if user else DUMMY_HASH)
    if not user or not valid or not user.is_active:
        raise HTTPException(401, "Неверный адрес электронной почты или пароль.", headers={"WWW-Authenticate": "Bearer"})
    return auth_response(user)


@router.get("/auth/me")
def me(user: CurrentUser):
    return user_data(user)


@router.patch("/auth/me")
def update_me(data: ProfileInput, user: CurrentUser, db: DbSession):
    user.name = data.name
    db.commit()
    return user_data(user)


@router.get("/destinations")
def destinations(db: DbSession, lang: Language = "ru"):
    counts = dict(db.execute(select(Experience.destination_id, func.count()).where(
        Experience.is_published.is_(True),
    ).group_by(Experience.destination_id)).all())
    items = []
    for item in db.scalars(select(Destination).order_by(Destination.slug)):
        items.append({
            "id": item.id, "slug": item.slug, "name": localized(item, "name", lang),
            "country": localized(item, "country", lang), "continent": item.continent,
            "image_url": item.image_url, "description": localized(item, "description", lang),
            "tour_count": counts.get(item.id, 0),
        })
    return {"items": items}


@router.get("/experiences")
def experiences(
    db: DbSession,
    q: str | None = Query(default=None, max_length=100),
    destination: str | None = Query(default=None, max_length=100),
    continent: Continent | None = None,
    category: Category | None = None,
    min_price: float | None = Query(default=None, ge=0, le=1000000, allow_inf_nan=False),
    max_price: float | None = Query(default=None, ge=0, le=1000000, allow_inf_nan=False),
    duration_max: int | None = Query(default=None, ge=1, le=90),
    sort: Literal["recommended", "price_asc", "price_desc", "rating"] = "recommended",
    page: int = Query(default=1, ge=1, le=1000000),
    page_size: int = Query(default=12, ge=1, le=100),
    lang: Language = "ru",
):
    if min_price is not None and max_price is not None and min_price > max_price:
        raise HTTPException(422, "Минимальная цена не может быть больше максимальной.")
    query = select(Experience).join(Destination).where(Experience.is_published.is_(True))
    if q and q.strip():
        fields = [getattr(model, field + suffix) for model, names in (
            (Experience, ("title", "description")), (Destination, ("name", "country")),
        ) for field in names for suffix in ("", "_en", "_kk")]
        terms = [field.icontains(q.strip(), autoescape=True) for field in fields]
        for suffix in ("", "_en", "_kk"):
            column = getattr(Experience, "tags" + suffix)
            # Extract JSON values instead of matching serialized Unicode escape sequences.
            tag_rows = (func.jsonb_array_elements_text(cast(column, JSONB)) if db.bind.dialect.name == "postgresql"
                        else func.json_each(column)).table_valued("value")
            terms.append(select(1).select_from(tag_rows).where(tag_rows.c.value.icontains(q.strip(), autoescape=True)).exists())
        query = query.where(or_(*terms))
    if destination:
        query = query.where(Destination.slug == destination)
    if continent:
        query = query.where(Destination.continent == continent)
    if category:
        query = query.where(Experience.category == category)
    if min_price is not None:
        query = query.where(Experience.price_from >= min_price)
    if max_price is not None:
        query = query.where(Experience.price_from <= max_price)
    if duration_max is not None:
        query = query.where(Experience.duration_days <= duration_max)
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    ordering = {
        "recommended": (Experience.rating.desc(), Experience.review_count.desc()),
        "rating": (Experience.rating.desc(), Experience.review_count.desc()),
        "price_asc": (Experience.price_from.asc(),), "price_desc": (Experience.price_from.desc(),),
    }[sort]
    rows = db.scalars(query.order_by(*ordering, Experience.id).offset((page - 1) * page_size).limit(page_size)).all()
    return {"items": [experience_data(item, lang) for item in rows], "total": total, "page": page,
            "page_size": page_size, "pages": ceil(total / page_size)}


@router.get("/experiences/{slug}")
def experience(slug: str, db: DbSession, lang: Language = "ru"):
    item = db.scalar(select(Experience).where(Experience.slug == slug, Experience.is_published.is_(True)))
    if not item:
        missing("Тур не найден или снят с публикации.")
    return experience_detail(db, item, lang)


@router.get("/favorites")
def favorites(user: CurrentUser, db: DbSession, lang: Language = "ru"):
    rows = db.scalars(select(Experience).join(Favorite).where(
        Favorite.user_id == user.id, Experience.is_published.is_(True),
    ).order_by(Favorite.created_at.desc())).all()
    return {"items": [experience_data(item, lang) for item in rows]}


@router.put("/favorites/{experience_id}", status_code=204)
def add_favorite(experience_id: str, user: CurrentUser, db: DbSession):
    if not db.scalar(select(Experience.id).where(Experience.id == experience_id, Experience.is_published.is_(True))):
        missing("Тур не найден.")
    if not db.get(Favorite, (user.id, experience_id)):
        db.add(Favorite(user_id=user.id, experience_id=experience_id))
        try:
            db.commit()
        except IntegrityError:
            db.rollback()  # Concurrent identical PUT is still successful and idempotent.
    return Response(status_code=204)


@router.delete("/favorites/{experience_id}", status_code=204)
def remove_favorite(experience_id: str, user: CurrentUser, db: DbSession):
    item = db.get(Favorite, (user.id, experience_id))
    if item:
        db.delete(item)
        db.commit()
    return Response(status_code=204)


def lock_departure(db, departure_id: str):
    return db.scalar(select(Departure).options(lazyload("*")).where(
        Departure.id == departure_id,
    ).with_for_update(of=Departure).execution_options(populate_existing=True))


def add_status(db, booking: Booking, actor: User):
    db.add(BookingStatusHistory(booking_id=booking.id, actor_id=actor.id, status=booking.status))


@router.post("/bookings", status_code=201)
def create_booking(data: BookingInput, user: CurrentUser, db: DbSession, lang: Language = "ru"):
    departure = lock_departure(db, data.departure_id)
    if not departure or not departure.experience.is_published:
        missing("Заезд не найден или тур снят с публикации.")
    if departure.start_date <= date.today():
        raise HTTPException(409, "Бронирование этого заезда уже закрыто.")
    available = departure.capacity - reserved_seats(db, departure.id)
    if data.travelers_count > available:
        raise HTTPException(409, f"Недостаточно свободных мест. Доступно: {max(available, 0)}.")
    booking = Booking(
        reference="SAP-" + secrets.token_hex(6).upper(), user_id=user.id, departure_id=departure.id,
        travelers_count=data.travelers_count, total_amount=departure.price * data.travelers_count,
        currency=departure.experience.currency, contact_name=data.contact_name,
        contact_email=str(data.contact_email).casefold(), notes=data.notes, status="pending",
        experience_snapshot=booking_snapshot(departure.experience), start_date=departure.start_date,
        end_date=departure.end_date,
    )
    db.add(booking)
    db.flush()
    add_status(db, booking, user)
    db.commit()
    return booking_data(booking, lang)


@router.get("/bookings")
def bookings(user: CurrentUser, db: DbSession, lang: Language = "ru"):
    rows = db.scalars(select(Booking).where(Booking.user_id == user.id).order_by(Booking.created_at.desc())).all()
    return {"items": [booking_data(item, lang) for item in rows]}


def locked_booking(db, booking_id: str, user: User, manage: bool = False):
    query = select(Booking).options(lazyload("*")).where(Booking.id == booking_id)
    if manage and user.role != "admin":
        query = query.join(Departure).join(Experience).where(Experience.vendor_id == user.id)
    elif not manage:
        query = query.where(Booking.user_id == user.id)
    item = db.scalar(query)
    if not item:
        missing("Бронирование не найдено.")
    # Every seat-changing operation locks in the same order: departure, then booking.
    lock_departure(db, item.departure_id)
    return db.scalar(query.with_for_update(of=Booking).execution_options(populate_existing=True))


@router.post("/bookings/{booking_id}/cancel")
def cancel_booking(booking_id: str, user: CurrentUser, db: DbSession, lang: Language = "ru"):
    item = locked_booking(db, booking_id, user)
    if item.status == "cancelled":
        return booking_data(item, lang)
    if item.status == "completed" or item.start_date <= date.today():
        raise HTTPException(409, "Начавшийся или завершённый тур нельзя отменить самостоятельно.")
    item.status = "cancelled"
    add_status(db, item, user)
    db.commit()
    return booking_data(item, lang)


def manageable_experience(db, experience_id: str, user: User, lock: bool = False):
    query = select(Experience).where(Experience.id == experience_id)
    if user.role != "admin":
        query = query.where(Experience.vendor_id == user.id)
    if lock:
        query = query.with_for_update(of=Experience)
    item = db.scalar(query)
    if not item:
        missing("Тур не найден или недоступен для редактирования.")
    return item


def validate_itinerary(values: dict, duration: int):
    for name in ("itinerary", "itinerary_en", "itinerary_kk"):
        entries = values.get(name, [])
        days = [entry["day"] for entry in entries]
        if len(set(days)) != len(days) or any(day > duration for day in days):
            raise HTTPException(422, "Дни программы должны быть уникальными и укладываться в длительность тура.")


def experience_values(data):
    values = data.model_dump(exclude_unset=isinstance(data, ExperiencePatch))
    if "image_url" in values:
        values["image_url"] = str(values["image_url"])
    return values


@router.get("/manage/experiences")
def manage_experiences(user: Manager, db: DbSession, lang: Language = "ru"):
    query = select(Experience).order_by(Experience.created_at.desc())
    if user.role != "admin":
        query = query.where(Experience.vendor_id == user.id)
    return {"items": [experience_detail(db, item, lang, manage=True) for item in db.scalars(query)]}


@router.post("/manage/experiences", status_code=201)
def create_experience(data: ExperienceInput, user: Manager, db: DbSession):
    values = experience_values(data)
    if not db.get(Destination, data.destination_id):
        missing("Направление не найдено.")
    validate_itinerary(values, data.duration_days)
    slug_base = re.sub(r"[^a-z0-9]+", "-", (data.title_en or "experience").lower()).strip("-")[:100] or "experience"
    item = Experience(**values, slug=slug_base + "-" + uuid4().hex[:10], vendor_id=user.id)
    db.add(item)
    db.commit()
    db.refresh(item)
    return experience_detail(db, item, manage=True)


@router.patch("/manage/experiences/{experience_id}")
def update_experience(experience_id: str, data: ExperiencePatch, user: Manager, db: DbSession):
    item = manageable_experience(db, experience_id, user, lock=True)
    values = experience_values(data)
    if "destination_id" in values and not db.get(Destination, values["destination_id"]):
        missing("Направление не найдено.")
    duration = values.get("duration_days", item.duration_days)
    if duration != item.duration_days and db.scalar(select(Departure.id).where(Departure.experience_id == item.id).limit(1)):
        raise HTTPException(409, "Нельзя менять длительность тура с созданными заездами. Создайте новый тур.")
    validate_itinerary({name: values.get(name, getattr(item, name)) for name in ("itinerary", "itinerary_en", "itinerary_kk")}, duration)
    for key, value in values.items():
        setattr(item, key, value)
    db.commit()
    db.refresh(item)
    return experience_detail(db, item, manage=True)


@router.post("/manage/experiences/{experience_id}/departures", status_code=201)
def create_departure(experience_id: str, data: DepartureInput, user: Manager, db: DbSession):
    item = manageable_experience(db, experience_id, user, lock=True)
    departure = Departure(experience_id=item.id, start_date=data.start_date,
                          end_date=data.start_date + timedelta(days=item.duration_days - 1),
                          capacity=data.capacity, price=data.price)
    db.add(departure)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Для этого тура уже есть заезд на выбранную дату.") from None
    return departure_data(departure, 0, manage=True)


@router.get("/manage/bookings")
def manage_bookings(user: Manager, db: DbSession, lang: Language = "ru"):
    query = select(Booking).join(Departure).join(Experience).order_by(Booking.created_at.desc())
    if user.role != "admin":
        query = query.where(Experience.vendor_id == user.id)
    return {"items": [booking_data(item, lang) for item in db.scalars(query)]}


@router.patch("/manage/bookings/{booking_id}")
def update_booking(booking_id: str, data: BookingStatusInput, user: Manager, db: DbSession, lang: Language = "ru"):
    item = locked_booking(db, booking_id, user, manage=True)
    if item.status == data.status:
        return booking_data(item, lang)
    allowed = {"pending": {"confirmed", "cancelled"}, "confirmed": {"cancelled", "completed"}}
    if data.status not in allowed.get(item.status, set()):
        raise HTTPException(409, "Недопустимое изменение статуса бронирования.")
    if data.status == "completed" and item.end_date >= date.today():
        raise HTTPException(409, "Тур можно завершить только после даты окончания.")
    if data.status == "confirmed" and item.start_date <= date.today():
        raise HTTPException(409, "Нельзя подтвердить уже начавшийся заезд.")
    item.status = data.status
    add_status(db, item, user)
    db.commit()
    return booking_data(item, lang)


@router.get("/admin/users")
def users(user: Admin, db: DbSession):
    return {"items": [user_data(item) for item in db.scalars(select(User).where(User.is_active.is_(True)).order_by(User.created_at.desc()))]}


@router.patch("/admin/users/{user_id}")
def update_role(user_id: str, data: RoleInput, user: Admin, db: DbSession):
    # Lock all administrators to prevent two simultaneous demotions removing the last one.
    admins = db.scalars(select(User).where(User.role == "admin", User.is_active.is_(True)).order_by(User.id).with_for_update()).all()
    db.refresh(user)
    if user.role != "admin":
        raise HTTPException(403, "Доступно только администратору.")
    target = db.get(User, user_id, populate_existing=True, with_for_update=True)
    if not target or not target.is_active:
        missing("Пользователь не найден.")
    if target.role == "admin" and data.role != "admin" and len(admins) <= 1:
        raise HTTPException(409, "Нельзя изменить роль последнего администратора.")
    target.role = data.role
    db.commit()
    return user_data(target)


def destination_manage_data(item: Destination) -> dict:
    return {column.name: getattr(item, column.name) for column in Destination.__table__.columns}


@router.get("/manage/destinations")
def manage_destinations(user: Admin, db: DbSession):
    return {"items": [destination_manage_data(item) for item in db.scalars(select(Destination).order_by(Destination.slug))]}


@router.post("/manage/destinations", status_code=201)
def create_destination(data: DestinationInput, user: Admin, db: DbSession):
    values = data.model_dump()
    values["image_url"] = str(values["image_url"])
    item = Destination(**values)
    db.add(item)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Направление с таким адресом уже существует.") from None
    return destination_manage_data(item)


@router.patch("/manage/destinations/{destination_id}")
def update_destination(destination_id: str, data: DestinationPatch, user: Admin, db: DbSession):
    item = db.get(Destination, destination_id)
    if not item:
        missing("Направление не найдено.")
    values = data.model_dump(exclude_unset=True)
    if "image_url" in values:
        values["image_url"] = str(values["image_url"])
    for key, value in values.items():
        setattr(item, key, value)
    db.commit()
    return destination_manage_data(item)
