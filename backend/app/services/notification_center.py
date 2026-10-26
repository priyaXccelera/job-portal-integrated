"""In-app notification inbox and notification preferences (read side of services.notifications)."""

from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from app.core.errors import AppError, NotFoundError
from app.core.responses import PageParams, paginate
from app.models.accounts import Notification, NotificationPreference
from app.schemas.messaging import NotificationPreferencesUpdate
from app.services.notifications import DEFAULT_EMAIL_FREQUENCY, DEFAULT_PREFERENCES, Category

logger = logging.getLogger(__name__)


def serialize_notification(n: Notification) -> dict[str, Any]:
    return {
        "id": n.id,
        "category": n.category,
        "title": n.title,
        "body": n.body,
        "data": n.data,
        "isRead": bool(n.is_read),
        "createdAt": n.created_at,
    }


def list_notifications(
    db: Session, user_id: uuid.UUID, params: PageParams, unread: bool | None, category: str | None
) -> tuple[list[dict[str, Any]], int]:
    stmt = select(Notification).where(Notification.user_id == user_id)
    if unread:
        stmt = stmt.where(Notification.is_read.is_(False))
    if category:
        value = category.strip().upper()
        if value not in {c.value for c in Category}:
            raise AppError(
                422,
                "VALIDATION_ERROR",
                "Validation failed",
                [{"field": "category", "message": f"Unknown category '{category}'"}],
            )
        stmt = stmt.where(Notification.category == value)
    stmt = stmt.order_by(Notification.created_at.desc(), Notification.id.desc())
    rows, total = paginate(db, stmt, params)
    return [serialize_notification(n) for n in rows], total


def unread_count(db: Session, user_id: uuid.UUID) -> int:
    return int(
        db.scalar(
            select(func.count())
            .select_from(Notification)
            .where(Notification.user_id == user_id, Notification.is_read.is_(False))
        )
        or 0
    )


def _owned(db: Session, user_id: uuid.UUID, notification_id: uuid.UUID) -> Notification:
    notification = db.scalar(
        select(Notification).where(Notification.id == notification_id, Notification.user_id == user_id)
    )
    if notification is None:
        raise NotFoundError("Notification not found")
    return notification


def mark_read(db: Session, user_id: uuid.UUID, notification_id: uuid.UUID) -> dict[str, Any]:
    notification = _owned(db, user_id, notification_id)
    if not notification.is_read:
        notification.is_read = True
        db.commit()
    return serialize_notification(notification)


def mark_all_read(db: Session, user_id: uuid.UUID) -> int:
    result = db.execute(
        update(Notification)
        .where(Notification.user_id == user_id, Notification.is_read.is_(False))
        .values(is_read=True)
    )
    db.commit()
    return int(result.rowcount or 0)


def delete_notification(db: Session, user_id: uuid.UUID, notification_id: uuid.UUID) -> None:
    result = db.execute(
        delete(Notification).where(Notification.id == notification_id, Notification.user_id == user_id)
    )
    if not result.rowcount:
        db.rollback()
        raise NotFoundError("Notification not found")
    db.commit()


def _serialize_preferences(pref: NotificationPreference | None) -> dict[str, Any]:
    categories = dict(DEFAULT_PREFERENCES)
    if pref is not None:
        categories.update({k: bool(v) for k, v in (pref.categories or {}).items() if k in DEFAULT_PREFERENCES})
    return {
        "categories": categories,
        "emailFrequency": (pref.email_frequency if pref else None) or DEFAULT_EMAIL_FREQUENCY,
        "newApplicantDigest": bool(pref.new_applicant_digest) if pref else False,
    }


def get_preferences(db: Session, user_id: uuid.UUID) -> dict[str, Any]:
    return _serialize_preferences(db.get(NotificationPreference, user_id))


def update_preferences(
    db: Session, user_id: uuid.UUID, payload: NotificationPreferencesUpdate
) -> dict[str, Any]:
    pref = db.get(NotificationPreference, user_id)
    if pref is None:
        pref = NotificationPreference(
            user_id=user_id,
            categories={},
            email_frequency=DEFAULT_EMAIL_FREQUENCY,
            new_applicant_digest=False,
        )
        db.add(pref)
    if payload.categories is not None:
        merged = dict(DEFAULT_PREFERENCES)
        merged.update(pref.categories or {})
        merged.update(payload.categories)
        pref.categories = merged  # reassign whole JSONB value
    if payload.email_frequency is not None:
        pref.email_frequency = payload.email_frequency
    if payload.new_applicant_digest is not None:
        pref.new_applicant_digest = payload.new_applicant_digest
    db.commit()
    return _serialize_preferences(pref)
