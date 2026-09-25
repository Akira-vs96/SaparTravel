from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, ForeignKey, Index, Integer, JSON, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def new_id() -> str:
    return str(uuid4())


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"
    __table_args__ = (CheckConstraint("role IN ('traveler', 'vendor', 'admin')", name="ck_users_role"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20), default="traveler")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class Destination(Base):
    __tablename__ = "destinations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    slug: Mapped[str] = mapped_column(String(100), unique=True)
    name: Mapped[str] = mapped_column(String(160))
    name_en: Mapped[str] = mapped_column(String(160), default="")
    name_kk: Mapped[str] = mapped_column(String(160), default="")
    country: Mapped[str] = mapped_column(String(120))
    country_en: Mapped[str] = mapped_column(String(120), default="")
    country_kk: Mapped[str] = mapped_column(String(120), default="")
    continent: Mapped[str] = mapped_column(String(30), index=True)
    description: Mapped[str] = mapped_column(Text)
    description_en: Mapped[str] = mapped_column(Text, default="")
    description_kk: Mapped[str] = mapped_column(Text, default="")
    image_url: Mapped[str] = mapped_column(String(2000))


class Experience(Base):
    __tablename__ = "experiences"
    __table_args__ = (
        CheckConstraint("duration_days >= 1 AND duration_days <= 90", name="ck_experiences_duration"),
        CheckConstraint("price_from >= 1", name="ck_experiences_price"),
        CheckConstraint("rating >= 0 AND rating <= 5", name="ck_experiences_rating"),
        CheckConstraint("category IN ('Nature','Culture','Adventure','Food','Beach','City')", name="ck_experiences_category"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    slug: Mapped[str] = mapped_column(String(160), unique=True)
    vendor_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    destination_id: Mapped[str] = mapped_column(ForeignKey("destinations.id"), index=True)
    title: Mapped[str] = mapped_column(String(180))
    title_en: Mapped[str] = mapped_column(String(180), default="")
    title_kk: Mapped[str] = mapped_column(String(180), default="")
    description: Mapped[str] = mapped_column(Text)
    description_en: Mapped[str] = mapped_column(Text, default="")
    description_kk: Mapped[str] = mapped_column(Text, default="")
    category: Mapped[str] = mapped_column(String(30), index=True)
    duration_days: Mapped[int] = mapped_column(Integer)
    price_from: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    rating: Mapped[Decimal] = mapped_column(Numeric(2, 1), default=0)
    review_count: Mapped[int] = mapped_column(Integer, default=0)
    image_url: Mapped[str] = mapped_column(String(2000))
    is_published: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    tags: Mapped[list] = mapped_column(JSON, default=list)
    tags_en: Mapped[list] = mapped_column(JSON, default=list)
    tags_kk: Mapped[list] = mapped_column(JSON, default=list)
    included: Mapped[list] = mapped_column(JSON, default=list)
    included_en: Mapped[list] = mapped_column(JSON, default=list)
    included_kk: Mapped[list] = mapped_column(JSON, default=list)
    excluded: Mapped[list] = mapped_column(JSON, default=list)
    excluded_en: Mapped[list] = mapped_column(JSON, default=list)
    excluded_kk: Mapped[list] = mapped_column(JSON, default=list)
    itinerary: Mapped[list] = mapped_column(JSON, default=list)
    itinerary_en: Mapped[list] = mapped_column(JSON, default=list)
    itinerary_kk: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    vendor: Mapped[User] = relationship(lazy="joined")
    destination: Mapped[Destination] = relationship(lazy="joined")


class Departure(Base):
    __tablename__ = "departures"
    __table_args__ = (
        UniqueConstraint("experience_id", "start_date", name="uq_departure_experience_date"),
        CheckConstraint("capacity >= 1 AND capacity <= 1000", name="ck_departures_capacity"),
        CheckConstraint("price >= 1", name="ck_departures_price"),
        CheckConstraint("end_date >= start_date", name="ck_departures_dates"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    experience_id: Mapped[str] = mapped_column(ForeignKey("experiences.id"), index=True)
    start_date: Mapped[date] = mapped_column(Date, index=True)
    end_date: Mapped[date] = mapped_column(Date)
    capacity: Mapped[int] = mapped_column(Integer)
    price: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    experience: Mapped[Experience] = relationship(lazy="joined")


class Favorite(Base):
    __tablename__ = "favorites"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    experience_id: Mapped[str] = mapped_column(ForeignKey("experiences.id", ondelete="CASCADE"), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class Booking(Base):
    __tablename__ = "bookings"
    __table_args__ = (
        CheckConstraint("status IN ('pending','confirmed','cancelled','completed')", name="ck_bookings_status"),
        CheckConstraint("travelers_count >= 1 AND travelers_count <= 20", name="ck_bookings_travelers"),
        CheckConstraint("total_amount >= 1", name="ck_bookings_amount"),
        Index("ix_bookings_departure_status", "departure_id", "status"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    reference: Mapped[str] = mapped_column(String(20), unique=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    departure_id: Mapped[str] = mapped_column(ForeignKey("departures.id"))
    status: Mapped[str] = mapped_column(String(20), default="pending")
    travelers_count: Mapped[int] = mapped_column(Integer)
    total_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    contact_name: Mapped[str] = mapped_column(String(120))
    contact_email: Mapped[str] = mapped_column(String(254))
    notes: Mapped[str] = mapped_column(Text, default="")
    # Freeze agreed product details and dates against subsequent catalog edits.
    experience_snapshot: Mapped[dict] = mapped_column(JSON)
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    departure: Mapped[Departure] = relationship(lazy="joined")


class BookingStatusHistory(Base):
    __tablename__ = "booking_status_history"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    booking_id: Mapped[str] = mapped_column(ForeignKey("bookings.id"), index=True)
    actor_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    status: Mapped[str] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
