"""Applications, answers, status timeline, notes, interviews and messaging."""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
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
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, created_at_col, updated_at_col, utcnow, uuid_pk
from app.models.enums import (
    ApplicationStatus,
    InterviewMode,
    InterviewResponse,
    pg_enum,
)


def _user_ref(nullable: bool = True, ondelete: str = "SET NULL", index: bool = False):
    return mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete=ondelete), nullable=nullable, index=index
    )


def _app_fk():
    return mapped_column(
        Uuid(as_uuid=True), ForeignKey("applications.id", ondelete="CASCADE"), index=True
    )


class Application(Base):
    __tablename__ = "applications"
    __table_args__ = (
        UniqueConstraint("job_id", "user_id", name="uq_application_job_user"),
        Index("ix_applications_user_id", "user_id"),
        Index("ix_applications_job_status", "job_id", "status"),
        CheckConstraint("rating IS NULL OR rating BETWEEN 1 AND 5", name="ck_application_rating"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    job_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE")
    )
    resume_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("resumes.id", ondelete="SET NULL"), nullable=True
    )
    cover_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    expected_ctc: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    notice_period: Mapped[str | None] = mapped_column(String(100), nullable=True)
    status: Mapped[ApplicationStatus] = mapped_column(
        pg_enum(ApplicationStatus),
        default=ApplicationStatus.APPLIED,
        server_default=ApplicationStatus.APPLIED.value,
    )
    screened_out: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    screen_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    rating: Mapped[int | None] = mapped_column(Integer, nullable=True)
    match_score: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    applied_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime] = updated_at_col()
    viewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ApplicationAnswer(Base):
    __tablename__ = "application_answers"

    id: Mapped[uuid.UUID] = uuid_pk()
    application_id: Mapped[uuid.UUID] = _app_fk()
    question_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("screening_questions.id", ondelete="SET NULL"), nullable=True
    )
    answer: Mapped[str | None] = mapped_column(Text, nullable=True)


class StatusHistory(Base):
    __tablename__ = "status_history"

    id: Mapped[uuid.UUID] = uuid_pk()
    application_id: Mapped[uuid.UUID] = _app_fk()
    status: Mapped[ApplicationStatus] = mapped_column(pg_enum(ApplicationStatus))
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    changed_by: Mapped[uuid.UUID | None] = _user_ref()
    created_at: Mapped[datetime] = created_at_col()


class ApplicationNote(Base):
    __tablename__ = "application_notes"

    id: Mapped[uuid.UUID] = uuid_pk()
    application_id: Mapped[uuid.UUID] = _app_fk()
    author_id: Mapped[uuid.UUID | None] = _user_ref()
    note: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = created_at_col()


class Interview(Base):
    __tablename__ = "interviews"

    id: Mapped[uuid.UUID] = uuid_pk()
    application_id: Mapped[uuid.UUID] = _app_fk()
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    mode: Mapped[InterviewMode] = mapped_column(pg_enum(InterviewMode))
    location_or_link: Mapped[str | None] = mapped_column(String(500), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    candidate_response: Mapped[InterviewResponse | None] = mapped_column(
        pg_enum(InterviewResponse), nullable=True
    )
    response_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[uuid.UUID | None] = _user_ref()
    created_at: Mapped[datetime] = created_at_col()


class MessageThread(Base):
    __tablename__ = "message_threads"
    __table_args__ = (UniqueConstraint("recruiter_id", "candidate_id", name="uq_thread_recruiter_candidate"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    recruiter_id: Mapped[uuid.UUID] = _user_ref(nullable=False, ondelete="CASCADE", index=True)
    candidate_id: Mapped[uuid.UUID] = _user_ref(nullable=False, ondelete="CASCADE", index=True)
    company_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = created_at_col()
    last_message_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=utcnow, server_default=func.now(), nullable=True
    )


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (Index("ix_messages_thread_created", "thread_id", "created_at"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    thread_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("message_threads.id", ondelete="CASCADE")
    )
    sender_id: Mapped[uuid.UUID] = _user_ref(nullable=False, ondelete="CASCADE", index=True)
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = created_at_col()
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
