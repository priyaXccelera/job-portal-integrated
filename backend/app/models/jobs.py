"""Jobs, screening questions and seeker-side job tables (saved, reports, views, alerts, searches)."""

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    ARRAY,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy import text as sql_text  # `text` is a column name on ScreeningQuestion
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base, created_at_col, updated_at_col, utcnow, uuid_pk
from app.models.enums import (
    AlertFrequency,
    EmploymentType,
    JobStatus,
    JobType,
    QuestionType,
    ReportReason,
    ReportStatus,
    WorkMode,
    pg_enum,
)

_EMPTY_ARRAY = sql_text("'{}'::text[]")


class Job(Base):
    __tablename__ = "jobs"
    __table_args__ = (
        Index("ix_jobs_status_posted_at", "status", "posted_at"),
        Index("ix_jobs_company_status", "company_id", "status"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), index=True
    )
    posted_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)  # rich text (HTML allowed)
    responsibilities: Mapped[str | None] = mapped_column(Text, nullable=True)
    required_skills: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list, server_default=_EMPTY_ARRAY)
    preferred_skills: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list, server_default=_EMPTY_ARRAY)
    experience_min: Mapped[Decimal | None] = mapped_column(Numeric(4, 1), nullable=True)
    experience_max: Mapped[Decimal | None] = mapped_column(Numeric(4, 1), nullable=True)
    salary_min: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    salary_max: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    hide_salary: Mapped[bool] = mapped_column(Boolean, default=False, server_default=sql_text("false"))
    job_type: Mapped[JobType | None] = mapped_column(pg_enum(JobType), nullable=True)
    employment_type: Mapped[EmploymentType | None] = mapped_column(pg_enum(EmploymentType), nullable=True)
    work_mode: Mapped[WorkMode | None] = mapped_column(pg_enum(WorkMode), nullable=True)
    locations: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list, server_default=_EMPTY_ARRAY)
    openings: Mapped[int] = mapped_column(Integer, default=1, server_default=sql_text("1"))
    industry: Mapped[str | None] = mapped_column(String(150), nullable=True, index=True)
    department: Mapped[str | None] = mapped_column(String(150), nullable=True, index=True)
    role_category: Mapped[str | None] = mapped_column(String(150), nullable=True)
    education: Mapped[str | None] = mapped_column(String(150), nullable=True)
    notice_preference: Mapped[str | None] = mapped_column(String(100), nullable=True)
    is_walk_in: Mapped[bool] = mapped_column(Boolean, default=False, server_default=sql_text("false"))
    walk_in_details: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    deadline: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[JobStatus] = mapped_column(
        pg_enum(JobStatus),
        default=JobStatus.DRAFT,
        server_default=JobStatus.DRAFT.value,
        index=True,
    )
    reject_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    view_count: Mapped[int] = mapped_column(Integer, default=0, server_default=sql_text("0"))
    application_count: Mapped[int] = mapped_column(Integer, default=0, server_default=sql_text("0"))
    # maintained by app.services.job_index.reindex_job (deferred: not loaded with the entity)
    search_vector: Mapped[str | None] = mapped_column(TSVECTOR, nullable=True, deferred=True)
    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime] = updated_at_col()
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    company = relationship("Company", lazy="select")
    questions = relationship(
        "ScreeningQuestion",
        order_by="ScreeningQuestion.position",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="select",
    )


class ScreeningQuestion(Base):
    """Screening question.

    expected_answer semantics (only evaluated when is_knockout is true):
      * TEXT:            ignored (never knocks out)
      * YES_NO:          'YES' or 'NO' (case-insensitive compare)
      * MULTIPLE_CHOICE: JSON-array string of accepted option(s), e.g. '["Python","Go"]'.
                         A plain (non-JSON) string is treated as one accepted option, and
                         a comma-separated string as several. Answer passes if it equals
                         (case-insensitive) any accepted option.
    options: list of choices for MULTIPLE_CHOICE (empty otherwise).
    """

    __tablename__ = "screening_questions"

    id: Mapped[uuid.UUID] = uuid_pk()
    job_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE"), index=True
    )
    text: Mapped[str] = mapped_column(Text)
    question_type: Mapped[QuestionType] = mapped_column(
        pg_enum(QuestionType), default=QuestionType.TEXT, server_default=QuestionType.TEXT.value
    )
    options: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list, server_default=_EMPTY_ARRAY)
    is_knockout: Mapped[bool] = mapped_column(Boolean, default=False, server_default=sql_text("false"))
    expected_answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_required: Mapped[bool] = mapped_column(Boolean, default=True, server_default=sql_text("true"))
    position: Mapped[int] = mapped_column(Integer, default=0, server_default=sql_text("0"))


class SavedJob(Base):
    __tablename__ = "saved_jobs"
    __table_args__ = (UniqueConstraint("user_id", "job_id", name="uq_saved_job_user_job"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE"), index=True
    )
    created_at: Mapped[datetime] = created_at_col()


class JobReport(Base):
    __tablename__ = "job_reports"

    id: Mapped[uuid.UUID] = uuid_pk()
    job_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    reason: Mapped[ReportReason] = mapped_column(pg_enum(ReportReason))
    details: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[ReportStatus] = mapped_column(
        pg_enum(ReportStatus),
        default=ReportStatus.OPEN,
        server_default=ReportStatus.OPEN.value,
        index=True,
    )
    created_at: Mapped[datetime] = created_at_col()


class JobView(Base):
    """One row per user per job per day -> unique view counting."""

    __tablename__ = "job_views"
    __table_args__ = (UniqueConstraint("user_id", "job_id", "view_date", name="uq_job_view_user_job_date"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    job_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    view_date: Mapped[date] = mapped_column(Date, default=lambda: utcnow().date())


class JobAlert(Base):
    __tablename__ = "job_alerts"

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(150))
    keywords: Mapped[str | None] = mapped_column(String(500), nullable=True)
    locations: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list, server_default=_EMPTY_ARRAY)
    experience: Mapped[Decimal | None] = mapped_column(Numeric(4, 1), nullable=True)
    salary_min: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    frequency: Mapped[AlertFrequency] = mapped_column(
        pg_enum(AlertFrequency),
        default=AlertFrequency.daily,
        server_default=AlertFrequency.daily.value,
    )
    is_paused: Mapped[bool] = mapped_column(Boolean, default=False, server_default=sql_text("false"))
    last_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime] = updated_at_col()


class RecentSearch(Base):
    __tablename__ = "recent_searches"
    __table_args__ = (Index("ix_recent_searches_user_created", "user_id", "created_at"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE")
    )
    query: Mapped[str | None] = mapped_column(String(500), nullable=True)
    filters: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, server_default=func.now()
    )


class SavedSearch(Base):
    __tablename__ = "saved_searches"

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(150))
    query: Mapped[str | None] = mapped_column(String(500), nullable=True)
    filters: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = created_at_col()
