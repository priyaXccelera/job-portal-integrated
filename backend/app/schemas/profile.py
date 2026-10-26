"""Request bodies for the seeker profile endpoints."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Annotated, Any
from urllib.parse import urlparse

from pydantic import AliasChoices, Field, field_validator, model_validator

from app.schemas.common import CamelModel, EmploymentType, JobType, Visibility, WorkStatus

MOBILE_PATTERN = r"^\+?[0-9]{10,15}$"
MAX_CTC = Decimal("999999999999")

Ctc = Annotated[Decimal, Field(ge=0, le=MAX_CTC, decimal_places=2)]


def validate_url(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme not in ("http", "https") or not parsed.netloc or " " in value:
        raise ValueError("must be a valid http(s) URL")
    return value


class TrimModel(CamelModel):
    """Strips whitespace from strings; blank strings become None (-> required fields fail)."""

    @field_validator("*", mode="before")
    @classmethod
    def _strip(cls, value: Any) -> Any:
        if isinstance(value, str):
            value = value.strip()
            return value or None
        return value


def _clean_list(values: list[str] | None, limit: int = 20, max_len: int = 150) -> list[str] | None:
    if values is None:
        return None
    out: list[str] = []
    seen: set[str] = set()
    for raw in values:
        item = (raw or "").strip()
        if not item:
            continue
        if len(item) > max_len:
            raise ValueError(f"items must be at most {max_len} characters")
        if item.casefold() not in seen:
            seen.add(item.casefold())
            out.append(item)
    if len(out) > limit:
        raise ValueError(f"at most {limit} items allowed")
    return out


# --------------------------------------------------------------------------- skills
class SkillItem(TrimModel):
    skill_id: uuid.UUID | None = None
    name: str | None = Field(None, max_length=150)
    years_of_experience: Decimal | None = Field(None, ge=0, le=60, decimal_places=1)

    @model_validator(mode="after")
    def _need_identifier(self) -> SkillItem:
        if self.skill_id is None and not self.name:
            raise ValueError("either skillId or name is required")
        return self


class SkillsReplace(CamelModel):
    skills: list[SkillItem] = Field(max_length=100)


# --------------------------------------------------------------------------- basics
class ProfileUpdate(TrimModel):
    name: str | None = Field(None, max_length=200)
    email: str | None = Field(None, max_length=320)
    mobile: str | None = Field(None, pattern=MOBILE_PATTERN)
    headline: str | None = Field(None, max_length=255)
    summary: str | None = Field(None, max_length=5000)
    current_location: str | None = Field(None, max_length=150)
    preferred_locations: list[str] | None = None
    dob: date | None = None
    gender: str | None = Field(None, max_length=32)
    experience_years: int | None = Field(None, ge=0, le=60)
    experience_months: int | None = Field(None, ge=0, le=11)
    notice_period: str | None = Field(None, max_length=100)
    current_ctc: Ctc | None = None
    expected_ctc: Ctc | None = None
    work_status: WorkStatus | None = None
    skills: list[SkillItem] | None = Field(None, max_length=100)

    @field_validator("dob")
    @classmethod
    def _dob_not_future(cls, value: date | None) -> date | None:
        if value is not None and value > datetime.now(timezone.utc).date():
            raise ValueError("dob cannot be in the future")
        return value

    @field_validator("preferred_locations")
    @classmethod
    def _locations(cls, value: list[str] | None) -> list[str] | None:
        return _clean_list(value)


# --------------------------------------------------------------------------- child records
class EmploymentCreate(TrimModel):
    company_name: str = Field(max_length=200)
    designation: str = Field(max_length=200)
    start_date: date | None = None
    end_date: date | None = None
    is_current: bool = False
    description: str | None = Field(None, max_length=5000)
    location: str | None = Field(None, max_length=150)


class EmploymentUpdate(TrimModel):
    company_name: str | None = Field(None, max_length=200)
    designation: str | None = Field(None, max_length=200)
    start_date: date | None = None
    end_date: date | None = None
    is_current: bool | None = None
    description: str | None = Field(None, max_length=5000)
    location: str | None = Field(None, max_length=150)


class EducationCreate(TrimModel):
    degree: str = Field(max_length=150)
    specialization: str | None = Field(None, max_length=150)
    institute: str | None = Field(None, max_length=200)
    start_year: int | None = Field(None, ge=1950, le=2100)
    end_year: int | None = Field(None, ge=1950, le=2100)
    grade: str | None = Field(None, max_length=50)


class EducationUpdate(TrimModel):
    degree: str | None = Field(None, max_length=150)
    specialization: str | None = Field(None, max_length=150)
    institute: str | None = Field(None, max_length=200)
    start_year: int | None = Field(None, ge=1950, le=2100)
    end_year: int | None = Field(None, ge=1950, le=2100)
    grade: str | None = Field(None, max_length=50)


class _UrlMixin:
    @staticmethod
    def check(value: str | None) -> str | None:
        return validate_url(value) if value else value


class ProjectCreate(TrimModel):
    title: str = Field(max_length=200)
    description: str | None = Field(None, max_length=5000)
    url: str | None = Field(None, max_length=500)
    start_date: date | None = None
    end_date: date | None = None
    skills: list[str] = Field(default_factory=list)

    @field_validator("url")
    @classmethod
    def _url(cls, value: str | None) -> str | None:
        return _UrlMixin.check(value)

    @field_validator("skills")
    @classmethod
    def _skills(cls, value: list[str]) -> list[str]:
        return _clean_list(value, limit=30, max_len=100) or []


class ProjectUpdate(TrimModel):
    title: str | None = Field(None, max_length=200)
    description: str | None = Field(None, max_length=5000)
    url: str | None = Field(None, max_length=500)
    start_date: date | None = None
    end_date: date | None = None
    skills: list[str] | None = None

    @field_validator("url")
    @classmethod
    def _url(cls, value: str | None) -> str | None:
        return _UrlMixin.check(value)

    @field_validator("skills")
    @classmethod
    def _skills(cls, value: list[str] | None) -> list[str] | None:
        return _clean_list(value, limit=30, max_len=100)


class CertificationCreate(TrimModel):
    name: str = Field(max_length=200)
    issuer: str | None = Field(None, max_length=200)
    issued_date: date | None = None
    expiry_date: date | None = None
    credential_url: str | None = Field(None, max_length=500)

    @field_validator("credential_url")
    @classmethod
    def _url(cls, value: str | None) -> str | None:
        return _UrlMixin.check(value)


class CertificationUpdate(TrimModel):
    name: str | None = Field(None, max_length=200)
    issuer: str | None = Field(None, max_length=200)
    issued_date: date | None = None
    expiry_date: date | None = None
    credential_url: str | None = Field(None, max_length=500)

    @field_validator("credential_url")
    @classmethod
    def _url(cls, value: str | None) -> str | None:
        return _UrlMixin.check(value)


# --------------------------------------------------------------------------- languages / links / prefs
class LanguageItem(TrimModel):
    name: str = Field(max_length=80)
    proficiency: str | None = Field(None, max_length=50)


class LanguagesBody(CamelModel):
    languages: list[LanguageItem] = Field(max_length=20)


class OnlineProfilesUpdate(TrimModel):
    linkedin: str | None = Field(None, max_length=500)
    github: str | None = Field(None, max_length=500)
    portfolio: str | None = Field(None, max_length=500)

    @field_validator("linkedin", "github", "portfolio")
    @classmethod
    def _url(cls, value: str | None) -> str | None:
        return _UrlMixin.check(value)


class CareerPreferencesUpdate(TrimModel):
    desired_industry: str | None = Field(None, max_length=150)
    desired_department: str | None = Field(
        None,
        max_length=150,
        validation_alias=AliasChoices("desiredDepartment", "functionalArea", "desired_department"),
    )
    desired_role_category: str | None = Field(None, max_length=150)
    desired_job_type: JobType | None = None
    desired_employment_type: EmploymentType | None = None
    desired_shift: str | None = Field(None, max_length=32)
    desired_locations: list[str] | None = None

    @field_validator("desired_locations")
    @classmethod
    def _locations(cls, value: list[str] | None) -> list[str] | None:
        return _clean_list(value)


class PrivacyUpdate(CamelModel):
    visibility: Visibility | None = None
    actively_looking: bool | None = None

    @model_validator(mode="after")
    def _non_null(self) -> PrivacyUpdate:
        for field in self.model_fields_set:
            if getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null")
        return self


class HiddenCompanyCreate(CamelModel):
    company_id: uuid.UUID
