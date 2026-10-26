"""Request bodies for the recruiter company / candidate-database endpoints."""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from typing import Self
from urllib.parse import urlparse

from pydantic import Field, field_validator, model_validator

from app.schemas.common import CamelModel, CompanyType

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MIN_FOUNDED_YEAR = 1800
MAX_GALLERY_ITEMS = 20
MAX_SOCIAL_LINKS = 10
LOCAL_FILE_PREFIX = "/api/v1/files/"


def _is_http_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in ("http", "https") and bool(parsed.netloc) and " " not in value


def _clean_optional(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value or None


class CompanyUpdate(CamelModel):
    """PUT /recruiter/company — only supplied fields change; logo/banner have their own endpoints."""

    name: str | None = Field(default=None, min_length=2, max_length=200)
    website: str | None = Field(default=None, max_length=300)
    industry: str | None = Field(default=None, max_length=150)
    company_type: CompanyType | None = None
    size_range: str | None = Field(default=None, max_length=50)
    founded_year: int | None = None
    headquarters: str | None = Field(default=None, max_length=150)
    description: str | None = Field(default=None, max_length=20000)
    benefits: str | None = Field(default=None, max_length=20000)
    gallery: list[str] | None = None
    social_links: dict[str, str] | None = None

    @field_validator("name")
    @classmethod
    def _name(cls, v: str | None) -> str | None:
        if v is None:
            return v
        v = v.strip()
        if len(v) < 2:
            raise ValueError("Name must be at least 2 characters")
        return v

    @field_validator("website")
    @classmethod
    def _website(cls, v: str | None) -> str | None:
        v = _clean_optional(v)
        if v is not None and not _is_http_url(v):
            raise ValueError("Website must be a valid http(s) URL")
        return v

    @field_validator("industry", "size_range", "headquarters", "description", "benefits")
    @classmethod
    def _strip(cls, v: str | None) -> str | None:
        return _clean_optional(v)

    @field_validator("founded_year")
    @classmethod
    def _founded_year(cls, v: int | None) -> int | None:
        if v is None:
            return v
        current = datetime.now(timezone.utc).year
        if not MIN_FOUNDED_YEAR <= v <= current:
            raise ValueError(f"Founded year must be between {MIN_FOUNDED_YEAR} and {current}")
        return v

    @field_validator("gallery")
    @classmethod
    def _gallery(cls, v: list[str] | None) -> list[str] | None:
        if v is None:
            return v
        if len(v) > MAX_GALLERY_ITEMS:
            raise ValueError(f"At most {MAX_GALLERY_ITEMS} gallery images are allowed")
        cleaned: list[str] = []
        for url in v:
            url = url.strip()
            if len(url) > 500 or not (_is_http_url(url) or url.startswith(LOCAL_FILE_PREFIX)):
                raise ValueError(f"Invalid gallery URL: {url[:60]}")
            cleaned.append(url)
        return cleaned

    @field_validator("social_links")
    @classmethod
    def _social_links(cls, v: dict[str, str] | None) -> dict[str, str] | None:
        if v is None:
            return v
        if len(v) > MAX_SOCIAL_LINKS:
            raise ValueError(f"At most {MAX_SOCIAL_LINKS} social links are allowed")
        cleaned: dict[str, str] = {}
        for key, url in v.items():
            key = key.strip().lower()
            url = (url or "").strip()
            if not key or len(key) > 30:
                raise ValueError("Social link names must be 1-30 characters")
            if len(url) > 300 or not _is_http_url(url):
                raise ValueError(f"Social link '{key}' must be a valid http(s) URL")
            cleaned[key] = url
        return cleaned

    @model_validator(mode="after")
    def _name_not_null(self) -> Self:
        if "name" in self.model_fields_set and self.name is None:
            raise ValueError("Name cannot be null")
        return self


class InvitationCreate(CamelModel):
    email: str = Field(max_length=320)

    @field_validator("email")
    @classmethod
    def _email(cls, v: str) -> str:
        v = v.strip().lower()
        if not EMAIL_RE.match(v):
            raise ValueError("Enter a valid email address")
        return v


class CandidateInviteCreate(CamelModel):
    job_id: uuid.UUID
    message: str | None = Field(default=None, max_length=2000)

    @field_validator("message")
    @classmethod
    def _message(cls, v: str | None) -> str | None:
        return _clean_optional(v)


class FolderIn(CamelModel):
    name: str = Field(min_length=1, max_length=150)

    @field_validator("name")
    @classmethod
    def _name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Name must not be blank")
        return v


class FolderCandidateIn(CamelModel):
    candidate_id: uuid.UUID
    note: str | None = Field(default=None, max_length=2000)

    @field_validator("note")
    @classmethod
    def _note(cls, v: str | None) -> str | None:
        return _clean_optional(v)
