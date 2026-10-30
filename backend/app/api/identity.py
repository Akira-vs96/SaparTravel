"""Authentication with server-side logout and one-use password recovery."""
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import secrets

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import EmailStr, Field
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError

from app.api.schemas import InputModel, LoginInput, ProfileInput, RegisterInput
from app.core.config import get_settings
from app.core.security import (Admin, CurrentUser, DbSession, DUMMY_HASH, check_auth_rate,
                               credential_digest, password_hash, token_for)
from app.domain.engagement import DemoEmail, OutboundEmail, PasswordReset, RevokedAccessToken
from app.domain.models import User, utc_now
from app.services.catalog_service import user_data
from app.services.engagement_service import audit
from app.services.mail_service import get_mail_delivery, usable_reset

router = APIRouter()


class ChangePasswordInput(InputModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=10, max_length=128)


class ForgotPasswordInput(InputModel):
    email: EmailStr


class ResetPasswordInput(InputModel):
    token: str = Field(min_length=20, max_length=200)
    new_password: str = Field(min_length=10, max_length=128)


def auth_response(user):
    return {"access_token": token_for(user), "token_type": "bearer", "user": user_data(user)}


def aware(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


@router.post("/auth/register", status_code=201, dependencies=[Depends(check_auth_rate)])
def register(data: RegisterInput, db: DbSession):
    email = str(data.email).casefold()
    if db.scalar(select(User.id).where(User.email == email)):
        raise HTTPException(409, "Аккаунт с таким адресом уже существует.")
    user = User(name=data.name, email=email, password_hash=password_hash.hash(data.password), role="traveler")
    db.add(user)
    try:
        db.flush()
        audit(db, user.id, "account.register", "user", user.id)
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
    audit(db, user.id, "account.login", "user", user.id)
    db.commit()
    return auth_response(user)


@router.get("/auth/me")
def me(user: CurrentUser):
    return user_data(user)


@router.patch("/auth/me")
def update_me(data: ProfileInput, user: CurrentUser, db: DbSession):
    user.name = data.name
    audit(db, user.id, "account.profile", "user", user.id)
    db.commit()
    return user_data(user)


@router.post("/auth/logout", status_code=204)
def logout(request: Request, user: CurrentUser, db: DbSession):
    payload = request.state.auth_payload
    db.add(RevokedAccessToken(id=payload["jti"], user_id=user.id,
                            expires_at=datetime.fromtimestamp(payload["exp"], timezone.utc)))
    audit(db, user.id, "account.logout", "user", user.id)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
    return Response(status_code=204)


@router.post("/auth/change-password", dependencies=[Depends(check_auth_rate)])
def change_password(data: ChangePasswordInput, user: CurrentUser, db: DbSession):
    locked = db.scalar(select(User).where(User.id == user.id).with_for_update().execution_options(populate_existing=True))
    if not locked or not locked.is_active:
        raise HTTPException(401, "Войдите в аккаунт, чтобы продолжить.")
    if not password_hash.verify(data.current_password, locked.password_hash):
        raise HTTPException(422, "Текущий пароль указан неверно.")
    if data.current_password == data.new_password:
        raise HTTPException(422, "Новый пароль должен отличаться от текущего.")
    locked.password_hash = password_hash.hash(data.new_password)
    db.execute(update(PasswordReset).where(PasswordReset.user_id == user.id, PasswordReset.used_at.is_(None)).values(used_at=utc_now()))
    audit(db, user.id, "account.password_changed", "user", user.id)
    db.commit()
    return auth_response(locked)


@router.post("/auth/forgot-password", dependencies=[Depends(check_auth_rate)])
def forgot_password(data: ForgotPasswordInput, db: DbSession):
    delivery = get_mail_delivery()
    # The response is identical for existing, blocked and unknown accounts. The local
    # delivery adapter is inspectable only through admin access or the private CLI.
    user = db.scalar(select(User).where(User.email == str(data.email).casefold(), User.is_active.is_(True)).with_for_update())
    if user:
        token = secrets.token_urlsafe(32)
        now = utc_now()
        db.execute(update(PasswordReset).where(PasswordReset.user_id == user.id, PasswordReset.used_at.is_(None)).values(used_at=now))
        reset = PasswordReset(user_id=user.id, token_hash=sha256(token.encode()).hexdigest(),
                             credential_digest=credential_digest(user),
                             expires_at=now + timedelta(minutes=get_settings().password_reset_expire_minutes))
        db.add(reset)
        link = get_settings().public_web_url.rstrip("/") + "/reset-password?token=" + token
        delivery.deliver(db, recipient=user.email, subject="SaparTravel — восстановление пароля / Password reset / Құпиясөзді қалпына келтіру",
                         body=f"Восстановление пароля / Password reset / Құпиясөзді қалпына келтіру:\n{link}\n\n"
                              f"Ссылка одноразовая, срок {get_settings().password_reset_expire_minutes} мин. / One use only. Ignore if you did not request it.", reset=reset)
        audit(db, user.id, "account.password_reset_requested", "user", user.id)
        db.commit()
    return {"message": "Если аккаунт существует, инструкция будет отправлена на его адрес.", "code": "reset_requested",
            "delivery": "email" if get_settings().resolved_mail_mode == "smtp" else "local"}


@router.post("/auth/reset-password", dependencies=[Depends(check_auth_rate)])
def reset_password(data: ResetPasswordInput, db: DbSession):
    digest = sha256(data.token.encode()).hexdigest()
    reset = db.scalar(select(PasswordReset).where(PasswordReset.token_hash == digest))
    invalid = HTTPException(422, "Ссылка недействительна или срок её действия истёк.")
    if not reset:
        raise invalid
    # Serialize all resets and password changes on the same user row. A concurrent
    # second redemption observes used_at after the first transaction commits.
    user = db.scalar(select(User).where(User.id == reset.user_id).with_for_update().execution_options(populate_existing=True))
    db.refresh(reset, with_for_update=True)
    if reset.used_at is not None or aware(reset.expires_at) <= utc_now() or not user or not user.is_active or reset.credential_digest != credential_digest(user):
        raise invalid
    user.password_hash = password_hash.hash(data.new_password)
    reset.used_at = utc_now()
    db.execute(update(PasswordReset).where(PasswordReset.user_id == user.id, PasswordReset.used_at.is_(None)).values(used_at=utc_now()))
    audit(db, user.id, "account.password_reset", "user", user.id)
    db.commit()
    return {"message": "Пароль обновлён. Войдите с новым паролем.", "code": "password_reset"}


@router.get("/admin/demo-mailbox")
def demo_mailbox(user: Admin, db: DbSession, recipient: str | None = Query(default=None, max_length=254), limit: int = Query(default=30, ge=1, le=100)):
    if not get_settings().demo_mailbox_enabled or get_settings().environment == "production":
        raise HTTPException(404, "Демонстрационный почтовый ящик отключён.")
    query = select(DemoEmail).order_by(DemoEmail.created_at.desc()).limit(limit)
    if recipient:
        query = query.where(DemoEmail.recipient == recipient.casefold())
    audit(db, user.id, "mailbox.read", "demo_email", details={"recipient_filter": bool(recipient)})
    rows = db.scalars(query).all()
    db.commit()
    return {"items": [{"id": item.id, "recipient": item.recipient, "subject": item.subject,
                       "body": item.body, "created_at": item.created_at.isoformat()} for item in rows]}


@router.get("/admin/mail-delivery")
def mail_delivery_status(user: Admin, db: DbSession):
    settings = get_settings()
    counts = dict(db.execute(select(OutboundEmail.state, func.count()).group_by(OutboundEmail.state)).all())
    rows = db.scalars(select(OutboundEmail).order_by(OutboundEmail.created_at.desc()).limit(30)).all()
    return {"mode": settings.resolved_mail_mode, "from_address": str(settings.smtp_from_email) if settings.smtp_from_email else None,
            "local_mailbox_enabled": settings.demo_mailbox_enabled and settings.environment != "production",
            "counts": {state: counts.get(state, 0) for state in ("pending", "sent", "failed", "cancelled")},
            "items": [{"id": row.id, "recipient": row.recipient, "subject": row.subject,
                       "state": row.state, "attempts": row.attempts, "error_code": row.error_code,
                       "created_at": row.created_at.isoformat(), "sent_at": row.sent_at.isoformat() if row.sent_at else None}
                      for row in rows]}


@router.post("/admin/mail-delivery/{message_id}/retry")
def retry_mail(message_id: str, user: Admin, db: DbSession):
    if get_settings().resolved_mail_mode != "smtp":
        raise HTTPException(503, "Почтовый сервис не настроен.")
    row = db.scalar(select(OutboundEmail).where(OutboundEmail.id == message_id).with_for_update())
    if row is None:
        raise HTTPException(404, "Письмо не найдено.")
    if row.state != "failed" or not usable_reset(db, row.password_reset):
        raise HTTPException(409, "Повторная отправка этого письма недоступна. Запросите новую ссылку.")
    row.state, row.attempts, row.error_code, row.next_attempt_at = "pending", 0, "", utc_now()
    audit(db, user.id, "mail.retry", "outbound_email", row.id)
    db.commit()
    return {"state": "pending"}
