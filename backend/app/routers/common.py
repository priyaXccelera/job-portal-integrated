"""Cross-cutting endpoints: health, notifications, preferences, messaging, public files."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, Query
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, get_db, require_roles
from app.core.errors import AppError
from app.core.responses import PageParams, ok, page_params, paged
from app.models.accounts import User
from app.models.enums import UserRole
from app.schemas.messaging import MessageCreate, NotificationPreferencesUpdate, ThreadCreate
from app.services import messaging, notification_center
from app.services.public_files import resolve_public_file

logger = logging.getLogger(__name__)

router = APIRouter(tags=["common"])
# Mounted a second time without prefix so only GET /health (not every common route) is mirrored at root.
health_router = APIRouter(tags=["common"])

messaging_user = require_roles(UserRole.RECRUITER, UserRole.JOB_SEEKER)


# ------------------------------------------------------------------ health
def health(db: Session = Depends(get_db)) -> JSONResponse:
    """Liveness + database readiness probe (no auth)."""
    try:
        db.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        logger.error("Health check: database unreachable", exc_info=exc)
        raise AppError(503, "SERVICE_UNAVAILABLE", "Database is unavailable") from exc
    return ok({"status": "UP", "database": "UP", "time": datetime.now(timezone.utc)})


for _r in (router, health_router):
    _r.add_api_route("/health", health, methods=["GET"], summary="Health check")


# ------------------------------------------------------------------ notifications
@router.get("/notifications")
def list_notifications(
    unread: bool | None = Query(None, description="true => only unread"),
    category: str | None = Query(None),
    params: PageParams = Depends(page_params),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    items, total = notification_center.list_notifications(db, user.id, params, unread, category)
    return paged(items, params.page, params.page_size, total)


@router.get("/notifications/unread-count")
def notifications_unread_count(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return ok({"unreadCount": notification_center.unread_count(db, user.id)})


@router.post("/notifications/read-all")
def read_all_notifications(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return ok({"updated": notification_center.mark_all_read(db, user.id)})


@router.patch("/notifications/{notification_id}/read")
def read_notification(
    notification_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    return ok(notification_center.mark_read(db, user.id, notification_id))


@router.delete("/notifications/{notification_id}")
def delete_notification(
    notification_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    notification_center.delete_notification(db, user.id, notification_id)
    return ok({"id": notification_id, "deleted": True})


@router.get("/notification-preferences")
def get_notification_preferences(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return ok(notification_center.get_preferences(db, user.id))


@router.put("/notification-preferences")
def put_notification_preferences(
    payload: NotificationPreferencesUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return ok(notification_center.update_preferences(db, user.id, payload))


# ------------------------------------------------------------------ messaging (static routes first)
@router.get("/messages/unread-count")
def messages_unread_count(user: User = Depends(messaging_user), db: Session = Depends(get_db)):
    return ok({"unreadCount": messaging.total_unread(db, user)})


@router.get("/messages/threads")
def list_threads(
    params: PageParams = Depends(page_params),
    user: User = Depends(messaging_user),
    db: Session = Depends(get_db),
):
    items, total = messaging.list_threads(db, user, params)
    return paged(items, params.page, params.page_size, total)


@router.post("/messages/threads")
def create_thread(payload: ThreadCreate, user: User = Depends(messaging_user), db: Session = Depends(get_db)):
    data = messaging.create_thread(db, user, payload.body, payload.candidate_id, payload.recruiter_id)
    return ok(data, status_code=201)


@router.get("/messages/threads/{thread_id}/messages")
def list_thread_messages(
    thread_id: uuid.UUID,
    order: Literal["asc", "desc"] = Query("desc", description="desc = newest first (default)"),
    params: PageParams = Depends(page_params),
    user: User = Depends(messaging_user),
    db: Session = Depends(get_db),
):
    items, total = messaging.list_messages(db, user, thread_id, params, order)
    return paged(items, params.page, params.page_size, total)


@router.post("/messages/threads/{thread_id}/messages")
def post_thread_message(
    thread_id: uuid.UUID,
    payload: MessageCreate,
    user: User = Depends(messaging_user),
    db: Session = Depends(get_db),
):
    return ok(messaging.post_message(db, user, thread_id, payload.body), status_code=201)


@router.post("/messages/threads/{thread_id}/read")
def read_thread(thread_id: uuid.UUID, user: User = Depends(messaging_user), db: Session = Depends(get_db)):
    return ok({"marked": messaging.mark_thread_read(db, user, thread_id)})


# ------------------------------------------------------------------ public files
@router.get("/files/{kind}/{filename}")
def get_public_file(kind: str, filename: str):
    path, media_type = resolve_public_file(kind, filename)
    return FileResponse(
        path,
        media_type=media_type,
        headers={
            "Cache-Control": "public, max-age=86400",
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "default-src 'none'; sandbox",
        },
    )
