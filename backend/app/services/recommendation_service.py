"""Deterministic recommendations from current catalog and seat inventory."""
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import lazyload

from app.core.clock import utc_now
from app.domain.models import Booking, CategoryRecord, Departure, Experience
from app.services.catalog_service import active_booking_condition, departure_data, experience_data, money, reservation_counts
from app.services.commerce_service import today


def recommend(db, *, budget: Decimal | None = None, category: str | None = None,
              duration_max: int | None = None, travelers: int = 1, lang: str = "ru"):
    moment = utc_now()
    occupied = select(func.coalesce(func.sum(Booking.travelers_count), 0)).where(
        Booking.departure_id == Departure.id, active_booking_condition(moment),
    ).correlate(Departure).scalar_subquery()
    eligible = select(Departure).where(Departure.status == "scheduled", Departure.start_date > today(),
                                       Departure.capacity - occupied >= travelers)
    if budget is not None:
        # Budget covers the group's base fare. Optional services are priced at checkout.
        eligible = eligible.where(Departure.price * travelers <= budget)
    eligible_prices = eligible.with_only_columns(Departure.experience_id,
                         func.min(Departure.price).label("lowest_price")).group_by(Departure.experience_id).subquery()
    query = select(Experience).join(eligible_prices, eligible_prices.c.experience_id == Experience.id).where(
        Experience.is_published.is_(True), Experience.publication_status == "published", Experience.currency == "KZT",
        Experience.is_monitoring.is_(False),
        Experience.min_participants <= travelers, Experience.max_participants >= travelers,
    )
    if category:
        query = query.where(Experience.category == category)
    if duration_max is not None:
        query = query.where(Experience.duration_days <= duration_max)
    ordering = ((eligible_prices.c.lowest_price.desc(), Experience.rating.desc()) if budget is not None else
                (Experience.rating.desc(), Experience.review_count.desc(), eligible_prices.c.lowest_price.asc()))
    rows = db.scalars(query.order_by(*ordering, Experience.id).limit(6)).all()
    codes = {item.category for item in rows}
    categories = {item.code: item for item in db.scalars(select(CategoryRecord).where(CategoryRecord.code.in_(codes)))} if codes else {}
    # Fetch at most three candidate departures for each of the six selected tours.
    # The alternatives let a concurrent sale invalidate one candidate without an
    # unbounded load of every future departure in the catalog.
    ranked = eligible.with_only_columns(Departure.id.label("departure_id"), func.row_number().over(
        partition_by=Departure.experience_id,
        order_by=(Departure.price, Departure.start_date, Departure.id),
    ).label("candidate_rank")).where(Departure.experience_id.in_([item.id for item in rows])).subquery()
    departures = db.scalars(select(Departure).options(lazyload(Departure.experience))
        .join(ranked, ranked.c.departure_id == Departure.id).where(ranked.c.candidate_rank <= 3)
        .order_by(Departure.price, Departure.start_date, Departure.id)).all() if rows else []
    # A separate grouped read catches seats sold after the candidate query; no
    # per-card availability request or stale stored seat counter is needed.
    counts = reservation_counts(db, [departure.id for departure in departures], moment)
    by_experience = {}
    for departure in departures:
        if departure.capacity - counts.get(departure.id, 0) >= travelers:
            by_experience.setdefault(departure.experience_id, departure)
    items = []
    for experience in rows:
        departure = by_experience.get(experience.id)
        if departure is None:
            continue
        free = departure.capacity - counts.get(departure.id, 0)
        label = (getattr(categories[experience.category], "name_" + lang) or experience.category) if experience.category in categories else experience.category
        reasons = {
            "ru": (["Укладывается в общий бюджет"] if budget is not None else []) +
                  ([f"Категория: {label}"] if category else []) +
                  ([f"Длительность до {duration_max} дней"] if duration_max is not None else []) + [f"Есть места для {travelers} участников"],
            "en": (["Fits your group budget"] if budget is not None else []) +
                  ([f"Category: {label}"] if category else []) +
                  ([f"Up to {duration_max} days"] if duration_max is not None else []) + [f"Seats available for {travelers} travelers"],
            "kk": (["Топтың бюджетіне сай"] if budget is not None else []) +
                  ([f"Санат: {label}"] if category else []) +
                  ([f"Ұзақтығы {duration_max} күнге дейін"] if duration_max is not None else []) + [f"{travelers} қатысушыға орын бар"],
        }
        result = experience_data(experience, lang)
        result.update(reason=" · ".join(reasons[lang]), reason_code="_".join(
            key for key, applies in (("budget", budget is not None), ("duration", duration_max is not None),
                                    ("interest", bool(category)), ("availability", True)) if applies),
                      recommended_departure=departure_data(departure, departure.capacity-free),
                      quoted_base_amount=money(departure.price * travelers))
        items.append(result)
    notices = {
        "ru": "Подбор учитывает бюджет на всю группу, длительность, интересы и свободные места. Дополнительные услуги рассчитываются при оформлении.",
        "en": "Matches use your whole-group budget, duration, interests and available seats. Optional services are priced at checkout.",
        "kk": "Таңдау бүкіл топтың бюджетіне, ұзақтығына, қызығушылықтарына және бос орындарға негізделген. Қосымша қызметтер бронь кезінде есептеледі.",
    }
    return {"items": items, "total": len(items), "notice": notices[lang], "currency": "KZT", "budget_scope": "group_base_fare"}
