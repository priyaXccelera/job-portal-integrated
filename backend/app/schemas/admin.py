"""Request bodies for the admin API."""

from __future__ import annotations

from typing import Any

from pydantic import Field, field_validator, model_validator

from app.models.enums import CompanyStatus, JobStatus, ReportStatus, ReviewStatus
from app.schemas.common import CamelModel

REASON_MAX = 1000


def _clean_reason(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value or None


class CompanyStatusUpdate(CamelModel):
    status: CompanyStatus
    reason: str | None = Field(default=None, max_length=REASON_MAX)

    @model_validator(mode="after")
    def _reason_required(self) -> CompanyStatusUpdate:
        self.reason = _clean_reason(self.reason)
        if self.status in (CompanyStatus.REJECTED, CompanyStatus.BLOCKED) and not self.reason:
            raise ValueError("reason is required when rejecting or blocking a company")
        return self


class CompanyVerifyUpdate(CamelModel):
    verified: bool


class CreditAdjustment(CamelModel):
    amount: int = Field(description="Credits to add; negative values deduct", ge=-1_000_000, le=1_000_000)
    reason: str = Field(min_length=1, max_length=255)

    @field_validator("amount")
    @classmethod
    def _non_zero(cls, value: int) -> int:
        if value == 0:
            raise ValueError("amount must be non-zero")
        return value

    @field_validator("reason")
    @classmethod
    def _strip_reason(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("reason must not be blank")
        return value


class QuotaUpdate(CamelModel):
    job_quota: int = Field(ge=0, le=1_000_000)


class JobStatusUpdate(CamelModel):
    status: JobStatus
    reason: str | None = Field(default=None, max_length=REASON_MAX)

    @model_validator(mode="after")
    def _check(self) -> JobStatusUpdate:
        self.reason = _clean_reason(self.reason)
        if self.status not in (JobStatus.ACTIVE, JobStatus.REJECTED, JobStatus.CLOSED):
            raise ValueError("status must be one of ACTIVE, REJECTED, CLOSED")
        if self.status in (JobStatus.REJECTED, JobStatus.CLOSED) and not self.reason:
            raise ValueError("reason is required when rejecting or taking down a job")
        return self


class JobReportUpdate(CamelModel):
    status: ReportStatus
    takedown: bool = False
    reason: str | None = Field(default=None, max_length=REASON_MAX)

    @model_validator(mode="after")
    def _check(self) -> JobReportUpdate:
        self.reason = _clean_reason(self.reason)
        if self.takedown and self.status != ReportStatus.RESOLVED:
            raise ValueError("takedown is only allowed when resolving a report")
        return self


class ReviewModeration(CamelModel):
    status: ReviewStatus

    @field_validator("status")
    @classmethod
    def _decision(cls, value: ReviewStatus) -> ReviewStatus:
        if value == ReviewStatus.PENDING:
            raise ValueError("status must be APPROVED or REJECTED")
        return value


class UserBlock(CamelModel):
    reason: str = Field(min_length=1, max_length=REASON_MAX)

    @field_validator("reason")
    @classmethod
    def _strip_reason(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("reason must not be blank")
        return value


# ----------------------------------------------------------------------------- master data


def _clean_name(value: str) -> str:
    value = " ".join(value.split())
    if not value:
        raise ValueError("name must not be blank")
    return value


def _clean_list(values: list[str]) -> list[str]:
    seen: set[str] = set()
    cleaned: list[str] = []
    for raw in values:
        item = " ".join(str(raw).split())
        if item and item.lower() not in seen:
            seen.add(item.lower())
            cleaned.append(item)
    return cleaned


class MasterBase(CamelModel):
    name: str = Field(min_length=1, max_length=150)

    @field_validator("name")
    @classmethod
    def _name(cls, value: str) -> str:
        return _clean_name(value)


class NameOnlyIn(MasterBase):
    pass


class SkillIn(MasterBase):
    synonyms: list[str] = Field(default_factory=list, max_length=50)
    is_active: bool = True

    @field_validator("synonyms")
    @classmethod
    def _synonyms(cls, value: list[str]) -> list[str]:
        if any(len(s) > 150 for s in value):
            raise ValueError("each synonym must be at most 150 characters")
        return _clean_list(value)


class LocationIn(MasterBase):
    state: str | None = Field(default=None, max_length=150)
    country: str = Field(default="India", min_length=1, max_length=100)

    @field_validator("state")
    @classmethod
    def _state(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = " ".join(value.split())
        return value or None

    @field_validator("country")
    @classmethod
    def _country(cls, value: str) -> str:
        return _clean_name(value)


class DegreeIn(MasterBase):
    specializations: list[str] = Field(default_factory=list, max_length=100)

    @field_validator("specializations")
    @classmethod
    def _specs(cls, value: list[str]) -> list[str]:
        if any(len(s) > 150 for s in value):
            raise ValueError("each specialization must be at most 150 characters")
        return _clean_list(value)


class NoticePeriodIn(MasterBase):
    name: str = Field(min_length=1, max_length=100)
    days: int = Field(default=0, ge=0, le=365)


MASTER_SCHEMAS: dict[str, type[CamelModel]] = {
    "skills": SkillIn,
    "industries": NameOnlyIn,
    "departments": NameOnlyIn,
    "role-categories": NameOnlyIn,
    "locations": LocationIn,
    "degrees": DegreeIn,
    "notice-periods": NoticePeriodIn,
}


def validate_master_payload(type_key: str, payload: Any) -> dict[str, Any]:
    """Validate ``payload`` for a master type; raises pydantic.ValidationError on bad input."""
    model = MASTER_SCHEMAS[type_key].model_validate(payload)
    return model.model_dump()
