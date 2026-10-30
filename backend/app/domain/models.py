from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, ForeignKey, Index, Integer, JSON, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def new_id() -> str:
    return str(uuid4())


def utc_now() -> datetime:
    from app.core.clock import utc_now as clock_now
    return clock_now()


class User(Base):
    __tablename__ = "users"
    __table_args__ = (CheckConstraint("role IN ('traveler', 'vendor', 'admin')", name="ck_users_role"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20), default="traveler")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_monitoring: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class Destination(Base):
    __tablename__ = "destinations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    slug: Mapped[str] = mapped_column(String(100), unique=True)
    continent: Mapped[str] = mapped_column(String(30), index=True)
    image_url: Mapped[str] = mapped_column(String(2000))
    translations: Mapped[list["DestinationTranslation"]] = relationship(cascade="all, delete-orphan", lazy="selectin")


class Experience(Base):
    __tablename__ = "experiences"
    __table_args__ = (
        CheckConstraint("duration_days >= 1 AND duration_days <= 90", name="ck_experiences_duration"),
        CheckConstraint("price_from >= 1", name="ck_experiences_price"),
        CheckConstraint("rating >= 0 AND rating <= 5", name="ck_experiences_rating"),
        CheckConstraint("currency = 'KZT'", name="ck_experiences_currency"),
        CheckConstraint("publication_status IN ('draft','published','unpublished','archived') AND is_published = (publication_status = 'published')", name="ck_experiences_publication"),
        CheckConstraint("min_participants >= 1 AND max_participants <= 20 AND min_participants <= max_participants", name="ck_experiences_participants"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    slug: Mapped[str] = mapped_column(String(160), unique=True)
    vendor_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    destination_id: Mapped[str] = mapped_column(ForeignKey("destinations.id"), index=True)
    category: Mapped[str] = mapped_column(ForeignKey("categories.code"), index=True)
    duration_days: Mapped[int] = mapped_column(Integer)
    price_from: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    currency: Mapped[str] = mapped_column(String(3), default="KZT")
    rating: Mapped[Decimal] = mapped_column(Numeric(2, 1), default=0)
    review_count: Mapped[int] = mapped_column(Integer, default=0)
    image_url: Mapped[str] = mapped_column(String(2000))
    is_published: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    is_monitoring: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    publication_status: Mapped[str] = mapped_column(String(20), default="published")
    min_participants: Mapped[int] = mapped_column(Integer, default=1)
    max_participants: Mapped[int] = mapped_column(Integer, default=20)
    cancellation_policy_version: Mapped[str] = mapped_column(String(30), default="demo-v1")
    translations: Mapped[list["ExperienceTranslation"]] = relationship(cascade="all, delete-orphan", lazy="selectin")
    lines: Mapped[list["CatalogLine"]] = relationship(cascade="all, delete-orphan", lazy="selectin", order_by="CatalogLine.position")
    days: Mapped[list["ItineraryDayRecord"]] = relationship(cascade="all, delete-orphan", lazy="selectin", order_by="ItineraryDayRecord.day")
    images: Mapped[list["ExperienceImage"]] = relationship(cascade="all, delete-orphan", lazy="selectin", order_by="ExperienceImage.position")
    services: Mapped[list["ExperienceService"]] = relationship(cascade="all, delete-orphan", lazy="selectin")
    def __init__(self, **kwargs):
        kwargs.setdefault("currency", "KZT")
        kwargs.setdefault("min_participants", 1)
        kwargs.setdefault("max_participants", 20)
        if "publication_status" not in kwargs:
            kwargs["publication_status"] = "published" if kwargs.get("is_published", True) else "draft"
        kwargs["is_published"] = kwargs["publication_status"] == "published"
        super().__init__(**kwargs)

    cancellation_rules: Mapped[list["ExperienceCancellationRule"]] = relationship(cascade="all, delete-orphan", lazy="selectin", order_by="ExperienceCancellationRule.days_before.desc()")
    vendor: Mapped[User] = relationship(lazy="joined")
    destination: Mapped[Destination] = relationship(lazy="joined")


class Departure(Base):
    __tablename__ = "departures"
    __table_args__ = (
        UniqueConstraint("experience_id", "start_date", name="uq_departure_experience_date"),
        CheckConstraint("capacity >= 1 AND capacity <= 1000", name="ck_departures_capacity"),
        CheckConstraint("price >= 1", name="ck_departures_price"),
        CheckConstraint("end_date >= start_date", name="ck_departures_dates"),
        CheckConstraint("status IN ('scheduled','cancelled')", name="ck_departures_status"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    experience_id: Mapped[str] = mapped_column(ForeignKey("experiences.id"), index=True)
    start_date: Mapped[date] = mapped_column(Date, index=True)
    end_date: Mapped[date] = mapped_column(Date)
    capacity: Mapped[int] = mapped_column(Integer)
    price: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    status: Mapped[str] = mapped_column(String(20), default="scheduled")
    experience: Mapped[Experience] = relationship(lazy="joined")


class Favorite(Base):
    __tablename__ = "favorites"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    experience_id: Mapped[str] = mapped_column(ForeignKey("experiences.id", ondelete="CASCADE"), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class Booking(Base):
    __tablename__ = "bookings"
    __table_args__ = (
        CheckConstraint("status IN ('pending','confirmed','expired','cancelled','completed')", name="ck_bookings_status"),
        CheckConstraint("travelers_count >= 1 AND travelers_count <= 20", name="ck_bookings_travelers"),
        CheckConstraint("total_amount >= 1", name="ck_bookings_amount"),
        CheckConstraint("subtotal_amount >= total_amount AND discount_amount >= 0 AND subtotal_amount - discount_amount = total_amount", name="ck_bookings_totals"),
        Index("ix_bookings_departure_status", "departure_id", "status"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    reference: Mapped[str] = mapped_column(String(20), unique=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    departure_id: Mapped[str] = mapped_column(ForeignKey("departures.id"))
    status: Mapped[str] = mapped_column(String(20), default="pending")
    travelers_count: Mapped[int] = mapped_column(Integer)
    total_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    currency: Mapped[str] = mapped_column(String(3), default="KZT")
    is_synthetic: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    contact_name: Mapped[str] = mapped_column(String(120))
    contact_email: Mapped[str] = mapped_column(String(254))
    notes: Mapped[str] = mapped_column(Text, default="")
    # Freeze agreed product details and dates against subsequent catalog edits.
    experience_snapshot: Mapped[dict] = mapped_column(JSON)
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    subtotal_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    discount_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    cancellation_policy: Mapped[dict] = mapped_column(JSON, default=dict)
    participants: Mapped[list["BookingParticipant"]] = relationship(cascade="all, delete-orphan", lazy="selectin", order_by="BookingParticipant.position")
    items: Mapped[list["BookingItem"]] = relationship(cascade="all, delete-orphan", lazy="selectin")
    payments: Mapped[list["PaymentAttempt"]] = relationship(lazy="selectin", order_by="PaymentAttempt.created_at")
    refunds: Mapped[list["Refund"]] = relationship(lazy="selectin", order_by="Refund.created_at")
    history: Mapped[list["BookingStatusHistory"]] = relationship(lazy="selectin", order_by="BookingStatusHistory.created_at")
    currency_conversion: Mapped["CurrencyConversionRecord | None"] = relationship(lazy="selectin", uselist=False)
    departure: Mapped[Departure] = relationship(lazy="joined")


class BookingStatusHistory(Base):
    __tablename__ = "booking_status_history"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    booking_id: Mapped[str] = mapped_column(ForeignKey("bookings.id"), index=True)
    actor_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    reason: Mapped[str] = mapped_column(String(500), default="")
    status: Mapped[str] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    actor: Mapped[User | None] = relationship(lazy="joined")


class CategoryRecord(Base):
    __tablename__ = "categories"
    code: Mapped[str] = mapped_column(String(30), primary_key=True)
    name_ru: Mapped[str] = mapped_column(String(100))
    name_en: Mapped[str] = mapped_column(String(100))
    name_kk: Mapped[str] = mapped_column(String(100))


class DestinationTranslation(Base):
    __tablename__ = "destination_translations"
    destination_id: Mapped[str] = mapped_column(ForeignKey("destinations.id", ondelete="CASCADE"), primary_key=True)
    language: Mapped[str] = mapped_column(String(2), primary_key=True)
    name: Mapped[str] = mapped_column(String(160), default="")
    country: Mapped[str] = mapped_column(String(120), default="")
    description: Mapped[str] = mapped_column(Text, default="")


class ExperienceTranslation(Base):
    __tablename__ = "experience_translations"
    experience_id: Mapped[str] = mapped_column(ForeignKey("experiences.id", ondelete="CASCADE"), primary_key=True)
    language: Mapped[str] = mapped_column(String(2), primary_key=True)
    title: Mapped[str] = mapped_column(String(180), default="")
    description: Mapped[str] = mapped_column(Text, default="")


class CatalogLine(Base):
    __tablename__ = "catalog_lines"
    experience_id: Mapped[str] = mapped_column(ForeignKey("experiences.id", ondelete="CASCADE"), primary_key=True)
    language: Mapped[str] = mapped_column(String(2), primary_key=True)
    kind: Mapped[str] = mapped_column(String(10), primary_key=True)
    position: Mapped[int] = mapped_column(Integer, primary_key=True)
    text: Mapped[str] = mapped_column(String(300))
    __table_args__ = (CheckConstraint("kind IN ('tags','included','excluded')", name="ck_catalog_line_kind"),)


class ItineraryDayRecord(Base):
    __tablename__ = "itinerary_days"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    experience_id: Mapped[str] = mapped_column(ForeignKey("experiences.id", ondelete="CASCADE"), index=True)
    day: Mapped[int] = mapped_column(Integer)
    translations: Mapped[list["ItineraryTranslation"]] = relationship(cascade="all, delete-orphan", lazy="selectin")
    __table_args__ = (UniqueConstraint("experience_id", "day", name="uq_itinerary_day"), CheckConstraint("day BETWEEN 1 AND 90", name="ck_itinerary_day"))


class ItineraryTranslation(Base):
    __tablename__ = "itinerary_translations"
    day_id: Mapped[str] = mapped_column(ForeignKey("itinerary_days.id", ondelete="CASCADE"), primary_key=True)
    language: Mapped[str] = mapped_column(String(2), primary_key=True)
    title: Mapped[str] = mapped_column(String(180))
    description: Mapped[str] = mapped_column(Text)


class ExperienceImage(Base):
    __tablename__ = "experience_images"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    experience_id: Mapped[str] = mapped_column(ForeignKey("experiences.id", ondelete="CASCADE"), index=True)
    position: Mapped[int] = mapped_column(Integer)
    url: Mapped[str] = mapped_column(String(2000))
    alt: Mapped[str] = mapped_column(String(180), default="")
    __table_args__ = (UniqueConstraint("experience_id", "position", name="uq_experience_image_position"),)


class ExperienceService(Base):
    __tablename__ = "experience_services"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    experience_id: Mapped[str] = mapped_column(ForeignKey("experiences.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(180))
    name_en: Mapped[str] = mapped_column(String(180), default="")
    name_kk: Mapped[str] = mapped_column(String(180), default="")
    price: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    currency: Mapped[str] = mapped_column(String(3), default="KZT")
    per_person: Mapped[bool] = mapped_column(Boolean, default=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    __table_args__ = (CheckConstraint("price >= 0 AND currency = 'KZT'", name="ck_service_amount_currency"),)


class ExperienceCancellationRule(Base):
    __tablename__ = "experience_cancellation_rules"
    experience_id: Mapped[str] = mapped_column(ForeignKey("experiences.id", ondelete="CASCADE"), primary_key=True)
    days_before: Mapped[int] = mapped_column(Integer, primary_key=True)
    refund_percent: Mapped[int] = mapped_column(Integer)
    __table_args__ = (CheckConstraint("days_before BETWEEN 0 AND 3650 AND refund_percent BETWEEN 0 AND 100", name="ck_cancellation_rule_bounds"),)


class BookingParticipant(Base):
    __tablename__ = "booking_participants"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    booking_id: Mapped[str] = mapped_column(ForeignKey("bookings.id", ondelete="CASCADE"), index=True)
    position: Mapped[int] = mapped_column(Integer)
    name: Mapped[str] = mapped_column(String(120))
    __table_args__ = (UniqueConstraint("booking_id", "position", name="uq_booking_participant_position"),)


class BookingItem(Base):
    __tablename__ = "booking_items"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    booking_id: Mapped[str] = mapped_column(ForeignKey("bookings.id", ondelete="CASCADE"), index=True)
    service_id: Mapped[str | None] = mapped_column(ForeignKey("experience_services.id"))
    kind: Mapped[str] = mapped_column(String(20))
    name: Mapped[str] = mapped_column(String(180))
    quantity: Mapped[int] = mapped_column(Integer)
    unit_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    total_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    currency: Mapped[str] = mapped_column(String(3))
    __table_args__ = (CheckConstraint("quantity > 0 AND unit_amount >= 0 AND total_amount >= 0", name="ck_booking_item_amount"),)


class PromoCode(Base):
    __tablename__ = "promocodes"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    code: Mapped[str] = mapped_column(String(40), unique=True)
    kind: Mapped[str] = mapped_column(String(10))
    value: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    currency: Mapped[str] = mapped_column(String(3), default="KZT")
    min_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    usage_limit: Mapped[int] = mapped_column(Integer, default=100)
    per_user_limit: Mapped[int] = mapped_column(Integer, default=1)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    experience_id: Mapped[str | None] = mapped_column(ForeignKey("experiences.id"))
    category: Mapped[str | None] = mapped_column(ForeignKey("categories.code"))
    __table_args__ = (CheckConstraint("kind IN ('percent','fixed') AND value > 0 AND (kind != 'percent' OR value <= 100) AND min_amount >= 0 AND ends_at > starts_at AND usage_limit > 0 AND per_user_limit > 0 AND currency = 'KZT'", name="ck_promocode_rules"),)


class PromoRedemption(Base):
    __tablename__ = "promo_redemptions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    promo_id: Mapped[str] = mapped_column(ForeignKey("promocodes.id"), index=True)
    booking_id: Mapped[str] = mapped_column(ForeignKey("bookings.id"), unique=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    discount_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class ProviderOperation(Base):
    __tablename__ = "provider_operations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    kind: Mapped[str] = mapped_column(String(10))
    scenario: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(20))
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    currency: Mapped[str] = mapped_column(String(3))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    __table_args__ = (CheckConstraint("amount >= 0", name="ck_provider_amount"),)


class PaymentAttempt(Base):
    __tablename__ = "payment_attempts"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    booking_id: Mapped[str] = mapped_column(ForeignKey("bookings.id"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    idempotency_key: Mapped[str] = mapped_column(String(100))
    request_fingerprint: Mapped[str] = mapped_column(String(64))
    provider_operation_id: Mapped[str] = mapped_column(ForeignKey("provider_operations.id"), unique=True)
    instrument_id: Mapped[str] = mapped_column(String(40))
    masked_card: Mapped[str] = mapped_column(String(24))
    status: Mapped[str] = mapped_column(String(20))
    error_code: Mapped[str] = mapped_column(String(40), default="")
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    currency: Mapped[str] = mapped_column(String(3))
    action_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    events: Mapped[list["PaymentEvent"]] = relationship(lazy="selectin", order_by="PaymentEvent.created_at")
    __table_args__ = (UniqueConstraint("user_id", "idempotency_key", name="uq_payment_idempotency"), CheckConstraint("status IN ('created','requires_action','unknown','succeeded','failed','cancelled') AND amount > 0", name="ck_payment_state_amount"), Index("uq_payment_succeeded_booking", "booking_id", unique=True, postgresql_where=__import__('sqlalchemy').text("status = 'succeeded'"), sqlite_where=__import__('sqlalchemy').text("status = 'succeeded'")))


class PaymentEvent(Base):
    __tablename__ = "payment_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    payment_id: Mapped[str] = mapped_column(ForeignKey("payment_attempts.id"), index=True)
    status: Mapped[str] = mapped_column(String(20))
    reason: Mapped[str] = mapped_column(String(500), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class Refund(Base):
    __tablename__ = "refunds"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    booking_id: Mapped[str] = mapped_column(ForeignKey("bookings.id"), index=True)
    payment_id: Mapped[str] = mapped_column(ForeignKey("payment_attempts.id"), index=True)
    provider_operation_id: Mapped[str] = mapped_column(ForeignKey("provider_operations.id"), unique=True)
    idempotency_key: Mapped[str] = mapped_column(String(100), unique=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    currency: Mapped[str] = mapped_column(String(3))
    reason: Mapped[str] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(20))
    actor_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    events: Mapped[list["RefundEvent"]] = relationship(lazy="selectin", order_by="RefundEvent.created_at")
    __table_args__ = (CheckConstraint("amount > 0 AND status IN ('pending','succeeded','failed')", name="ck_refund_amount_state"),)


class RefundEvent(Base):
    __tablename__ = "refund_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    refund_id: Mapped[str] = mapped_column(ForeignKey("refunds.id"), index=True)
    status: Mapped[str] = mapped_column(String(20))
    reason: Mapped[str] = mapped_column(String(500), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class CurrencyConversionRecord(Base):
    __tablename__ = "currency_conversion_records"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    booking_id: Mapped[str | None] = mapped_column(ForeignKey("bookings.id"), unique=True)
    experience_id: Mapped[str | None] = mapped_column(ForeignKey("experiences.id"), unique=True)
    original_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    original_currency: Mapped[str] = mapped_column(String(3))
    equivalent_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    factor: Mapped[Decimal] = mapped_column(Numeric(12, 4))
    rule: Mapped[str] = mapped_column(String(150), default="Educational USD × 500; not an exchange rate")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


def _translated_property(field, language, record_type):
    def get(self):
        row = next((r for r in self.translations if r.language == language), None)
        return getattr(row, field) if row else ""
    def set_value(self, value):
        row = next((r for r in self.translations if r.language == language), None)
        if row is None:
            row = record_type(language=language)
            self.translations.append(row)
        setattr(row, field, value or "")
    return property(get, set_value)


def _lines_property(kind, language):
    def get(self):
        return [r.text for r in sorted(self.lines, key=lambda r: r.position) if r.kind == kind and r.language == language]
    def set_value(self, values):
        current = [r for r in self.lines if r.kind == kind and r.language == language]
        # Update rows in place to avoid conflicting insert/delete ordering on composite keys.
        for position, value in enumerate(values or []):
            row = next((r for r in current if r.position == position), None)
            if row:
                row.text = value
            else:
                self.lines.append(CatalogLine(kind=kind, language=language, position=position, text=value))
        for row in current:
            if row.position >= len(values or []):
                self.lines.remove(row)
    return property(get, set_value)


def _itinerary_property(language):
    def get(self):
        result = []
        for day in sorted(self.days, key=lambda r: r.day):
            row = next((r for r in day.translations if r.language == language), None)
            if row:
                result.append({"day": day.day, "title": row.title, "description": row.description})
        return result
    def set_value(self, values):
        remaining = set()
        for value in values or []:
            remaining.add(value["day"])
            day = next((r for r in self.days if r.day == value["day"]), None)
            if day is None:
                day = ItineraryDayRecord(day=value["day"])
                self.days.append(day)
            row = next((r for r in day.translations if r.language == language), None)
            if row is None:
                day.translations.append(ItineraryTranslation(language=language, title=value["title"], description=value["description"]))
            else:
                row.title, row.description = value["title"], value["description"]
        for day in list(self.days):
            if day.day not in remaining:
                for row in list(day.translations):
                    if row.language == language:
                        day.translations.remove(row)
                if not day.translations:
                    self.days.remove(day)
    return property(get, set_value)


for _language in ("ru", "en", "kk"):
    _suffix = "" if _language == "ru" else "_" + _language
    for _field in ("name", "country", "description"):
        setattr(Destination, _field + _suffix, _translated_property(_field, _language, DestinationTranslation))
    for _field in ("title", "description"):
        setattr(Experience, _field + _suffix, _translated_property(_field, _language, ExperienceTranslation))
    for _field in ("tags", "included", "excluded"):
        setattr(Experience, _field + _suffix, _lines_property(_field, _language))
    setattr(Experience, "itinerary" + _suffix, _itinerary_property(_language))

# Compatibility writes to is_published preserve the canonical publication lifecycle.
from sqlalchemy import event as _sa_event


@_sa_event.listens_for(Experience.is_published, "set")
def _sync_publication_flag(target, value, oldvalue, initiator):
    if getattr(target, "_publication_sync", False):
        return
    target._publication_sync = True
    try:
        if value:
            target.publication_status = "published"
        elif target.publication_status not in ("draft", "unpublished", "archived"):
            target.publication_status = "unpublished"
    finally:
        target._publication_sync = False


@_sa_event.listens_for(Experience.publication_status, "set")
def _sync_publication_status(target, value, oldvalue, initiator):
    if getattr(target, "_publication_sync", False):
        return
    target._publication_sync = True
    try:
        target.is_published = value == "published"
    finally:
        target._publication_sync = False
