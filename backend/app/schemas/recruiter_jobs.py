"""Request bodies for recruiter job management, applicant pipeline and interviews."""

from __future__ import annotations

import uuid
from datetime import date as DateType
from datetime import datetime, timezone
from decimal import Decimal
from typing import Annotated

from pydantic import AliasChoices, Field, field_validator, model_validator

from app.schemas.common import (
    ApplicationStatus,
    CamelModel,
    EmploymentType,
    InterviewMode,
    JobStatus,
    JobType,
    QuestionType,
    WorkMode,
)

MAX_QUESTIONS = 20
MAX_SKILLS = 50
MAX_LOCATIONS = 50
BULK_LIMIT = 100


def _clean_list(values: list[str] | None, limit: int, label: str, max_len: int = 150) -> list[str]:
    """Trim, drop blanks, de-duplicate case-insensitively (first spelling wins)."""
    seen: set[str] = set()
    out: list[str] = []
    for raw in values or []:
        value = " ".join(str(raw).split())
        if not value:
            continue
        if len(value) > max_len:
            raise ValueError(f"{label} entries must be at most {max_len} characters")
        key = value.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(value)
    if len(out) > limit:
        raise ValueError(f"At most {limit} {label} are allowed")
    return out


class WalkInDetails(CamelModel):
    venue: str | None = Field(default=None, max_length=500)
    date: DateType | None = None
    time: str | None = Field(default=None, max_length=50)
    contact: str | None = Field(default=None, max_length=200)


class QuestionIn(CamelModel):
    id: uuid.UUID | None = None
    text: str = Field(min_length=1, max_length=1000)
    type: QuestionType = Field(
        default=QuestionType.TEXT, validation_alias=AliasChoices("type", "questionType", "question_type")
    )
    options: list[str] = Field(default_factory=list)
    is_knockout: bool = False
    expected_answer: str | list[str] | None = None
    is_required: bool = True

    @field_validator("text")
    @classmethod
    def _strip_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Question text must not be blank")
        return value

    @model_validator(mode="after")
    def _check_type_rules(self) -> QuestionIn:
        options = _clean_list(self.options, 20, "options", max_len=200)
        expected = self.expected_answer
        if isinstance(expected, str):
            expected = expected.strip() or None
        elif isinstance(expected, list):
            expected = [e.strip() for e in expected if e and e.strip()] or None

        if self.type == QuestionType.MULTIPLE_CHOICE:
            if len(options) < 2:
                raise ValueError("MULTIPLE_CHOICE questions need at least 2 options")
        else:
            options = []

        if self.is_knockout:
            if self.type == QuestionType.TEXT:
                raise ValueError("Knockout is only supported for YES_NO and MULTIPLE_CHOICE questions")
            if expected is None:
                raise ValueError("Knockout questions need an expectedAnswer")

        if expected is not None and self.type == QuestionType.YES_NO:
            if isinstance(expected, list) or expected.upper() not in ("YES", "NO"):
                raise ValueError("expectedAnswer for YES_NO must be YES or NO")
            expected = expected.upper()
        elif expected is not None and self.type == QuestionType.MULTIPLE_CHOICE:
            accepted = [expected] if isinstance(expected, str) else list(expected)
            lowered = {o.lower(): o for o in options}
            canonical: list[str] = []
            for item in accepted:
                if item.lower() not in lowered:
                    raise ValueError("expectedAnswer must be one of the options")
                if lowered[item.lower()] not in canonical:
                    canonical.append(lowered[item.lower()])
            expected = canonical
        elif self.type == QuestionType.TEXT:
            expected = None

        self.options = options
        self.expected_answer = expected
        return self


class JobIn(CamelModel):
    title: str = Field(min_length=1, max_length=255)
    description: str = Field(min_length=1, max_length=100_000)
    responsibilities: str | None = Field(default=None, max_length=50_000)
    required_skills: list[str] = Field(default_factory=list)
    preferred_skills: list[str] = Field(default_factory=list)
    experience_min: Decimal | None = Field(default=None, ge=0, le=99)
    experience_max: Decimal | None = Field(default=None, ge=0, le=99)
    salary_min: Decimal | None = Field(default=None, ge=0, lt=Decimal("1e12"))
    salary_max: Decimal | None = Field(default=None, ge=0, lt=Decimal("1e12"))
    hide_salary: bool = False
    job_type: JobType | None = None
    employment_type: EmploymentType | None = None
    work_mode: WorkMode | None = None
    locations: list[str] = Field(default_factory=list)
    openings: int = Field(default=1, ge=1, le=100_000)
    industry: str | None = Field(default=None, max_length=150)
    department: str | None = Field(
        default=None,
        max_length=150,
        validation_alias=AliasChoices("department", "functionalArea", "functional_area"),
    )
    role_category: str | None = Field(default=None, max_length=150)
    education: str | None = Field(default=None, max_length=150)
    notice_preference: str | None = Field(default=None, max_length=100)
    is_walk_in: bool = False
    walk_in_details: WalkInDetails | None = None
    deadline: DateType | None = None
    questions: list[QuestionIn] = Field(default_factory=list, max_length=MAX_QUESTIONS)
    publish: bool = False

    @field_validator("title", "description")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Must not be blank")
        return value

    @field_validator("responsibilities", "industry", "department", "role_category", "education", "notice_preference")
    @classmethod
    def _blank_to_none(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None

    @field_validator("required_skills", "preferred_skills")
    @classmethod
    def _skills(cls, value: list[str]) -> list[str]:
        return _clean_list(value, MAX_SKILLS, "skills", max_len=100)

    @field_validator("locations")
    @classmethod
    def _locations(cls, value: list[str]) -> list[str]:
        return _clean_list(value, MAX_LOCATIONS, "locations")

    @field_validator("deadline")
    @classmethod
    def _deadline_not_past(cls, value: DateType | None) -> DateType | None:
        if value is not None and value < datetime.now(timezone.utc).date():
            raise ValueError("deadline must not be in the past")
        return value

    @model_validator(mode="after")
    def _ranges(self) -> JobIn:
        if self.salary_min is not None and self.salary_max is not None and self.salary_min > self.salary_max:
            raise ValueError("salaryMin must not exceed salaryMax")
        if (
            self.experience_min is not None
            and self.experience_max is not None
            and self.experience_min > self.experience_max
        ):
            raise ValueError("experienceMin must not exceed experienceMax")
        if self.is_walk_in and (self.walk_in_details is None or not (self.walk_in_details.venue or "").strip()):
            raise ValueError("walkInDetails.venue is required for walk-in jobs")
        return self


class JobStatusIn(CamelModel):
    status: JobStatus
    reason: str | None = Field(default=None, max_length=1000)


class ApplicationStatusIn(CamelModel):
    status: ApplicationStatus
    message: str | None = Field(default=None, max_length=2000)


class BulkStatusIn(CamelModel):
    application_ids: list[uuid.UUID] = Field(min_length=1, max_length=BULK_LIMIT)
    status: ApplicationStatus
    message: str | None = Field(default=None, max_length=2000)


class BulkRejectIn(CamelModel):
    application_ids: list[uuid.UUID] = Field(min_length=1, max_length=BULK_LIMIT)
    message: str | None = Field(default=None, max_length=2000)


class NoteIn(CamelModel):
    note: str = Field(min_length=1, max_length=5000)

    @field_validator("note")
    @classmethod
    def _strip(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("note must not be blank")
        return value


class RatingIn(CamelModel):
    rating: Annotated[int, Field(strict=True, ge=1, le=5)]


class InterviewIn(CamelModel):
    date_time: datetime
    mode: InterviewMode
    location_or_link: str = Field(min_length=1, max_length=500)
    notes: str | None = Field(default=None, max_length=2000)

    @field_validator("date_time")
    @classmethod
    def _future_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("dateTime must include a timezone offset (ISO-8601)")
        if value <= datetime.now(timezone.utc):
            raise ValueError("dateTime must be in the future")
        return value

    @field_validator("location_or_link")
    @classmethod
    def _strip_location(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("locationOrLink must not be blank")
        return value
