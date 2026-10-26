"""Password hashing, JWT access tokens, opaque refresh tokens and OTP generation."""

from __future__ import annotations

import base64
import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import bcrypt
import jwt

from app.config import settings
from app.core.errors import UnauthorizedError


def _prepare(password: str) -> bytes:
    """bcrypt only uses the first 72 bytes; pre-hash longer inputs so none are silently dropped."""
    raw = password.encode("utf-8")
    if len(raw) > 72:
        return base64.b64encode(hashlib.sha256(raw).digest())
    return raw


def hash_password(password: str) -> str:
    return bcrypt.hashpw(_prepare(password), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str | None) -> bool:
    if not password_hash:
        return False
    try:
        return bcrypt.checkpw(_prepare(password), password_hash.encode("utf-8"))
    except ValueError:
        return False


def create_access_token(user: Any) -> tuple[str, int]:
    """Return ``(token, expires_in_seconds)`` for the given user."""
    now = datetime.now(timezone.utc)
    expires_in = int(settings.access_token_minutes) * 60
    role = getattr(user.role, "value", user.role)
    payload = {
        "sub": str(user.id),
        "role": str(role),
        "iat": now,
        "exp": now + timedelta(seconds=expires_in),
        "jti": uuid.uuid4().hex,
        "type": "access",
    }
    token = jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    return token, expires_in


def decode_token(token: str) -> dict[str, Any]:
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
            options={"require": ["exp", "sub"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise UnauthorizedError("Token has expired") from exc
    except jwt.PyJWTError as exc:
        raise UnauthorizedError("Invalid authentication token") from exc
    if payload.get("type") != "access":
        raise UnauthorizedError("Invalid authentication token")
    return payload


def new_refresh_token() -> str:
    return secrets.token_urlsafe(48)


def hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def generate_otp() -> str:
    length = max(4, int(settings.otp_length))
    return "".join(secrets.choice("0123456789") for _ in range(length))
