"""Identity and engagement records, kept separate from the commerce domain."""
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.domain.models import new_id, utc_now, User


class RevokedAccessToken(Base):
    __tablename__ = "revoked_access_tokens"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    revoked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class UserAccessBoundary(Base):
    __tablename__ = "user_access_boundaries"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    invalidated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class PasswordReset(Base):
    __tablename__ = "password_resets"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    credential_digest: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class DemoEmail(Base):
    __tablename__ = "demo_emails"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    recipient: Mapped[str] = mapped_column(String(254), index=True)
    subject: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)


class OutboundEmail(Base):
    __tablename__ = "outbound_emails"
    __table_args__ = (
        CheckConstraint("state IN ('pending','sent','failed','cancelled')", name="ck_outbound_email_state"),
        CheckConstraint("attempts >= 0", name="ck_outbound_email_attempts"),
        Index("ix_outbound_email_pending", "state", "next_attempt_at"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    recipient: Mapped[str] = mapped_column(String(254))
    subject: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text)
    state: Mapped[str] = mapped_column(String(12), default="pending")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_code: Mapped[str] = mapped_column(String(80), default="")
    password_reset_id: Mapped[str | None] = mapped_column(ForeignKey("password_resets.id", ondelete="CASCADE"), nullable=True)
    password_reset: Mapped[PasswordReset | None] = relationship()


class Notification(Base):
    __tablename__ = "notifications"
    __table_args__ = (Index("ix_notifications_user_read_created", "user_id", "is_read", "created_at"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    event: Mapped[str] = mapped_column(String(80))
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text)
    title_en: Mapped[str] = mapped_column(String(200), default="")
    title_kk: Mapped[str] = mapped_column(String(200), default="")
    body_en: Mapped[str] = mapped_column(Text, default="")
    body_kk: Mapped[str] = mapped_column(Text, default="")
    booking_id: Mapped[str | None] = mapped_column(ForeignKey("bookings.id"), nullable=True)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class SavedSearch(Base):
    __tablename__ = "saved_searches"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    filters: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class SupportTicket(Base):
    __tablename__ = "support_tickets"
    __table_args__ = (
        CheckConstraint("status IN ('open','in_progress','resolved','closed')", name="ck_support_ticket_status"),
        CheckConstraint("priority IN ('P1','P2','P3')", name="ck_support_priority"),
        CheckConstraint("response_working_seconds IS NULL OR response_working_seconds >= 0", name="ck_support_response_seconds"),
        Index("ix_support_response_due_priority", "response_due_at", "priority"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    vendor_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    booking_id: Mapped[str | None] = mapped_column(ForeignKey("bookings.id"), nullable=True, index=True)
    subject: Mapped[str] = mapped_column(String(180))
    status: Mapped[str] = mapped_column(String(20), default="open")
    priority: Mapped[str] = mapped_column(String(2), default="P3")
    response_due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    first_response_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    first_response_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    response_working_seconds: Mapped[int | None] = mapped_column(Integer)
    response_calendar: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class SupportMessage(Base):
    __tablename__ = "support_messages"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    ticket_id: Mapped[str] = mapped_column(ForeignKey("support_tickets.id", ondelete="CASCADE"), index=True)
    author_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    author_role: Mapped[str] = mapped_column(String(20))
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    author: Mapped[User] = relationship(lazy="joined")


class Review(Base):
    __tablename__ = "reviews"
    __table_args__ = (
        CheckConstraint("rating >= 1 AND rating <= 5", name="ck_reviews_rating"),
        CheckConstraint("status IN ('pending','approved','rejected')", name="ck_reviews_status"),
        Index("ix_reviews_experience_status", "experience_id", "status"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    booking_id: Mapped[str] = mapped_column(ForeignKey("bookings.id"), unique=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    experience_id: Mapped[str] = mapped_column(ForeignKey("experiences.id"))
    rating: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(180))
    text: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    moderated_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    moderated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    author: Mapped[User] = relationship(foreign_keys=[user_id], lazy="joined")


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    actor_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(100))
    resource_type: Mapped[str] = mapped_column(String(80))
    resource_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)
