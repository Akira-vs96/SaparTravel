"""Transactional email delivery with bounded SMTP retries and private local fallback."""
from datetime import timedelta, timezone
from email.message import EmailMessage
import smtplib
import ssl
from typing import Protocol

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.domain.engagement import DemoEmail, OutboundEmail, PasswordReset
from app.domain.models import User, utc_now


class MailDelivery(Protocol):
    def deliver(self, db: Session, recipient: str, subject: str, body: str, *, reset: PasswordReset | None = None) -> None: ...


class DatabaseMailboxDelivery:
    def deliver(self, db: Session, recipient: str, subject: str, body: str, *, reset: PasswordReset | None = None) -> None:
        db.add(DemoEmail(recipient=recipient, subject=subject, body=body))


class QueuedSMTPDelivery:
    def deliver(self, db: Session, recipient: str, subject: str, body: str, *, reset: PasswordReset | None = None) -> None:
        db.add(OutboundEmail(recipient=recipient, subject=subject, body=body, password_reset=reset))


def get_mail_delivery() -> MailDelivery:
    mode = get_settings().resolved_mail_mode
    if mode == "smtp":
        return QueuedSMTPDelivery()
    if mode == "local":
        return DatabaseMailboxDelivery()
    raise HTTPException(503, "Восстановление пароля по почте временно недоступно. Попробуйте позже.")


def usable_reset(db, reset):
    if reset is None:
        return True
    db.refresh(reset)
    from app.core.security import credential_digest
    expires = reset.expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    user = db.get(User, reset.user_id, populate_existing=True)
    return reset.used_at is None and expires > utc_now() and user is not None and user.is_active and reset.credential_digest == credential_digest(user)


def send_smtp(message):
    settings = get_settings()
    sender = str(settings.smtp_from_email)
    email = EmailMessage()
    email["From"] = sender
    email["To"] = message.recipient
    email["Subject"] = message.subject
    email["Message-ID"] = f"<{message.id}@{sender.rsplit('@', 1)[-1]}>"
    email.set_content(message.body)
    context = ssl.create_default_context()
    arguments = {"host": settings.smtp_host, "port": settings.smtp_port, "timeout": settings.smtp_timeout_seconds}
    connection = smtplib.SMTP_SSL(**arguments, context=context) if settings.smtp_security == "ssl" else smtplib.SMTP(**arguments)
    try:
        connection.ehlo()
        if settings.smtp_security == "starttls":
            connection.starttls(context=context)
            connection.ehlo()
        if settings.smtp_username:
            connection.login(settings.smtp_username, settings.smtp_password.get_secret_value())
        refused = connection.send_message(email, from_addr=sender, to_addrs=[message.recipient])
        if refused:
            raise smtplib.SMTPRecipientsRefused(refused)
    finally:
        # DATA acceptance is the boundary. A failed QUIT must not requeue mail.
        connection.close()


def process_mail_queue(db: Session, *, batch_size=10):
    settings = get_settings()
    counts = {"sent": 0, "retried": 0, "failed": 0, "cancelled": 0}
    if settings.resolved_mail_mode != "smtp":
        return counts
    for _ in range(min(max(batch_size, 1), 100)):
        # Lock one row per transaction; commits must not release a prefetched batch.
        message = db.scalar(select(OutboundEmail).where(
            OutboundEmail.state == "pending", OutboundEmail.next_attempt_at <= utc_now()
        ).order_by(OutboundEmail.next_attempt_at, OutboundEmail.created_at).limit(1).with_for_update(skip_locked=True).execution_options(populate_existing=True))
        if message is None:
            break
        if not usable_reset(db, message.password_reset):
            message.state, message.body, message.error_code = "cancelled", "", "expired_or_replaced"
            counts["cancelled"] += 1
        elif message.attempts >= settings.mail_max_attempts:
            message.state = "failed"
            counts["failed"] += 1
        else:
            message.attempts += 1
            try:
                send_smtp(message)
            except (OSError, smtplib.SMTPException) as error:
                # Exception strings may contain recipient data or credentials.
                message.error_code = type(error).__name__
                terminal = message.attempts >= settings.mail_max_attempts
                message.state = "failed" if terminal else "pending"
                message.next_attempt_at = utc_now() + timedelta(seconds=settings.mail_retry_seconds * 2 ** min(message.attempts - 1, 6))
                counts["failed" if terminal else "retried"] += 1
            else:
                message.state, message.sent_at, message.body, message.error_code = "sent", utc_now(), "", ""
                counts["sent"] += 1
        db.commit()
    return counts
