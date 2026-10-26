"""Master data (admin-managed lookup tables)."""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, Integer, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, created_at_col, uuid_pk


class Skill(Base):
    __tablename__ = "skills"

    id: Mapped[uuid.UUID] = uuid_pk()
    name: Mapped[str] = mapped_column(String(150), unique=True)
    # list[str] of alternative names used for search synonym expansion
    synonyms: Mapped[list] = mapped_column(JSONB, default=list, server_default=text("'[]'::jsonb"))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"))
    created_at: Mapped[datetime] = created_at_col()


class Industry(Base):
    __tablename__ = "industries"

    id: Mapped[uuid.UUID] = uuid_pk()
    name: Mapped[str] = mapped_column(String(150), unique=True)
    created_at: Mapped[datetime] = created_at_col()


class Department(Base):
    """Department == functional area."""

    __tablename__ = "departments"

    id: Mapped[uuid.UUID] = uuid_pk()
    name: Mapped[str] = mapped_column(String(150), unique=True)
    created_at: Mapped[datetime] = created_at_col()


class RoleCategory(Base):
    __tablename__ = "role_categories"

    id: Mapped[uuid.UUID] = uuid_pk()
    name: Mapped[str] = mapped_column(String(150), unique=True)
    created_at: Mapped[datetime] = created_at_col()


class Location(Base):
    __tablename__ = "locations"
    __table_args__ = (UniqueConstraint("name", "state", name="uq_location_name_state"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    name: Mapped[str] = mapped_column(String(150))  # city
    state: Mapped[str | None] = mapped_column(String(150), nullable=True)
    country: Mapped[str] = mapped_column(String(100), default="India", server_default=text("'India'"))
    created_at: Mapped[datetime] = created_at_col()


class Degree(Base):
    __tablename__ = "degrees"

    id: Mapped[uuid.UUID] = uuid_pk()
    name: Mapped[str] = mapped_column(String(150), unique=True)
    # list[str]
    specializations: Mapped[list] = mapped_column(
        JSONB, default=list, server_default=text("'[]'::jsonb")
    )
    created_at: Mapped[datetime] = created_at_col()


class NoticePeriodOption(Base):
    __tablename__ = "notice_period_options"

    id: Mapped[uuid.UUID] = uuid_pk()
    name: Mapped[str] = mapped_column(String(100), unique=True)
    days: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    created_at: Mapped[datetime] = created_at_col()


# key = URL segment in /master/{type} and /admin/master/{type}
MASTER_TYPES: dict[str, type] = {
    "skills": Skill,
    "industries": Industry,
    "departments": Department,
    "role-categories": RoleCategory,
    "locations": Location,
    "degrees": Degree,
    "notice-periods": NoticePeriodOption,
}
