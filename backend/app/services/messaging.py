"""Recruiter <-> candidate messaging: eligibility, threads, messages and read state."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Literal

from sqlalchemy import exists, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import AppError, BadRequestError, ForbiddenError, NotFoundError
from app.core.responses import PageParams, paginate
from app.models.accounts import User
from app.models.applications import Application, Message, MessageThread
from app.models.company import Company, ContactUnlock, CandidateInvite
from app.models.enums import UserRole
from app.models.jobs import Job
from app.services.notifications import Category, notify

logger = logging.getLogger(__name__)

MESSAGING_NOT_ALLOWED = "MESSAGING_NOT_ALLOWED"
SNIPPET_LENGTH = 140


def _not_allowed(message: str) -> AppError:
    return AppError(403, MESSAGING_NOT_ALLOWED, message)


def _now() -> datetime:
    return datetime.now(timezone.utc)


# --------------------------------------------------------------------------- eligibility
def can_message_candidate(db: Session, company_id: uuid.UUID, candidate_id: uuid.UUID) -> bool:
    """True when the candidate applied to a job of the company, was unlocked or was invited."""
    applied = exists().where(
        Application.user_id == candidate_id,
        Application.job_id == Job.id,
        Job.company_id == company_id,
    )
    unlocked = exists().where(
        ContactUnlock.company_id == company_id, ContactUnlock.candidate_id == candidate_id
    )
    invited = exists().where(
        CandidateInvite.company_id == company_id, CandidateInvite.candidate_id == candidate_id
    )
    return bool(db.scalar(select(or_(applied, unlocked, invited))))


def _require_eligibility(db: Session, recruiter: User, candidate_id: uuid.UUID) -> None:
    if recruiter.company_id is None:
        raise ForbiddenError("Recruiter is not linked to a company")
    if not can_message_candidate(db, recruiter.company_id, candidate_id):
        raise _not_allowed(
            "You can only message candidates who applied to your jobs, "
            "whose contact you unlocked, or whom you invited"
        )


# --------------------------------------------------------------------------- serializers
def serialize_message(message: Message, viewer_id: uuid.UUID) -> dict[str, Any]:
    return {
        "id": message.id,
        "threadId": message.thread_id,
        "senderId": message.sender_id,
        "body": message.body,
        "createdAt": message.created_at,
        "readAt": message.read_at,
        "isMine": message.sender_id == viewer_id,
    }


def _last_message_dict(message: Message | None) -> dict[str, Any] | None:
    if message is None:
        return None
    return {"body": message.body, "createdAt": message.created_at, "senderId": message.sender_id}


def _serialize_threads(db: Session, threads: list[MessageThread], viewer: User) -> list[dict[str, Any]]:
    """Batched serialization: 4 queries regardless of page size."""
    if not threads:
        return []
    thread_ids = [t.id for t in threads]
    viewer_is_recruiter = UserRole(viewer.role) == UserRole.RECRUITER
    counterpart_ids = {(t.candidate_id if viewer_is_recruiter else t.recruiter_id) for t in threads}

    users = {
        u.id: u
        for u in db.scalars(select(User).where(User.id.in_(counterpart_ids))).all()
    }
    company_ids = {t.company_id for t in threads if t.company_id} | {
        u.company_id for u in users.values() if u.company_id
    }
    company_names: dict[uuid.UUID, str] = {}
    if not viewer_is_recruiter and company_ids:
        company_names = dict(
            db.execute(select(Company.id, Company.name).where(Company.id.in_(company_ids))).all()
        )

    last_messages = {
        m.thread_id: m
        for m in db.scalars(
            select(Message)
            .where(Message.thread_id.in_(thread_ids))
            .distinct(Message.thread_id)
            .order_by(Message.thread_id, Message.created_at.desc(), Message.id.desc())
        ).all()
    }
    unread = dict(
        db.execute(
            select(Message.thread_id, func.count(Message.id))
            .where(
                Message.thread_id.in_(thread_ids),
                Message.sender_id != viewer.id,
                Message.read_at.is_(None),
            )
            .group_by(Message.thread_id)
        ).all()
    )

    items: list[dict[str, Any]] = []
    for thread in threads:
        other_id = thread.candidate_id if viewer_is_recruiter else thread.recruiter_id
        other = users.get(other_id)
        counterpart: dict[str, Any] = {"id": other_id, "name": other.name if other else None}
        if not viewer_is_recruiter:
            company_id = thread.company_id or (other.company_id if other else None)
            counterpart["companyName"] = company_names.get(company_id) if company_id else None
        items.append(
            {
                "id": thread.id,
                "counterpart": counterpart,
                "lastMessage": _last_message_dict(last_messages.get(thread.id)),
                "unreadCount": int(unread.get(thread.id, 0)),
                "lastMessageAt": thread.last_message_at,
                "createdAt": thread.created_at,
            }
        )
    return items


# --------------------------------------------------------------------------- threads
def _own_threads_filter(user: User):
    if UserRole(user.role) == UserRole.RECRUITER:
        return MessageThread.recruiter_id == user.id
    return MessageThread.candidate_id == user.id


def list_threads(db: Session, user: User, params: PageParams) -> tuple[list[dict[str, Any]], int]:
    stmt = (
        select(MessageThread)
        .where(_own_threads_filter(user))
        .order_by(MessageThread.last_message_at.desc().nulls_last(), MessageThread.id)
    )
    threads, total = paginate(db, stmt, params)
    return _serialize_threads(db, threads, user), total


def get_participant_thread(db: Session, user: User, thread_id: uuid.UUID) -> MessageThread:
    thread = db.get(MessageThread, thread_id)
    if thread is None or user.id not in (thread.recruiter_id, thread.candidate_id):
        raise NotFoundError("Thread not found")
    return thread


def _find_or_create_thread(db: Session, recruiter: User, candidate_id: uuid.UUID) -> MessageThread:
    stmt = select(MessageThread).where(
        MessageThread.recruiter_id == recruiter.id, MessageThread.candidate_id == candidate_id
    )
    thread = db.scalar(stmt)
    if thread is not None:
        return thread
    thread = MessageThread(
        id=uuid.uuid4(),
        recruiter_id=recruiter.id,
        candidate_id=candidate_id,
        company_id=recruiter.company_id,
        created_at=_now(),
        last_message_at=_now(),
    )
    try:
        with db.begin_nested():
            db.add(thread)
    except IntegrityError:
        # concurrent creation of the same (recruiter, candidate) thread: reuse the winner
        existing = db.scalar(stmt)
        if existing is None:
            raise
        return existing
    return thread


def _append_message(db: Session, thread: MessageThread, sender: User, body: str) -> Message:
    now = _now()
    message = Message(id=uuid.uuid4(), thread_id=thread.id, sender_id=sender.id, body=body, created_at=now)
    db.add(message)
    thread.last_message_at = now
    recipient_id = thread.candidate_id if sender.id == thread.recruiter_id else thread.recruiter_id
    snippet = body if len(body) <= SNIPPET_LENGTH else body[: SNIPPET_LENGTH - 1] + "…"
    notify(
        db,
        recipient_id,
        Category.MESSAGE,
        f"New message from {sender.name}",
        snippet,
        email=False,
        data={"threadId": str(thread.id)},
    )
    return message


def _single_thread_dict(db: Session, thread: MessageThread, viewer: User) -> dict[str, Any]:
    return _serialize_threads(db, [thread], viewer)[0]


def create_thread(
    db: Session,
    user: User,
    body: str,
    candidate_id: uuid.UUID | None,
    recruiter_id: uuid.UUID | None,
) -> dict[str, Any]:
    """Recruiter: start (or reuse) a thread with an eligible candidate.
    Candidate: may only reply into a thread a recruiter already opened."""
    role = UserRole(user.role)
    if role == UserRole.RECRUITER:
        if candidate_id is None:
            raise BadRequestError("candidateId is required for recruiters")
        candidate = db.scalar(
            select(User).where(
                User.id == candidate_id,
                User.role == UserRole.JOB_SEEKER,
                User.deleted_at.is_(None),
                User.is_blocked.is_(False),
            )
        )
        if candidate is None:
            raise NotFoundError("Candidate not found")
        _require_eligibility(db, user, candidate.id)
        thread = _find_or_create_thread(db, user, candidate.id)
    else:
        if recruiter_id is None:
            raise BadRequestError("recruiterId is required for candidates")
        thread = db.scalar(
            select(MessageThread).where(
                MessageThread.recruiter_id == recruiter_id, MessageThread.candidate_id == user.id
            )
        )
        if thread is None:
            raise _not_allowed("Candidates can only reply to recruiters who have contacted them first")
    message = _append_message(db, thread, user, body)
    db.commit()
    result = _single_thread_dict(db, thread, user)
    result["message"] = serialize_message(message, user.id)
    return result


# --------------------------------------------------------------------------- messages
def list_messages(
    db: Session,
    user: User,
    thread_id: uuid.UUID,
    params: PageParams,
    order: Literal["asc", "desc"],
) -> tuple[list[dict[str, Any]], int]:
    thread = get_participant_thread(db, user, thread_id)
    if order == "asc":
        ordering = (Message.created_at.asc(), Message.id.asc())
    else:
        ordering = (Message.created_at.desc(), Message.id.desc())
    stmt = select(Message).where(Message.thread_id == thread.id).order_by(*ordering)
    rows, total = paginate(db, stmt, params)
    return [serialize_message(m, user.id) for m in rows], total


def post_message(db: Session, user: User, thread_id: uuid.UUID, body: str) -> dict[str, Any]:
    thread = get_participant_thread(db, user, thread_id)
    if UserRole(user.role) == UserRole.RECRUITER:
        _require_eligibility(db, user, thread.candidate_id)
    message = _append_message(db, thread, user, body)
    db.commit()
    return serialize_message(message, user.id)


def mark_thread_read(db: Session, user: User, thread_id: uuid.UUID) -> int:
    thread = get_participant_thread(db, user, thread_id)
    result = db.execute(
        update(Message)
        .where(
            Message.thread_id == thread.id,
            Message.sender_id != user.id,
            Message.read_at.is_(None),
        )
        .values(read_at=_now())
    )
    db.commit()
    return int(result.rowcount or 0)


def total_unread(db: Session, user: User) -> int:
    return int(
        db.scalar(
            select(func.count(Message.id))
            .join(MessageThread, MessageThread.id == Message.thread_id)
            .where(
                or_(MessageThread.recruiter_id == user.id, MessageThread.candidate_id == user.id),
                Message.sender_id != user.id,
                Message.read_at.is_(None),
            )
        )
        or 0
    )
