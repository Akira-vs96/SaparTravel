import string

import pytest
from pydantic import ValidationError

from app.core.config import Settings, get_settings
from app.core import security


def test_secrets_and_database_configuration():
    with pytest.raises(ValidationError):
        Settings(jwt_secret="short")
    with pytest.raises(ValidationError):
        Settings(jwt_secret="x" * 64)
    with pytest.raises(ValidationError):
        Settings(environment="production", database_url="sqlite:///wrong.db")
    settings = Settings(admin_email="", admin_password="")
    assert settings.admin_email is None and settings.admin_password is None
    with pytest.raises(ValidationError):
        Settings(admin_email="admin@example.com", admin_password="")


@pytest.mark.parametrize("scheme", ["postgres://", "postgresql://"])
def test_standard_postgres_urls_use_psycopg(scheme):
    settings = Settings(
        database_url=f"{scheme}postgres@example.com/postgres",
        jwt_secret=string.ascii_letters + string.digits + string.punctuation,
    )
    assert settings.database_url == "postgresql+psycopg://postgres@example.com/postgres"


def test_authentication_rate_limit(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "auth_rate_limit", 1)
    security._auth_attempts.clear()
    payload = {"email": "unknown@example.com", "password": "unknown-password"}
    assert client.post("/api/v1/auth/login", json=payload).status_code == 401
    second = client.post("/api/v1/auth/login", json=payload)
    assert second.status_code == 429
    assert second.headers["retry-after"] == "60"
    security._auth_attempts.clear()


def test_smtp_configuration_requires_sender_credentials_and_encryption():
    base = {"database_url": "postgresql+psycopg://test@localhost/test", "auth_rate_limit": 20,
            "environment": "production", "mail_delivery_mode": "smtp", "smtp_host": "mail.example.com",
            "smtp_from_email": "support@example.com", "smtp_username": "", "smtp_password": None}
    assert Settings(**base).resolved_mail_mode == "smtp"
    with pytest.raises(ValidationError, match="Unencrypted SMTP"):
        Settings(**{**base, "smtp_security": "none"})
    with pytest.raises(ValidationError, match="SMTP_HOST and SMTP_FROM_EMAIL"):
        Settings(**{**base, "smtp_from_email": None})
    with pytest.raises(ValidationError, match="configured together"):
        Settings(**{**base, "smtp_username": "sender"})


def test_recovery_urls_cannot_contain_credentials_queries_or_fragments():
    for url in ("https://user:pass@example.com", "https://example.com?redirect=other", "https://example.com#fragment", "https://"):
        with pytest.raises(ValidationError, match="PUBLIC_WEB_URL"):
            Settings(public_web_url=url)


def test_smtp_configuration_errors_do_not_echo_passwords():
    value = "redaction-check-password-2026"
    with pytest.raises(ValidationError) as error:
        Settings(mail_delivery_mode="smtp", smtp_host="mail.example.com", smtp_from_email="support@example.com",
                 smtp_username="", smtp_password=value)
    assert value not in str(error.value)
