"""Job-seeker profile and its child records."""

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    ARRAY,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, created_at_col, updated_at_col, utcnow, uuid_pk
from app.models.enums import Visibility, WorkStatus, pg_enum


def _user_fk(**kw):
    return mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True, **kw)


class JobSeekerProfile(Base):
    __tablename__ = "job_seeker_profiles"

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    headline: Mapped[str | None] = mapped_column(String(255), nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    current_location: Mapped[str | None] = mapped_column(String(150), nullable=True)
    preferred_locations: Mapped[list[str]] = mapped_column(
        ARRAY(Text), default=list, server_default=text("'{}'::text[]")
    )
    dob: Mapped[date | None] = mapped_column(Date, nullable=True)
    gender: Mapped[str | None] = mapped_column(String(32), nullable=True)
    photo_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    experience_years: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    experience_months: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    notice_period: Mapped[str | None] = mapped_column(String(100), nullable=True)
    current_ctc: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    expected_ctc: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    work_status: Mapped[WorkStatus | None] = mapped_column(pg_enum(WorkStatus), nullable=True)
    # list of {"name": str, "proficiency": str}
    languages: Mapped[list] = mapped_column(JSONB, default=list, server_default=text("'[]'::jsonb"))
    # {"linkedin": url, "github": url, "portfolio": url}
    online_profiles: Mapped[dict] = mapped_column(JSONB, default=dict, server_default=text("'{}'::jsonb"))
    visibility: Mapped[Visibility] = mapped_column(
        pg_enum(Visibility),
        default=Visibility.ALL_RECRUITERS,
        server_default=Visibility.ALL_RECRUITERS.value,
        index=True,
    )
    actively_looking: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"))
    desired_industry: Mapped[str | None] = mapped_column(String(150), nullable=True)
    desired_department: Mapped[str | None] = mapped_column(String(150), nullable=True)
    desired_role_category: Mapped[str | None] = mapped_column(String(150), nullable=True)
    desired_job_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    desired_employment_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    desired_shift: Mapped[str | None] = mapped_column(String(32), nullable=True)
    desired_locations: Mapped[list[str]] = mapped_column(
        ARRAY(Text), default=list, server_default=text("'{}'::text[]")
    )
    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime] = updated_at_col()


class ProfileSkill(Base):
    __tablename__ = "profile_skills"
    __table_args__ = (UniqueConstraint("user_id", "skill_id", name="uq_profile_skill_user_skill"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = _user_fk()
    skill_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("skills.id", ondelete="CASCADE"), index=True
    )
    years_of_experience: Mapped[Decimal | None] = mapped_column(Numeric(4, 1), nullable=True)


class Employment(Base):
    __tablename__ = "employments"

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = _user_fk()
    company_name: Mapped[str] = mapped_column(String(200))
    designation: Mapped[str] = mapped_column(String(200))
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    is_current: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    location: Mapped[str | None] = mapped_column(String(150), nullable=True)


class Education(Base):
    __tablename__ = "educations"

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = _user_fk()
    degree: Mapped[str] = mapped_column(String(150))
    specialization: Mapped[str | None] = mapped_column(String(150), nullable=True)
    institute: Mapped[str | None] = mapped_column(String(200), nullable=True)
    start_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    end_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    grade: Mapped[str | None] = mapped_column(String(50), nullable=True)


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = _user_fk()
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    skills: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list, server_default=text("'{}'::text[]"))


class Certification(Base):
    __tablename__ = "certifications"

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = _user_fk()
    name: Mapped[str] = mapped_column(String(200))
    issuer: Mapped[str | None] = mapped_column(String(200), nullable=True)
    issued_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    expiry_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    credential_url: Mapped[str | None] = mapped_column(String(500), nullable=True)


class Resume(Base):
    __tablename__ = "resumes"

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = _user_fk()
    file_name: Mapped[str] = mapped_column(String(255))
    file_path: Mapped[str] = mapped_column(String(500))
    content_type: Mapped[str | None] = mapped_column(String(150), nullable=True)
    size_bytes: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    # list[str] of skill names found by the keyword parser
    parsed_skills: Mapped[list] = mapped_column(JSONB, default=list, server_default=text("'[]'::jsonb"))
    created_at: Mapped[datetime] = created_at_col()


class ProfileView(Base):
    __tablename__ = "profile_views"

    id: Mapped[uuid.UUID] = uuid_pk()
    candidate_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    recruiter_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    company_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="SET NULL"), nullable=True, index=True
    )
    viewed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, server_default=func.now()
    )


class HiddenCompany(Base):
    __tablename__ = "hidden_companies"
    __table_args__ = (UniqueConstraint("user_id", "company_id", name="uq_hidden_company_user_company"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = _user_fk()
    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), index=True
    )
