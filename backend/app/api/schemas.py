from datetime import date
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, HttpUrl, StringConstraints, field_validator, model_validator

Language = Literal["ru", "kk", "en"]
Role = Literal["traveler", "vendor", "admin"]
Category = Literal["Nature", "Culture", "Adventure", "Food", "Beach", "City"]
Continent = Literal["Europe", "Asia", "Africa", "North America", "South America", "Oceania"]
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=120)]
Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=180)]
Description = Annotated[str, StringConstraints(strip_whitespace=True, min_length=20, max_length=10000)]
Money = Annotated[Decimal, Field(ge=1, le=1000000, max_digits=12, decimal_places=2)]
ShortText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300)]


class InputModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RegisterInput(InputModel):
    name: Name
    email: EmailStr
    password: str = Field(min_length=10, max_length=128)


class LoginInput(InputModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class ProfileInput(InputModel):
    name: Name


class BookingInput(InputModel):
    departure_id: str = Field(min_length=1, max_length=36)
    travelers_count: int = Field(ge=1, le=20, strict=True)
    contact_name: Name
    contact_email: EmailStr
    notes: str = Field(default="", max_length=2000)


class ItineraryDay(InputModel):
    day: int = Field(ge=1, le=90)
    title: str = Field(min_length=1, max_length=180)
    description: str = Field(min_length=1, max_length=3000)


class ExperienceInput(InputModel):
    title: Title
    title_en: str = Field(default="", max_length=180)
    title_kk: str = Field(default="", max_length=180)
    description: Description
    description_en: str = Field(default="", max_length=10000)
    description_kk: str = Field(default="", max_length=10000)
    destination_id: str = Field(min_length=1, max_length=36)
    category: Category
    duration_days: int = Field(ge=1, le=90, strict=True)
    price_from: Money
    image_url: HttpUrl
    is_published: bool = True
    tags: list[ShortText] = Field(default_factory=list, max_length=20)
    tags_en: list[ShortText] = Field(default_factory=list, max_length=20)
    tags_kk: list[ShortText] = Field(default_factory=list, max_length=20)
    included: list[ShortText] = Field(default_factory=list, max_length=30)
    included_en: list[ShortText] = Field(default_factory=list, max_length=30)
    included_kk: list[ShortText] = Field(default_factory=list, max_length=30)
    excluded: list[ShortText] = Field(default_factory=list, max_length=30)
    excluded_en: list[ShortText] = Field(default_factory=list, max_length=30)
    excluded_kk: list[ShortText] = Field(default_factory=list, max_length=30)
    itinerary: list[ItineraryDay] = Field(default_factory=list, max_length=90)
    itinerary_en: list[ItineraryDay] = Field(default_factory=list, max_length=90)
    itinerary_kk: list[ItineraryDay] = Field(default_factory=list, max_length=90)


class ExperiencePatch(InputModel):
    title: Title | None = None
    title_en: str | None = Field(default=None, max_length=180)
    title_kk: str | None = Field(default=None, max_length=180)
    description: Description | None = None
    description_en: str | None = Field(default=None, max_length=10000)
    description_kk: str | None = Field(default=None, max_length=10000)
    destination_id: str | None = Field(default=None, min_length=1, max_length=36)
    category: Category | None = None
    duration_days: int | None = Field(default=None, ge=1, le=90, strict=True)
    price_from: Money | None = None
    image_url: HttpUrl | None = None
    is_published: bool | None = None
    tags: list[ShortText] | None = Field(default=None, max_length=20)
    tags_en: list[ShortText] | None = Field(default=None, max_length=20)
    tags_kk: list[ShortText] | None = Field(default=None, max_length=20)
    included: list[ShortText] | None = Field(default=None, max_length=30)
    included_en: list[ShortText] | None = Field(default=None, max_length=30)
    included_kk: list[ShortText] | None = Field(default=None, max_length=30)
    excluded: list[ShortText] | None = Field(default=None, max_length=30)
    excluded_en: list[ShortText] | None = Field(default=None, max_length=30)
    excluded_kk: list[ShortText] | None = Field(default=None, max_length=30)
    itinerary: list[ItineraryDay] | None = Field(default=None, max_length=90)
    itinerary_en: list[ItineraryDay] | None = Field(default=None, max_length=90)
    itinerary_kk: list[ItineraryDay] | None = Field(default=None, max_length=90)

    @model_validator(mode="after")
    def reject_nulls(self):
        if any(getattr(self, key) is None for key in self.model_fields_set):
            raise ValueError("Fields cannot be null; omit unchanged fields")
        return self


class DepartureInput(InputModel):
    start_date: date
    capacity: int = Field(ge=1, le=1000, strict=True)
    price: Money

    @field_validator("start_date")
    @classmethod
    def future_date(cls, value: date) -> date:
        if value <= date.today():
            raise ValueError("Дата начала должна быть позже сегодняшнего дня")
        return value


class BookingStatusInput(InputModel):
    status: Literal["confirmed", "cancelled", "completed"]


class RoleInput(InputModel):
    role: Role


class DestinationInput(InputModel):
    slug: str = Field(min_length=2, max_length=100, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    name: str = Field(min_length=2, max_length=160)
    name_en: str = Field(default="", max_length=160)
    name_kk: str = Field(default="", max_length=160)
    country: str = Field(min_length=2, max_length=120)
    country_en: str = Field(default="", max_length=120)
    country_kk: str = Field(default="", max_length=120)
    continent: Continent
    description: Description
    description_en: str = Field(default="", max_length=10000)
    description_kk: str = Field(default="", max_length=10000)
    image_url: HttpUrl


class DestinationPatch(InputModel):
    name: str | None = Field(default=None, min_length=2, max_length=160)
    name_en: str | None = Field(default=None, max_length=160)
    name_kk: str | None = Field(default=None, max_length=160)
    country: str | None = Field(default=None, min_length=2, max_length=120)
    country_en: str | None = Field(default=None, max_length=120)
    country_kk: str | None = Field(default=None, max_length=120)
    continent: Continent | None = None
    description: Description | None = None
    description_en: str | None = Field(default=None, max_length=10000)
    description_kk: str | None = Field(default=None, max_length=10000)
    image_url: HttpUrl | None = None

    @model_validator(mode="after")
    def reject_nulls(self):
        if any(getattr(self, key) is None for key in self.model_fields_set):
            raise ValueError("Fields cannot be null; omit unchanged fields")
        return self
