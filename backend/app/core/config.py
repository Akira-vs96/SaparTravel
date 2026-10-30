from functools import lru_cache
from typing import Literal
from urllib.parse import urlsplit

from pydantic import EmailStr, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "SaparTravel API"
    environment: str = "development"
    api_prefix: str = "/api/v1"
    log_level: str = "INFO"
    cors_origins: str = "http://localhost:5173"
    database_url: str
    jwt_secret: SecretStr
    access_token_expire_minutes: int = Field(default=120, ge=5, le=10080)
    seed_demo_data: bool = False
    admin_email: EmailStr | None = None
    admin_password: SecretStr | None = None
    auth_rate_limit: int = Field(default=20, ge=0, le=1000)
    reservation_minutes: int = Field(default=15, ge=1, le=120)
    payment_demo_enabled: bool = False
    demo_mailbox_enabled: bool = False
    demo_private_data: bool = False
    password_reset_expire_minutes: int = Field(default=30, ge=5, le=120)
    public_web_url: str = "http://localhost:5173"
    support_calendar_file: str = ""
    mail_delivery_mode: Literal["auto", "smtp", "local", "disabled"] = "auto"
    smtp_host: str = ""
    smtp_port: int = Field(default=587, ge=1, le=65535)
    smtp_from_email: EmailStr | None = None
    smtp_username: str = ""
    smtp_password: SecretStr | None = None
    smtp_security: Literal["starttls", "ssl", "none"] = "starttls"
    smtp_timeout_seconds: int = Field(default=10, ge=1, le=30)
    mail_max_attempts: int = Field(default=5, ge=1, le=20)
    mail_retry_seconds: int = Field(default=60, ge=1, le=3600)

    model_config = SettingsConfigDict(env_file=".env", extra="ignore", hide_input_in_errors=True)

    @field_validator("admin_email", "admin_password", "smtp_from_email", "smtp_password", mode="before")
    @classmethod
    def optional_credentials(cls, value):
        return None if value == "" else value

    @field_validator("database_url", mode="before")
    @classmethod
    def normalize_postgres_url(cls, value):
        if isinstance(value, str):
            for prefix in ("postgres://", "postgresql://"):
                if value.startswith(prefix):
                    return "postgresql+psycopg://" + value[len(prefix):]
        return value

    @field_validator("jwt_secret")
    @classmethod
    def validate_secret(cls, value: SecretStr) -> SecretStr:
        secret = value.get_secret_value()
        if len(secret) < 32 or secret.lower() in {
            "change-me-to-a-long-random-secret", "your-secret-key-at-least-32-characters",
        } or len(set(secret)) < 8:
            raise ValueError("JWT_SECRET must contain at least 32 random characters")
        return value

    @model_validator(mode="after")
    def validate_environment(self):
        if not self.database_url.startswith("postgresql+psycopg://") and not (
            self.environment == "testing" and self.database_url.startswith("sqlite")
        ):
            raise ValueError("DATABASE_URL must use postgresql+psycopg://")
        if bool(self.admin_email) != bool(self.admin_password):
            raise ValueError("ADMIN_EMAIL and ADMIN_PASSWORD must be set together")
        if self.admin_password and len(self.admin_password.get_secret_value()) < 10:
            raise ValueError("ADMIN_PASSWORD must contain at least 10 characters")
        if self.auth_rate_limit == 0 and self.environment != "testing":
            raise ValueError("Authentication rate limiting can only be disabled in tests")
        if self.environment == "production" and (self.demo_private_data or self.demo_mailbox_enabled):
            raise ValueError("Private demonstration data and mailbox are disabled in production")
        web = urlsplit(self.public_web_url)
        if web.scheme not in {"http", "https"} or not web.hostname or web.username or web.password or web.query or web.fragment:
            raise ValueError("PUBLIC_WEB_URL must use http or https")
        if self.mail_delivery_mode == "local" and self.environment == "production":
            raise ValueError("Local mail delivery is disabled in production")
        if self.mail_delivery_mode == "smtp" or (self.mail_delivery_mode == "auto" and (self.smtp_host or self.smtp_from_email)):
            if not self.smtp_host or not self.smtp_from_email:
                raise ValueError("SMTP_HOST and SMTP_FROM_EMAIL are required for SMTP delivery")
            if bool(self.smtp_username) != bool(self.smtp_password):
                raise ValueError("SMTP_USERNAME and SMTP_PASSWORD must be configured together")
            if self.smtp_security == "none" and not (self.environment != "production" and self.smtp_host in {"127.0.0.1", "localhost", "::1"}):
                raise ValueError("Unencrypted SMTP is allowed only on a local non-production test server")
        return self

    @property
    def resolved_mail_mode(self) -> str:
        if self.mail_delivery_mode != "auto":
            return self.mail_delivery_mode
        if self.smtp_host and self.smtp_from_email:
            return "smtp"
        if self.environment == "testing" or (self.environment != "production" and self.demo_mailbox_enabled):
            return "local"
        return "disabled"

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
