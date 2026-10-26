"""Request bodies for job-seeker actions."""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

from pydantic import Field, field_validator

from app.schemas.common import AlertFrequency, CamelModel, InterviewResponse, ReportReason


def _clean_str(value: Any) -> Any:
    return value.strip() if isinstance(value, str) else value


class AnswerIn(CamelModel):
    question_id: uuid.UUID
    answer: str | None = Field(default=None, max_length=5000)


class ApplyRequest(CamelModel):
    resume_id: uuid.UUID | None = None
    cover_note: str | None = Field(default=None, max_length=5000)
    answers: list[AnswerIn] = Field(default_factory=list, max_length=50)
    expected_ctc: Decimal | None = Field(default=None, ge=0, le=Decimal("999999999999"))
    notice_period: str | None = Field(default=None, max_length=100)


class WithdrawRequest(CamelModel):
    reason: str | None = Field(default=None, max_length=1000)


class InterviewResponseRequest(CamelModel):
    response: InterviewResponse
    note: str | None = Field(default=None, max_length=2000)


def _normalise_keywords(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (list, tuple)):
        value = ", ".join(str(v).strip() for v in value if str(v).strip())
    if isinstance(value, str):
        value = value.strip()
        return value or None
    return value


def _normalise_locations(value: Any) -> Any:
    if value is None:
        return []
    if isinstance(value, str):
        value = [v for v in value.split(",")]
    if isinstance(value, (list, tuple)):
        cleaned: list[str] = []
        for item in value:
            text = str(item).strip()
            if text and text.casefold() not in {c.casefold() for c in cleaned}:
                cleaned.append(text)
        return cleaned
    return value


class JobAlertIn(CamelModel):
    """Full alert definition (POST / PUT)."""

    name: str | None = Field(default=None, max_length=150)
    keywords: str | None = Field(default=None, max_length=500)
    locations: list[str] = Field(default_factory=list, max_length=20)
    experience: Decimal | None = Field(default=None, ge=0, le=60)
    salary_min: Decimal | None = Field(default=None, ge=0, le=Decimal("999999999999"))
    frequency: AlertFrequency = AlertFrequency.daily

    @field_validator("keywords", mode="before")
    @classmethod
    def _keywords(cls, v: Any) -> Any:
        return _normalise_keywords(v)

    @field_validator("locations", mode="before")
    @classmethod
    def _locations(cls, v: Any) -> Any:
        return _normalise_locations(v)

    @field_validator("name", mode="before")
    @classmethod
    def _name(cls, v: Any) -> Any:
        v = _clean_str(v)
        return v or None

    @field_validator("locations")
    @classmethod
    def _location_len(cls, v: list[str]) -> list[str]:
        if any(len(item) > 100 for item in v):
            raise ValueError("Each location must be at most 100 characters")
        return v


class JobAlertPatch(CamelModel):
    """Partial alert update (PATCH): only fields present in the body are applied."""

    name: str | None = Field(default=None, max_length=150)
    keywords: str | None = Field(default=None, max_length=500)
    locations: list[str] | None = Field(default=None, max_length=20)
    experience: Decimal | None = Field(default=None, ge=0, le=60)
    salary_min: Decimal | None = Field(default=None, ge=0, le=Decimal("999999999999"))
    frequency: AlertFrequency | None = None
    is_paused: bool | None = None

    @field_validator("keywords", mode="before")
    @classmethod
    def _keywords(cls, v: Any) -> Any:
        return _normalise_keywords(v)

    @field_validator("locations", mode="before")
    @classmethod
    def _locations(cls, v: Any) -> Any:
        return None if v is None else _normalise_locations(v)

    @field_validator("name", mode="before")
    @classmethod
    def _name(cls, v: Any) -> Any:
        v = _clean_str(v)
        return v or None


class ReviewIn(CamelModel):
    rating: int = Field(ge=1, le=5)
    title: str | None = Field(default=None, max_length=200)
    body: str | None = Field(default=None, max_length=5000)

    @field_validator("title", "body", mode="before")
    @classmethod
    def _strip(cls, v: Any) -> Any:
        v = _clean_str(v)
        return v or None


class JobReportIn(CamelModel):
    reason: ReportReason
    details: str | None = Field(default=None, max_length=2000)

    @field_validator("details", mode="before")
    @classmethod
    def _strip(cls, v: Any) -> Any:
        v = _clean_str(v)
        return v or None


class SavedSearchIn(CamelModel):
    name: str = Field(min_length=1, max_length=150)
    query: str | None = Field(default=None, max_length=500)
    filters: dict[str, Any] | None = None

    @field_validator("name", mode="before")
    @classmethod
    def _strip_name(cls, v: Any) -> Any:
        return _clean_str(v)

    @field_validator("query", mode="before")
    @classmethod
    def _strip_query(cls, v: Any) -> Any:
        v = _clean_str(v)
        return v or None
