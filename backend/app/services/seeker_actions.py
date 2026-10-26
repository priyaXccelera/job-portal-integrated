"""Seeker-side actions: saved jobs, company follows, reviews, job reports and searches."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import Select, delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError
from app.models.company import Company, CompanyFollow, CompanyReview
from app.models.enums import CompanyStatus, JobStatus, ReportReason, ReportStatus, ReviewStatus
from app.models.jobs import Job, JobReport, RecentSearch, SavedJob, SavedSearch

logger = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now(timezone.utc)


# --------------------------------------------------------------------------- saved jobs


def saved_jobs_stmt(user_id: uuid.UUID, sort: str, order: str) -> Select[Any]:
    """Saved (non-deleted) jobs of a user as ``(Job, saved_at)`` rows."""
    column = Job.posted_at if sort == "postedAt" else SavedJob.created_at
    ordering = column.asc() if order == "asc" else column.desc()
    return (
        select(Job, SavedJob.created_at)
        .join(SavedJob, SavedJob.job_id == Job.id)
        .where(SavedJob.user_id == user_id, Job.deleted_at.is_(None))
        .order_by(ordering.nulls_last(), SavedJob.id)
    )


def get_existing_job(db: Session, job_id: uuid.UUID) -> Job:
    job = db.scalar(select(Job).where(Job.id == job_id, Job.deleted_at.is_(None)))
    if job is None:
        raise NotFoundError("Job not found")
    return job


def save_job(db: Session, user_id: uuid.UUID, job_id: uuid.UUID) -> bool:
    """Idempotently save a job. Returns True when a new row was created. Does not commit."""
    get_existing_job(db, job_id)
    if db.scalar(select(SavedJob.id).where(SavedJob.user_id == user_id, SavedJob.job_id == job_id)) is not None:
        return False
    try:
        with db.begin_nested():
            db.add(SavedJob(id=uuid.uuid4(), user_id=user_id, job_id=job_id, created_at=_now()))
    except IntegrityError:
        return False  # concurrent save won the race (uq_saved_job_user_job)
    return True


def unsave_job(db: Session, user_id: uuid.UUID, job_id: uuid.UUID) -> bool:
    """Remove a saved job; True if a row was removed. Does not commit."""
    result = db.execute(delete(SavedJob).where(SavedJob.user_id == user_id, SavedJob.job_id == job_id))
    return (result.rowcount or 0) > 0


# --------------------------------------------------------------------------- follows


def _approved_company(db: Session, company_id: uuid.UUID) -> Company:
    company = db.scalar(
        select(Company).where(
            Company.id == company_id, Company.deleted_at.is_(None), Company.status == CompanyStatus.APPROVED
        )
    )
    if company is None:
        raise NotFoundError("Company not found")
    return company


def following_stmt(user_id: uuid.UUID) -> Select[Any]:
    return (
        select(Company, CompanyFollow.created_at)
        .join(CompanyFollow, CompanyFollow.company_id == Company.id)
        .where(CompanyFollow.user_id == user_id, Company.deleted_at.is_(None))
        .order_by(CompanyFollow.created_at.desc(), CompanyFollow.id)
    )


def serialize_following(db: Session, rows: list[Any]) -> list[dict[str, Any]]:
    """Serialize ``(Company, followed_at)`` rows with a batched open-jobs count."""
    if not rows:
        return []
    ids = [company.id for company, _ in rows]
    open_counts = dict(
        db.execute(
            select(Job.company_id, func.count())
            .where(Job.company_id.in_(ids), Job.status == JobStatus.ACTIVE, Job.deleted_at.is_(None))
            .group_by(Job.company_id)
        ).all()
    )
    return [
        {
            "id": company.id,
            "name": company.name,
            "logoUrl": company.logo_url,
            "industry": company.industry,
            "headquarters": company.headquarters,
            "verified": company.verified,
            "openJobs": int(open_counts.get(company.id, 0)),
            "followedAt": followed_at,
        }
        for company, followed_at in rows
    ]


def follow_company(db: Session, user_id: uuid.UUID, company_id: uuid.UUID) -> bool:
    """Idempotent follow of an approved company; True when newly followed. Does not commit."""
    _approved_company(db, company_id)
    if (
        db.scalar(
            select(CompanyFollow.id).where(CompanyFollow.user_id == user_id, CompanyFollow.company_id == company_id)
        )
        is not None
    ):
        return False
    try:
        with db.begin_nested():
            db.add(CompanyFollow(id=uuid.uuid4(), user_id=user_id, company_id=company_id, created_at=_now()))
    except IntegrityError:
        return False
    return True


def unfollow_company(db: Session, user_id: uuid.UUID, company_id: uuid.UUID) -> bool:
    result = db.execute(
        delete(CompanyFollow).where(CompanyFollow.user_id == user_id, CompanyFollow.company_id == company_id)
    )
    return (result.rowcount or 0) > 0


# --------------------------------------------------------------------------- reviews & reports


def add_review(
    db: Session, user_id: uuid.UUID, company_id: uuid.UUID, rating: int, title: str | None, body: str | None
) -> CompanyReview:
    """Create a PENDING review (one per user/company). Does not commit."""
    _approved_company(db, company_id)
    already = db.scalar(
        select(CompanyReview.id).where(CompanyReview.company_id == company_id, CompanyReview.user_id == user_id)
    )
    if already is not None:
        raise ConflictError("You have already reviewed this company")
    review = CompanyReview(
        id=uuid.uuid4(),
        company_id=company_id,
        user_id=user_id,
        rating=rating,
        title=title,
        body=body,
        status=ReviewStatus.PENDING,
        created_at=_now(),
    )
    try:
        with db.begin_nested():
            db.add(review)
    except IntegrityError as exc:
        raise ConflictError("You have already reviewed this company") from exc
    return review


def serialize_review(review: CompanyReview) -> dict[str, Any]:
    return {
        "id": review.id,
        "companyId": review.company_id,
        "rating": review.rating,
        "title": review.title,
        "body": review.body,
        "status": review.status,
        "createdAt": review.created_at,
    }


def report_job(
    db: Session, user_id: uuid.UUID, job_id: uuid.UUID, reason: ReportReason, details: str | None
) -> JobReport:
    """File a report; one OPEN report per user/job. Does not commit."""
    get_existing_job(db, job_id)
    open_report = db.scalar(
        select(JobReport.id).where(
            JobReport.job_id == job_id, JobReport.user_id == user_id, JobReport.status == ReportStatus.OPEN
        )
    )
    if open_report is not None:
        raise ConflictError("You have already reported this job")
    report = JobReport(
        id=uuid.uuid4(),
        job_id=job_id,
        user_id=user_id,
        reason=ReportReason(reason),
        details=details,
        status=ReportStatus.OPEN,
        created_at=_now(),
    )
    db.add(report)
    db.flush()
    return report


def serialize_report(report: JobReport) -> dict[str, Any]:
    return {
        "id": report.id,
        "jobId": report.job_id,
        "reason": report.reason,
        "details": report.details,
        "status": report.status,
        "createdAt": report.created_at,
    }


# --------------------------------------------------------------------------- searches


def recent_searches_stmt(user_id: uuid.UUID) -> Select[Any]:
    return select(RecentSearch).where(RecentSearch.user_id == user_id).order_by(
        RecentSearch.created_at.desc(), RecentSearch.id
    )


def clear_recent_searches(db: Session, user_id: uuid.UUID) -> int:
    result = db.execute(delete(RecentSearch).where(RecentSearch.user_id == user_id))
    return result.rowcount or 0


def serialize_recent_search(item: RecentSearch) -> dict[str, Any]:
    return {"id": item.id, "query": item.query, "filters": item.filters or {}, "createdAt": item.created_at}


def saved_searches_stmt(user_id: uuid.UUID) -> Select[Any]:
    return select(SavedSearch).where(SavedSearch.user_id == user_id).order_by(
        SavedSearch.created_at.desc(), SavedSearch.id
    )


def create_saved_search(
    db: Session, user_id: uuid.UUID, name: str, query: str | None, filters: dict[str, Any] | None
) -> SavedSearch:
    item = SavedSearch(
        id=uuid.uuid4(), user_id=user_id, name=name, query=query, filters=filters or {}, created_at=_now()
    )
    db.add(item)
    db.flush()
    return item


def delete_saved_search(db: Session, user_id: uuid.UUID, search_id: uuid.UUID) -> None:
    item = db.scalar(select(SavedSearch).where(SavedSearch.id == search_id, SavedSearch.user_id == user_id))
    if item is None:
        raise NotFoundError("Saved search not found")
    db.delete(item)
    db.flush()


def serialize_saved_search(item: SavedSearch) -> dict[str, Any]:
    return {
        "id": item.id,
        "name": item.name,
        "query": item.query,
        "filters": item.filters or {},
        "createdAt": item.created_at,
    }
