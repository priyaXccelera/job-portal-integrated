"""In-app + email notifications honouring each user's NotificationPreference."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.responses import to_jsonable
from app.models.accounts import Notification, NotificationPreference, User
from app.services.senders import SenderError, get_email_sender

logger = logging.getLogger(__name__)


class Category(StrEnum):
    APPLICATION_VIEWED = "APPLICATION_VIEWED"
    APPLICATION_SHORTLISTED = "APPLICATION_SHORTLISTED"
    INTERVIEW_SCHEDULED = "INTERVIEW_SCHEDULED"
    INTERVIEW_RESPONSE = "INTERVIEW_RESPONSE"
    STATUS_CHANGE = "STATUS_CHANGE"
    JOB_ALERT = "JOB_ALERT"
    RECRUITER_APPROVED = "RECRUITER_APPROVED"
    RECRUITER_REJECTED = "RECRUITER_REJECTED"
    JOB_APPROVED = "JOB_APPROVED"
    JOB_REJECTED = "JOB_REJECTED"
    JOB_EXPIRING = "JOB_EXPIRING"
    NEW_APPLICANT = "NEW_APPLICANT"
    PROFILE_VIEWED = "PROFILE_VIEWED"
    NEW_JOB_FROM_COMPANY = "NEW_JOB_FROM_COMPANY"
    MESSAGE = "MESSAGE"
    SYSTEM = "SYSTEM"


EMAIL_FREQUENCIES = ("INSTANT", "DAILY", "OFF")
DEFAULT_EMAIL_FREQUENCY = "INSTANT"
DEFAULT_PREFERENCES: dict[str, bool] = {c.value: True for c in Category}


def list_categories() -> list[str]:
    return [c.value for c in Category]


def notify(
    db: Session,
    user_id: uuid.UUID,
    category: Category | str,
    title: str,
    body: str,
    email: bool = True,
    data: dict[str, Any] | None = None,
) -> Notification | None:
    """Record an in-app notification and optionally email it. Does NOT commit.

    Returns ``None`` when the user disabled this category.
    """
    category_value = Category(category).value
    pref = db.scalar(select(NotificationPreference).where(NotificationPreference.user_id == user_id))
    categories = (pref.categories or {}) if pref is not None else {}
    if categories.get(category_value) is False:
        return None

    notification = Notification(
        id=uuid.uuid4(),
        user_id=user_id,
        category=category_value,
        title=title[:255],
        body=body,
        data=to_jsonable(data) if data is not None else None,
        is_read=False,
        created_at=datetime.now(timezone.utc),
    )
    db.add(notification)
    db.flush()

    frequency = (pref.email_frequency if pref is not None else DEFAULT_EMAIL_FREQUENCY) or DEFAULT_EMAIL_FREQUENCY
    if email and frequency == "INSTANT":
        address = db.scalar(select(User.email).where(User.id == user_id))
        if address:
            try:
                get_email_sender().send(address, title, body)
            except (SenderError, OSError):
                logger.warning("Email delivery failed for notification %s", notification.id, exc_info=True)
    return notification
