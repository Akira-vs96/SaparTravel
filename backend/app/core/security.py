from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from hmac import compare_digest
from math import isfinite
from uuid import uuid4
from threading import Lock
from time import monotonic
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pwdlib import PasswordHash
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db import get_db
from app.domain.models import User
from app.domain.engagement import RevokedAccessToken, UserAccessBoundary

password_hash = PasswordHash.recommended()
# Valid hash also used for unknown accounts to reduce account timing disclosure.
DUMMY_HASH = password_hash.hash("unusable-timing-placeholder-password")
bearer = HTTPBearer(auto_error=False)
DbSession = Annotated[Session, Depends(get_db)]
_auth_attempts: dict[str, deque] = defaultdict(deque)
_auth_lock = Lock()


def check_auth_rate(request: Request) -> None:
    limit = get_settings().auth_rate_limit
    if limit == 0:
        return
    key = request.client.host if request.client else "unknown"
    now = monotonic()
    with _auth_lock:
        # Bound memory, dropping only expired entries.
        if len(_auth_attempts) > 10000:
            for old_key in list(_auth_attempts):
                if not _auth_attempts[old_key] or _auth_attempts[old_key][-1] < now - 60:
                    del _auth_attempts[old_key]
            if len(_auth_attempts) > 10000 and key not in _auth_attempts:
                raise HTTPException(429, "Слишком много попыток. Повторите через минуту.", headers={"Retry-After": "60"})
        attempts = _auth_attempts[key]
        while attempts and attempts[0] < now - 60:
            attempts.popleft()
        if len(attempts) >= limit:
            raise HTTPException(429, "Слишком много попыток. Повторите через минуту.", headers={"Retry-After": "60"})
        attempts.append(now)


def credential_digest(user: User) -> str:
    return sha256(user.password_hash.encode()).hexdigest()


def token_for(user: User) -> str:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {"sub": user.id, "jti": str(uuid4()), "issued": now.timestamp(), "cred": credential_digest(user), "iat": now, "exp": now + timedelta(minutes=settings.access_token_expire_minutes),
         "iss": "sapartravel", "aud": "sapartravel-api"},
        settings.jwt_secret.get_secret_value(), algorithm="HS256",
    )


def current_user(request: Request, db: DbSession, credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]) -> User:
    error = HTTPException(401, "Войдите в аккаунт, чтобы продолжить.", headers={"WWW-Authenticate": "Bearer"})
    if credentials is None:
        raise error
    try:
        payload = jwt.decode(
            credentials.credentials, get_settings().jwt_secret.get_secret_value(), algorithms=["HS256"],
            issuer="sapartravel", audience="sapartravel-api", options={"require": ["sub", "jti", "issued", "cred", "exp", "iat", "iss", "aud"]},
        )
        user = db.get(User, payload["sub"])
    except (jwt.InvalidTokenError, TypeError, ValueError):
        raise error from None
    if user is None or not user.is_active:
        raise error
    credential = payload["cred"]
    if not isinstance(credential, str) or not credential.isascii() or not compare_digest(credential_digest(user), credential):
        raise error
    issued = payload["issued"]
    if type(issued) not in (int, float) or not isfinite(issued):
        raise error
    if db.get(RevokedAccessToken, payload["jti"]) is not None:
        raise error
    boundary = db.get(UserAccessBoundary, user.id)
    if boundary:
        invalidated_at = boundary.invalidated_at
        if invalidated_at.tzinfo is None:
            invalidated_at = invalidated_at.replace(tzinfo=timezone.utc)
        if issued <= invalidated_at.timestamp():
            raise error
    request.state.auth_payload = payload
    return user


CurrentUser = Annotated[User, Depends(current_user)]


def manager(user: CurrentUser) -> User:
    if user.role not in ("vendor", "admin"):
        raise HTTPException(403, "Доступно только организатору или администратору.")
    return user


def admin(user: CurrentUser) -> User:
    if user.role != "admin":
        raise HTTPException(403, "Доступно только администратору.")
    return user


Manager = Annotated[User, Depends(manager)]
Admin = Annotated[User, Depends(admin)]
