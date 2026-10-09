from functools import lru_cache

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

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @field_validator("admin_email", "admin_password", mode="before")
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
        return self

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
