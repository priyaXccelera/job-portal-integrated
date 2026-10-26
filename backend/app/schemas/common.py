"""Shared schema base class and re-exported domain enums."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

from app.models.enums import (
    AlertFrequency,
    ApplicationStatus,
    CompanyStatus,
    CompanyType,
    EmploymentType,
    InterviewMode,
    InterviewResponse,
    JobStatus,
    JobType,
    QuestionType,
    ReportReason,
    ReviewStatus,
    UserRole,
    Visibility,
    WorkMode,
    WorkStatus,
)


class CamelModel(BaseModel):
    """Request/response base: camelCase aliases, accepts snake_case too, ORM-friendly."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, from_attributes=True)


__all__ = [
    "AlertFrequency",
    "ApplicationStatus",
    "CamelModel",
    "CompanyStatus",
    "CompanyType",
    "EmploymentType",
    "InterviewMode",
    "InterviewResponse",
    "JobStatus",
    "JobType",
    "QuestionType",
    "ReportReason",
    "ReviewStatus",
    "UserRole",
    "Visibility",
    "WorkMode",
    "WorkStatus",
]
