from datetime import date, timedelta
from decimal import Decimal
from math import ceil
import re
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import func, or_, select, text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import lazyload

from app.api.schemas import (
    Category, Continent, DepartureInput, DestinationInput, DestinationPatch, ExperienceInput,
    ExperiencePatch, DeparturePatch, Language,
)
from app.core.security import Admin, CurrentUser, DbSession, Manager
from app.domain.models import (Booking, Departure, Destination, Experience, Favorite, User, ExperienceTranslation, DestinationTranslation, CatalogLine, ExperienceImage, ExperienceService, BookingItem, ExperienceCancellationRule, CategoryRecord)
from app.services.commerce_service import lock_departure, cancel_booking as service_cancel_booking, today
from app.services.catalog_service import (
    booking_data, departure_data, experience_data, experience_detail,
    localized, reserved_seats, reservation_counts,
)

router = APIRouter()


def catalog_audit(db, user, action, resource_type, resource_id):
    from app.services.engagement_service import audit
    audit(db, user.id, action, resource_type, resource_id)


def missing(message: str = "Запись не найдена."):
    raise HTTPException(404, message)


@router.get("/health")
def health(db: DbSession) -> dict:
    try:
        db.execute(text("SELECT 1"))
    except SQLAlchemyError:
        raise HTTPException(503, "База данных временно недоступна.") from None
    return {"status": "ok", "service": "sapartravel-api", "database": "ok"}


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


@router.get("/recommendations")
def recommendations(
    db: DbSession,
    budget: Decimal | None = Query(default=None, ge=0, le=100000000),
    category: Category | None = None,
    duration_max: int | None = Query(default=None, ge=1, le=90),
    travelers: int = Query(default=1, ge=1, le=20),
    lang: Language = "ru",
):
    from app.services.recommendation_service import recommend
    return recommend(db, budget=budget, category=category, duration_max=duration_max, travelers=travelers, lang=lang)


@router.get("/experiences")
def experiences(
    db: DbSession,
    q: str | None = Query(default=None, max_length=100),
    destination: str | None = Query(default=None, max_length=100),
    continent: Continent | None = None,
    category: Category | None = None,
    min_price: Decimal | None = Query(default=None, ge=0, le=100000000),
    max_price: Decimal | None = Query(default=None, ge=0, le=100000000),
    date_from: date | None = None,
    date_to: date | None = None,
    travelers: int = Query(default=1, ge=1, le=20),
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
        needle = q.strip()
        query = query.where(or_(
            select(ExperienceTranslation.experience_id).where(
                ExperienceTranslation.experience_id == Experience.id,
                or_(ExperienceTranslation.title.icontains(needle, autoescape=True), ExperienceTranslation.description.icontains(needle, autoescape=True)),
            ).exists(),
            select(DestinationTranslation.destination_id).where(
                DestinationTranslation.destination_id == Destination.id,
                or_(DestinationTranslation.name.icontains(needle, autoescape=True), DestinationTranslation.country.icontains(needle, autoescape=True)),
            ).exists(),
            select(CatalogLine.experience_id).where(CatalogLine.experience_id == Experience.id,
                                                  CatalogLine.kind == "tags", CatalogLine.text.icontains(needle, autoescape=True)).exists(),
        ))
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
    if date_from and date_to and date_to < date_from:
        raise HTTPException(422, "Дата окончания диапазона не может быть раньше начала.")
    query = query.where(Experience.min_participants <= travelers, Experience.max_participants >= travelers)
    if date_from or date_to or travelers > 1:
        from app.services.catalog_service import active_booking_condition
        occupied = select(func.coalesce(func.sum(Booking.travelers_count), 0)).where(
            Booking.departure_id == Departure.id, active_booking_condition(),
        ).correlate(Departure).scalar_subquery()
        available = select(Departure.id).where(Departure.experience_id == Experience.id,
                    Departure.status == "scheduled", Departure.start_date > today(), Departure.capacity - occupied >= travelers)
        if date_from:
            available = available.where(Departure.start_date >= date_from)
        if date_to:
            available = available.where(Departure.start_date <= date_to)
        query = query.where(available.exists())
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
    values.pop("gallery", None)
    values.pop("services", None)
    values.pop("cancellation_rules", None)
    status = values.get("publication_status")
    if status is None:
        values.pop("publication_status", None)
        if "is_published" in values:
            values["publication_status"] = "published" if values["is_published"] else "draft" if isinstance(data, ExperienceInput) else "unpublished"
    else:
        values["is_published"] = status == "published"
    return values


def update_children(db, item, data):
    if "cancellation_rules" in data.model_fields_set or isinstance(data, ExperienceInput):
        rules = data.cancellation_rules or []
        if rules:
            if len({rule.days_before for rule in rules}) != len(rules) or not any(rule.days_before == 0 for rule in rules):
                raise HTTPException(422, "Условия отмены должны иметь уникальные пороги и правило для 0 дней.")
            ordered = sorted(rules, key=lambda rule: rule.days_before)
            if any(a.refund_percent > b.refund_percent for a,b in zip(ordered, ordered[1:])):
                raise HTTPException(422, "Возврат при более ранней отмене не может быть меньше.")
        current = {rule.days_before: rule for rule in item.cancellation_rules}
        for rule in rules:
            if rule.days_before in current:
                current[rule.days_before].refund_percent = rule.refund_percent
            else:
                item.cancellation_rules.append(ExperienceCancellationRule(days_before=rule.days_before, refund_percent=rule.refund_percent))
        thresholds = {rule.days_before for rule in rules}
        for rule in list(item.cancellation_rules):
            if rule.days_before not in thresholds:
                item.cancellation_rules.remove(rule)
    if "gallery" in data.model_fields_set or isinstance(data, ExperienceInput):
        urls = [str(url) for url in (data.gallery or [])] or [item.image_url]
        by_position = {image.position: image for image in item.images}
        for position, url in enumerate(urls):
            if position in by_position:
                by_position[position].url = url
            else:
                item.images.append(ExperienceImage(position=position, url=url, alt=item.title))
        for image in list(item.images):
            if image.position >= len(urls):
                item.images.remove(image)
    if "services" in data.model_fields_set or isinstance(data, ExperienceInput):
        supplied = set()
        for data_service in data.services or []:
            values = data_service.model_dump(exclude={"id"})
            service = next((service for service in item.services if service.id == data_service.id), None) if data_service.id else None
            if data_service.id and not service:
                raise HTTPException(422, "Услуга не принадлежит этому туру.")
            if service:
                for key, value in values.items():
                    setattr(service, key, value)
            else:
                service = ExperienceService(**values)
                item.services.append(service)
                db.flush()
            supplied.add(service.id)
        # Sold service references and historical item prices remain intact.
        for service in item.services:
            if service.id not in supplied:
                service.is_active = False


def validate_publication(item):
    if item.min_participants > item.max_participants:
        raise HTTPException(422, "Минимальное число участников больше максимального.")
    if not item.is_published:
        return
    if not item.title.strip() or len(item.description.strip()) < 20 or not item.image_url or not item.itinerary:
        raise HTTPException(422, "Перед публикацией заполните название, описание, изображение и программу тура.")
    if item.currency != "KZT":
        raise HTTPException(422, "Новые продажи разрешены только в KZT.")


@router.get("/manage/experiences")
def manage_experiences(user: Manager, db: DbSession, lang: Language = "ru"):
    query = select(Experience).order_by(Experience.created_at.desc())
    if user.role != "admin":
        query = query.where(Experience.vendor_id == user.id)
    rows = db.scalars(query).all()
    departures = db.scalars(select(Departure).options(lazyload(Departure.experience))
        .where(Departure.experience_id.in_([item.id for item in rows]))
        .order_by(Departure.experience_id, Departure.start_date)).all() if rows else []
    counts = reservation_counts(db, [departure.id for departure in departures])
    by_experience = {}
    for departure in departures:
        by_experience.setdefault(departure.experience_id, []).append(departure)
    return {"items": [experience_detail(db, item, lang, manage=True,
                        departures=by_experience.get(item.id, []), reserved_counts=counts) for item in rows]}


@router.post("/manage/experiences", status_code=201)
def create_experience(data: ExperienceInput, user: Manager, db: DbSession):
    values = experience_values(data)
    if not db.get(Destination, data.destination_id):
        missing("Направление не найдено.")
    if not db.get(CategoryRecord, data.category):
        raise HTTPException(422, "Категория не найдена.")
    validate_itinerary(values, data.duration_days)
    slug_base = re.sub(r"[^a-z0-9]+", "-", (data.title_en or "experience").lower()).strip("-")[:100] or "experience"
    item = Experience(id=str(uuid4()), **values, slug=slug_base + "-" + uuid4().hex[:10], vendor_id=user.id)
    db.add(item)
    update_children(db, item, data)
    validate_publication(item)
    catalog_audit(db, user, "catalog.created", "experience", item.id)
    db.commit()
    db.refresh(item)
    return experience_detail(db, item, manage=True)


@router.patch("/manage/experiences/{experience_id}")
def update_experience(experience_id: str, data: ExperiencePatch, user: Manager, db: DbSession):
    item = manageable_experience(db, experience_id, user, lock=True)
    values = experience_values(data)
    if "destination_id" in values and not db.get(Destination, values["destination_id"]):
        missing("Направление не найдено.")
    if "category" in values and not db.get(CategoryRecord, values["category"]):
        raise HTTPException(422, "Категория не найдена.")
    duration = values.get("duration_days", item.duration_days)
    if duration != item.duration_days and db.scalar(select(Departure.id).where(Departure.experience_id == item.id).limit(1)):
        raise HTTPException(409, "Нельзя менять длительность тура с созданными заездами. Создайте новый тур.")
    validate_itinerary({name: values.get(name, getattr(item, name)) for name in ("itinerary", "itinerary_en", "itinerary_kk")}, duration)
    for key, value in values.items():
        setattr(item, key, value)
    update_children(db, item, data)
    validate_publication(item)
    catalog_audit(db, user, "catalog.updated", "experience", item.id)
    db.commit()
    db.refresh(item)
    return experience_detail(db, item, manage=True)


@router.post("/manage/experiences/{experience_id}/departures", status_code=201)
def create_departure(experience_id: str, data: DepartureInput, user: Manager, db: DbSession):
    item = manageable_experience(db, experience_id, user, lock=True)
    departure = Departure(id=str(uuid4()), experience_id=item.id, start_date=data.start_date,
                          end_date=data.start_date + timedelta(days=item.duration_days - 1),
                          capacity=data.capacity, price=data.price)
    db.add(departure)
    try:
        catalog_audit(db, user, "departure.created", "departure", departure.id)
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



def destination_manage_data(item: Destination) -> dict:
    result = {column.name: getattr(item, column.name) for column in Destination.__table__.columns}
    for field in ("name", "country", "description"):
        for suffix in ("", "_en", "_kk"):
            result[field+suffix] = getattr(item, field+suffix)
    return result


@router.get("/manage/destinations")
def manage_destinations(user: Admin, db: DbSession):
    return {"items": [destination_manage_data(item) for item in db.scalars(select(Destination).order_by(Destination.slug))]}


@router.post("/manage/destinations", status_code=201)
def create_destination(data: DestinationInput, user: Admin, db: DbSession):
    values = data.model_dump()
    values["image_url"] = str(values["image_url"])
    item = Destination(id=str(uuid4()), **values)
    db.add(item)
    try:
        catalog_audit(db, user, "destination.created", "destination", item.id)
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
    catalog_audit(db, user, "destination.updated", "destination", item.id)
    db.commit()
    return destination_manage_data(item)


@router.patch("/manage/experiences/{experience_id}/departures/{departure_id}")
def update_departure(experience_id: str, departure_id: str, data: DeparturePatch, user: Manager, db: DbSession):
    manageable_experience(db, experience_id, user)
    departure = lock_departure(db, departure_id)
    if not departure or departure.experience_id != experience_id:
        missing("Выезд не найден.")
    if departure.status == "cancelled" and data.status == "scheduled":
        raise HTTPException(409, "Отменённый выезд нельзя восстановить. Создайте новый.")
    occupied = reserved_seats(db, departure.id)
    if data.capacity is not None:
        if data.capacity < occupied:
            raise HTTPException(409, "Вместимость не может быть меньше числа занятых мест.")
        departure.capacity = data.capacity
    if data.price is not None:
        departure.price = data.price
    if data.status == "cancelled" and departure.status != "cancelled":
        departure.status = "cancelled"
        bookings = db.scalars(select(Booking).where(Booking.departure_id == departure.id,
                              Booking.status.in_(("pending", "confirmed"))).order_by(Booking.id)).all()
        for booking in bookings:
            service_cancel_booking(db, user, booking.id, "Выезд отменён поставщиком", manage=True, force_full=True)
    catalog_audit(db, user, "departure.updated", "departure", departure.id)
    db.commit()
    return departure_data(departure, reserved_seats(db, departure.id), manage=True)


@router.patch("/manage/departures/{departure_id}")
def update_departure_alias(departure_id: str, data: DeparturePatch, user: Manager, db: DbSession):
    departure = db.get(Departure, departure_id)
    if not departure:
        missing("Выезд не найден.")
    return update_departure(departure.experience_id, departure_id, data, user, db)


@router.delete("/manage/departures/{departure_id}", status_code=204)
def delete_departure(departure_id: str, user: Manager, db: DbSession):
    departure = db.get(Departure, departure_id)
    if not departure:
        missing("Выезд не найден.")
    manageable_experience(db, departure.experience_id, user)
    departure = lock_departure(db, departure_id)
    if db.scalar(select(Booking.id).where(Booking.departure_id == departure_id).limit(1)):
        raise HTTPException(409, "Нельзя удалить выезд с историей бронирований. Отмените выезд.")
    db.delete(departure)
    catalog_audit(db, user, "departure.deleted", "departure", departure.id)
    db.commit()
    return Response(status_code=204)
