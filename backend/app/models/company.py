"""Companies, recruiter invitations, follows, reviews, credits and talent-pool tables."""

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, created_at_col, updated_at_col, uuid_pk
from app.models.enums import (
    CompanyStatus,
    CompanyType,
    InvitationStatus,
    ReviewStatus,
    pg_enum,
)


def _company_fk(**kw):
    return mapped_column(
        Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), index=True, **kw
    )


def _user_ref(nullable: bool = True, ondelete: str = "SET NULL", index: bool = False):
    return mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete=ondelete), nullable=nullable, index=index
    )


class Company(Base):
    __tablename__ = "companies"

    id: Mapped[uuid.UUID] = uuid_pk()
    name: Mapped[str] = mapped_column(String(200), index=True)
    logo_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    banner_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    website: Mapped[str | None] = mapped_column(String(300), nullable=True)
    industry: Mapped[str | None] = mapped_column(String(150), nullable=True)
    company_type: Mapped[CompanyType | None] = mapped_column(pg_enum(CompanyType), nullable=True)
    size_range: Mapped[str | None] = mapped_column(String(50), nullable=True)
    founded_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    headquarters: Mapped[str | None] = mapped_column(String(150), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    benefits: Mapped[str | None] = mapped_column(Text, nullable=True)
    # list[str] of image urls
    gallery: Mapped[list] = mapped_column(JSONB, default=list, server_default=text("'[]'::jsonb"))
    # {"linkedin": url, "twitter": url, ...}
    social_links: Mapped[dict] = mapped_column(JSONB, default=dict, server_default=text("'{}'::jsonb"))
    verified: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    status: Mapped[CompanyStatus] = mapped_column(
        pg_enum(CompanyStatus),
        default=CompanyStatus.PENDING,
        server_default=CompanyStatus.PENDING.value,
        index=True,
    )
    status_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    credits: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    job_quota: Mapped[int] = mapped_column(Integer, default=10, server_default=text("10"))
    jobs_posted: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    # users.id of the registering recruiter. Plain UUID (no FK) to avoid a users<->companies FK cycle.
    created_by: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime] = updated_at_col()
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Invitation(Base):
    __tablename__ = "invitations"

    id: Mapped[uuid.UUID] = uuid_pk()
    company_id: Mapped[uuid.UUID] = _company_fk()
    email: Mapped[str] = mapped_column(String(320), index=True)
    invited_by: Mapped[uuid.UUID | None] = _user_ref()
    token_hash: Mapped[str] = mapped_column(String(128), unique=True)
    status: Mapped[InvitationStatus] = mapped_column(
        pg_enum(InvitationStatus),
        default=InvitationStatus.PENDING,
        server_default=InvitationStatus.PENDING.value,
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = created_at_col()


class CompanyFollow(Base):
    __tablename__ = "company_follows"
    __table_args__ = (UniqueConstraint("user_id", "company_id", name="uq_company_follow_user_company"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = _user_ref(nullable=False, ondelete="CASCADE", index=True)
    company_id: Mapped[uuid.UUID] = _company_fk()
    created_at: Mapped[datetime] = created_at_col()


class CompanyReview(Base):
    __tablename__ = "company_reviews"
    __table_args__ = (
        UniqueConstraint("company_id", "user_id", name="uq_company_review_company_user"),
        CheckConstraint("rating BETWEEN 1 AND 5", name="ck_company_review_rating"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    company_id: Mapped[uuid.UUID] = _company_fk()
    user_id: Mapped[uuid.UUID] = _user_ref(nullable=False, ondelete="CASCADE", index=True)
    rating: Mapped[int] = mapped_column(Integer)
    title: Mapped[str | None] = mapped_column(String(200), nullable=True)
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[ReviewStatus] = mapped_column(
        pg_enum(ReviewStatus),
        default=ReviewStatus.PENDING,
        server_default=ReviewStatus.PENDING.value,
        index=True,
    )
    created_at: Mapped[datetime] = created_at_col()


class CreditLog(Base):
    __tablename__ = "credit_logs"

    id: Mapped[uuid.UUID] = uuid_pk()
    company_id: Mapped[uuid.UUID] = _company_fk()
    user_id: Mapped[uuid.UUID | None] = _user_ref()
    delta: Mapped[int] = mapped_column(Integer)
    balance_after: Mapped[int] = mapped_column(Integer)
    reason: Mapped[str] = mapped_column(String(255))
    ref_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    ref_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = created_at_col()


class CandidateFolder(Base):
    __tablename__ = "candidate_folders"

    id: Mapped[uuid.UUID] = uuid_pk()
    company_id: Mapped[uuid.UUID] = _company_fk()
    name: Mapped[str] = mapped_column(String(150))
    created_by: Mapped[uuid.UUID | None] = _user_ref()
    created_at: Mapped[datetime] = created_at_col()


class FolderCandidate(Base):
    __tablename__ = "folder_candidates"
    __table_args__ = (UniqueConstraint("folder_id", "candidate_id", name="uq_folder_candidate"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    folder_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("candidate_folders.id", ondelete="CASCADE"), index=True
    )
    candidate_id: Mapped[uuid.UUID] = _user_ref(nullable=False, ondelete="CASCADE", index=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = created_at_col()


class ContactUnlock(Base):
    __tablename__ = "contact_unlocks"
    __table_args__ = (UniqueConstraint("company_id", "candidate_id", name="uq_contact_unlock"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    company_id: Mapped[uuid.UUID] = _company_fk()
    candidate_id: Mapped[uuid.UUID] = _user_ref(nullable=False, ondelete="CASCADE", index=True)
    unlocked_by: Mapped[uuid.UUID | None] = _user_ref()
    created_at: Mapped[datetime] = created_at_col()


class CandidateInvite(Base):
    """Recruiter invites a candidate to apply for a job (costs credits)."""

    __tablename__ = "candidate_invites"
    __table_args__ = (Index("ix_candidate_invites_company_candidate", "company_id", "candidate_id"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    company_id: Mapped[uuid.UUID] = _company_fk()
    candidate_id: Mapped[uuid.UUID] = _user_ref(nullable=False, ondelete="CASCADE", index=True)
    job_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("jobs.id", ondelete="SET NULL"), nullable=True, index=True
    )
    recruiter_id: Mapped[uuid.UUID | None] = _user_ref()
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = created_at_col()
