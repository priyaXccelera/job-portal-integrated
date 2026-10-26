"""Company credit ledger: spending, top-ups and idempotent contact unlocks.

All mutating helpers row-lock the company (``SELECT ... FOR UPDATE``) so the balance can never
go negative and concurrent unlocks of the same candidate are serialised. None of them commit.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import settings
from app.core.errors import AppError, BadRequestError, ConflictError
from app.db import utcnow
from app.models.accounts import User
from app.models.company import Company, ContactUnlock, CreditLog

logger = logging.getLogger(__name__)


def lock_company(db: Session, company: Company) -> Company:
    """Row-lock the company and refresh its counters from the database."""
    locked = db.scalar(
        select(Company).where(Company.id == company.id).with_for_update().execution_options(populate_existing=True)
    )
    if locked is None:
        raise BadRequestError("Company no longer exists")
    return locked


def _write_log(
    db: Session,
    company: Company,
    delta: int,
    reason: str,
    user_id: uuid.UUID | None,
    ref_type: str | None,
    ref_id: str | uuid.UUID | None,
) -> CreditLog:
    entry = CreditLog(
        id=uuid.uuid4(),
        company_id=company.id,
        user_id=user_id,
        delta=delta,
        balance_after=company.credits,
        reason=reason[:255],
        ref_type=ref_type,
        ref_id=str(ref_id) if ref_id is not None else None,
        created_at=utcnow(),
    )
    db.add(entry)
    db.flush()
    return entry


def spend(
    db: Session,
    company: Company,
    amount: int,
    reason: str,
    user_id: uuid.UUID | None = None,
    ref_type: str | None = None,
    ref_id: str | uuid.UUID | None = None,
) -> CreditLog:
    """Deduct ``amount`` credits (402 INSUFFICIENT_CREDITS when the balance is too low)."""
    if amount <= 0:
        raise BadRequestError("Amount to spend must be positive")
    company = lock_company(db, company)
    if company.credits < amount:
        raise AppError(
            402,
            "INSUFFICIENT_CREDITS",
            f"Insufficient credits: {amount} required, {company.credits} available",
            [{"field": "credits", "message": f"required {amount}, balance {company.credits}"}],
        )
    company.credits -= amount
    return _write_log(db, company, -amount, reason, user_id, ref_type, ref_id)


def add_credits(
    db: Session,
    company: Company,
    amount: int,
    reason: str,
    user_id: uuid.UUID | None = None,
) -> CreditLog:
    """Top up ``amount`` credits and record it in the log."""
    if amount <= 0:
        raise BadRequestError("Amount to add must be positive")
    company = lock_company(db, company)
    company.credits += amount
    return _write_log(db, company, amount, reason, user_id, "TOPUP", None)


def is_unlocked(db: Session, company_id: uuid.UUID, candidate_id: uuid.UUID) -> bool:
    return (
        db.scalar(
            select(ContactUnlock.id).where(
                ContactUnlock.company_id == company_id, ContactUnlock.candidate_id == candidate_id
            )
        )
        is not None
    )


def unlocked_ids(db: Session, company_id: uuid.UUID, candidate_ids: list[uuid.UUID]) -> set[uuid.UUID]:
    """Batch variant of :func:`is_unlocked` (single query)."""
    if not candidate_ids:
        return set()
    return set(
        db.scalars(
            select(ContactUnlock.candidate_id).where(
                ContactUnlock.company_id == company_id, ContactUnlock.candidate_id.in_(candidate_ids)
            )
        ).all()
    )


def unlock_contact(
    db: Session, company: Company, candidate_id: uuid.UUID, user: User
) -> tuple[ContactUnlock, bool]:
    """Unlock a candidate's contact details once per company.

    Returns ``(unlock, charged)``; a repeat call is free and returns ``charged=False``.
    The company row lock serialises concurrent unlocks, the unique constraint is the backstop.
    """
    company = lock_company(db, company)
    existing: ContactUnlock | None = db.scalar(
        select(ContactUnlock).where(
            ContactUnlock.company_id == company.id, ContactUnlock.candidate_id == candidate_id
        )
    )
    if existing is not None:
        return existing, False

    cost = settings.unlock_credit_cost
    if cost > 0:
        spend(db, company, cost, "Unlocked candidate contact", user.id, "CANDIDATE", candidate_id)
    unlock = ContactUnlock(
        id=uuid.uuid4(),
        company_id=company.id,
        candidate_id=candidate_id,
        unlocked_by=user.id,
        created_at=utcnow(),
    )
    db.add(unlock)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        logger.warning("Concurrent unlock race for company %s candidate %s", company.id, candidate_id)
        raise ConflictError("Candidate was unlocked concurrently, retry the request") from exc
    return unlock, True


def serialize_log(entry: CreditLog) -> dict[str, Any]:
    return {
        "id": entry.id,
        "delta": entry.delta,
        "balanceAfter": entry.balance_after,
        "reason": entry.reason,
        "refType": entry.ref_type,
        "refId": entry.ref_id,
        "createdAt": entry.created_at,
        "userId": entry.user_id,
    }
