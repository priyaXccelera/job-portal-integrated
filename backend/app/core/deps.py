"""FastAPI dependencies: authentication, role checks and recruiter context."""

from __future__ import annotations

import logging
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.errors import ForbiddenError, UnauthorizedError
from app.core.security import decode_token
from app.db import get_db
from app.models.accounts import User
from app.models.company import Company
from app.models.enums import UserRole

logger = logging.getLogger(__name__)

bearer_scheme = HTTPBearer(auto_error=False)

LAST_ACTIVE_INTERVAL = timedelta(minutes=5)

__all__ = [
    "RecruiterContext",
    "bearer_scheme",
    "client_ip",
    "get_current_user",
    "get_db",
    "optional_user",
    "recruiter_ctx",
    "require_roles",
]


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _touch_last_active(db: Session, user: User) -> None:
    now = datetime.now(timezone.utc)
    last = user.last_active_at
    if last is not None:
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        if now - last < LAST_ACTIVE_INTERVAL:
            return
    try:
        user.last_active_at = now
        db.commit()
    except SQLAlchemyError:
        logger.warning("Could not update last_active_at for user %s", user.id, exc_info=True)
        db.rollback()


def _user_from_token(db: Session, token: str) -> User:
    payload = decode_token(token)
    try:
        user_id = uuid.UUID(str(payload["sub"]))
    except (ValueError, KeyError) as exc:
        raise UnauthorizedError("Invalid authentication token") from exc
    user = db.get(User, user_id)
    if user is None or user.deleted_at is not None:
        raise UnauthorizedError("Invalid authentication token")
    if user.is_blocked:
        raise ForbiddenError("Your account has been blocked", code="ACCOUNT_BLOCKED")
    _touch_last_active(db, user)
    return user


def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    if creds is None or not creds.credentials:
        raise UnauthorizedError()
    return _user_from_token(db, creds.credentials)


def optional_user(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User | None:
    if creds is None or not creds.credentials:
        return None
    return _user_from_token(db, creds.credentials)


def require_roles(*roles: UserRole) -> Callable[..., User]:
    allowed = {UserRole(r) for r in roles}

    def dependency(user: User = Depends(get_current_user)) -> User:
        if UserRole(user.role) not in allowed:
            raise ForbiddenError("You do not have permission to perform this action")
        return user

    return dependency


@dataclass
class RecruiterContext:
    user: User
    company: Company
    is_company_admin: bool


def recruiter_ctx(
    user: User = Depends(require_roles(UserRole.RECRUITER)),
    db: Session = Depends(get_db),
) -> RecruiterContext:
    if user.company_id is None:
        raise ForbiddenError("Recruiter is not linked to a company")
    company = db.get(Company, user.company_id)
    if company is None or getattr(company, "deleted_at", None) is not None:
        raise ForbiddenError("Company is not available")
    return RecruiterContext(user=user, company=company, is_company_admin=bool(user.is_company_admin))
