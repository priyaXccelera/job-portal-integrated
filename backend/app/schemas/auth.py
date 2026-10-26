"""Request bodies for the /auth endpoints."""

from __future__ import annotations

import re
from typing import Literal, Self

from pydantic import Field, field_validator, model_validator

from app.schemas.common import CamelModel, UserRole

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MOBILE_RE = re.compile(r"^\+?[0-9]{10,15}$")
MAX_PASSWORD_LENGTH = 128


def normalise_mobile(value: str) -> str:
    """Strip whitespace (and common separators) from a mobile number."""
    return re.sub(r"[\s\-()]", "", value or "")


def _check_email(value: str) -> str:
    value = value.strip().lower()
    if len(value) > 320 or not EMAIL_RE.match(value):
        raise ValueError("Enter a valid email address")
    return value


def _check_password(value: str) -> str:
    if len(value) < 8:
        raise ValueError("Password must be at least 8 characters long")
    if len(value) > MAX_PASSWORD_LENGTH:
        raise ValueError(f"Password must be at most {MAX_PASSWORD_LENGTH} characters long")
    if not re.search(r"[A-Za-z]", value) or not re.search(r"[0-9]", value):
        raise ValueError("Password must contain at least one letter and one digit")
    return value


class RegisterRequest(CamelModel):
    name: str = Field(min_length=1, max_length=200)
    email: str
    mobile: str
    password: str
    role: UserRole
    company_name: str | None = Field(default=None, max_length=200)
    invitation_token: str | None = Field(default=None, max_length=512)

    @field_validator("name")
    @classmethod
    def _name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Name must not be blank")
        return v

    @field_validator("email")
    @classmethod
    def _email(cls, v: str) -> str:
        return _check_email(v)

    @field_validator("mobile")
    @classmethod
    def _mobile(cls, v: str) -> str:
        v = normalise_mobile(v)
        if not MOBILE_RE.match(v):
            raise ValueError("Mobile must be 10-15 digits, optionally prefixed with +")
        return v

    @field_validator("password")
    @classmethod
    def _password(cls, v: str) -> str:
        return _check_password(v)

    @field_validator("role")
    @classmethod
    def _role(cls, v: UserRole) -> UserRole:
        if v == UserRole.ADMIN:
            raise ValueError("Role must be JOB_SEEKER or RECRUITER")
        return v

    @field_validator("company_name", "invitation_token")
    @classmethod
    def _blank_to_none(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.strip()
        return v or None

    @model_validator(mode="after")
    def _company_required(self) -> Self:
        if self.role == UserRole.RECRUITER and not self.company_name and not self.invitation_token:
            raise ValueError("companyName is required for recruiters")
        return self


class LoginRequest(CamelModel):
    identifier: str | None = Field(default=None, max_length=320)
    email: str | None = Field(default=None, max_length=320)
    password: str = Field(min_length=1, max_length=256)

    @model_validator(mode="after")
    def _identifier(self) -> Self:
        value = (self.identifier or self.email or "").strip()
        if not value:
            raise ValueError("identifier is required")
        self.identifier = value
        return self


class SendOtpRequest(CamelModel):
    identifier: str | None = Field(default=None, max_length=320)
    email: str | None = Field(default=None, max_length=320)
    purpose: Literal["LOGIN"] = "LOGIN"

    @model_validator(mode="after")
    def _identifier(self) -> Self:
        value = (self.identifier or self.email or "").strip()
        if not value:
            raise ValueError("identifier is required")
        self.identifier = value
        return self


class LoginOtpRequest(CamelModel):
    identifier: str | None = Field(default=None, max_length=320)
    email: str | None = Field(default=None, max_length=320)
    otp: str = Field(min_length=4, max_length=10)

    @model_validator(mode="after")
    def _identifier(self) -> Self:
        value = (self.identifier or self.email or "").strip()
        if not value:
            raise ValueError("identifier is required")
        self.identifier = value
        return self


class RefreshRequest(CamelModel):
    refresh_token: str = Field(min_length=1, max_length=512)


class VerifyEmailRequest(CamelModel):
    token: str = Field(min_length=1, max_length=512)


class VerifyMobileRequest(CamelModel):
    otp: str = Field(min_length=4, max_length=10)


class ForgotPasswordRequest(CamelModel):
    email: str

    @field_validator("email")
    @classmethod
    def _email(cls, v: str) -> str:
        return _check_email(v)


class ResetPasswordRequest(CamelModel):
    token: str = Field(min_length=1, max_length=512)
    new_password: str

    @field_validator("new_password")
    @classmethod
    def _password(cls, v: str) -> str:
        return _check_password(v)


class ChangePasswordRequest(CamelModel):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str

    @field_validator("new_password")
    @classmethod
    def _password(cls, v: str) -> str:
        return _check_password(v)
