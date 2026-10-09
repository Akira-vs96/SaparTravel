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
        jwt_secret="pytest-secret-long-and-varied-47c90b126",
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
