"""Domain enums (StrEnum -> compare equal to their string values) and the column helper."""

from enum import StrEnum

from sqlalchemy import Enum


class UserRole(StrEnum):
    JOB_SEEKER = "JOB_SEEKER"
    RECRUITER = "RECRUITER"
    ADMIN = "ADMIN"


class CompanyStatus(StrEnum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    BLOCKED = "BLOCKED"


class CompanyType(StrEnum):
    CORPORATE = "CORPORATE"
    STARTUP = "STARTUP"
    MNC = "MNC"
    GOVERNMENT = "GOVERNMENT"
    CONSULTANCY = "CONSULTANCY"


class JobStatus(StrEnum):
    DRAFT = "DRAFT"
    PENDING_REVIEW = "PENDING_REVIEW"
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    CLOSED = "CLOSED"
    EXPIRED = "EXPIRED"
    REJECTED = "REJECTED"


class JobType(StrEnum):
    PERMANENT = "PERMANENT"
    CONTRACT = "CONTRACT"


class EmploymentType(StrEnum):
    FULL_TIME = "FULL_TIME"
    PART_TIME = "PART_TIME"


class WorkMode(StrEnum):
    ONSITE = "ONSITE"
    REMOTE = "REMOTE"
    HYBRID = "HYBRID"


class ApplicationStatus(StrEnum):
    APPLIED = "APPLIED"
    VIEWED = "VIEWED"
    SHORTLISTED = "SHORTLISTED"
    INTERVIEW_SCHEDULED = "INTERVIEW_SCHEDULED"
    OFFERED = "OFFERED"
    HIRED = "HIRED"
    REJECTED = "REJECTED"
    WITHDRAWN = "WITHDRAWN"


class Visibility(StrEnum):
    ALL_RECRUITERS = "ALL_RECRUITERS"
    APPLIED_ONLY = "APPLIED_ONLY"
    HIDDEN = "HIDDEN"


class AlertFrequency(StrEnum):
    instant = "instant"
    daily = "daily"
    weekly = "weekly"


class QuestionType(StrEnum):
    TEXT = "TEXT"
    YES_NO = "YES_NO"
    MULTIPLE_CHOICE = "MULTIPLE_CHOICE"


class InterviewMode(StrEnum):
    VIDEO = "VIDEO"
    PHONE = "PHONE"
    IN_PERSON = "IN_PERSON"


class WorkStatus(StrEnum):
    FRESHER = "FRESHER"
    EXPERIENCED = "EXPERIENCED"


class ReportReason(StrEnum):
    FAKE = "FAKE"
    SPAM = "SPAM"
    MISLEADING = "MISLEADING"


class ReviewStatus(StrEnum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class InterviewResponse(StrEnum):
    CONFIRM = "CONFIRM"
    RESCHEDULE = "RESCHEDULE"


class ReportStatus(StrEnum):
    OPEN = "OPEN"
    RESOLVED = "RESOLVED"
    DISMISSED = "DISMISSED"


class InvitationStatus(StrEnum):
    PENDING = "PENDING"
    ACCEPTED = "ACCEPTED"
    REVOKED = "REVOKED"


def pg_enum(enum_cls: type[StrEnum]) -> Enum:
    """VARCHAR(32) column storing the exact enum *values* (no native PG enum, no CHECK)."""
    return Enum(
        enum_cls,
        native_enum=False,
        length=32,
        values_callable=lambda e: [m.value for m in e],
        validate_strings=True,
    )
