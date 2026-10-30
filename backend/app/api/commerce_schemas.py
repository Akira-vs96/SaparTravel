from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal
from pydantic import Field, field_validator, model_validator

from app.api.schemas import Category, InputModel, Money


class PaymentInput(InputModel):
    card_number: str = Field(min_length=1, max_length=32)
    holder_name: str = Field(min_length=2, max_length=120)
    expiry_month: int = Field(ge=1, le=12, strict=True)
    expiry_year: int = Field(ge=2000, le=2200, strict=True)
    cvc: str = Field(min_length=3, max_length=4, pattern=r"^\d{3,4}$")


class ConfirmationInput(InputModel):
    outcome: Literal["success", "failure", "expired", "cancelled"]


class CancellationInput(InputModel):
    reason: str = Field(default="Отмена путешественником", max_length=500)


class RefundInput(InputModel):
    amount: Annotated[Decimal, Field(gt=0, le=100000000, max_digits=12, decimal_places=2)]
    reason: str = Field(min_length=3, max_length=500)
    scenario: Literal["success", "temporary_failure", "processing"] = "success"


class PromoInput(InputModel):
    code: str = Field(min_length=3, max_length=40, pattern=r"^[A-Za-z0-9_-]+$")
    kind: Literal["percent", "fixed"]
    value: Money
    min_amount: Decimal = Field(default=Decimal(0), ge=0, le=100000000, decimal_places=2)
    starts_at: datetime
    ends_at: datetime
    usage_limit: int = Field(default=100, ge=1, le=1000000)
    per_user_limit: int = Field(default=1, ge=1, le=1000)
    is_active: bool = True
    experience_id: str | None = None
    category: Category | None = None

    @field_validator("starts_at", "ends_at")
    @classmethod
    def require_timezone(cls, value):
        if value.tzinfo is None:
            raise ValueError("Укажите часовой пояс")
        return value

    @model_validator(mode="after")
    def rules(self):
        if self.ends_at <= self.starts_at or (self.kind == "percent" and self.value > 100):
            raise ValueError("Некорректные сроки или процент скидки")
        return self
