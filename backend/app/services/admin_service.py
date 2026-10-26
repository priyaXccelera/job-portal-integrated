"""Admin business logic: companies, job moderation, reports, reviews, master data, users, audit log.

Every mutating action writes an ``AuditLog`` row through :func:`audit` and commits once at the end.
"""

from __future__ import annotations

import logging
import uuid
from datetime import date, datetime, time, timedelta, timezone
from typing import Any

from pydantic import ValidationError
from sqlalchemy import ColumnElement, Select, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import settings
from app.core.errors import AppError, BadRequestError, ConflictError, ForbiddenError, NotFoundError
from app.core.responses import PageParams, paginate, to_jsonable
from app.core.security import hash_token, new_refresh_token
from app.db import utcnow
from app.models.accounts import AuditLog, EmailToken, RefreshToken, User
from app.models.applications import Application
from app.models.company import Company, CompanyReview, CreditLog
from app.models.enums import (
    CompanyStatus,
    JobStatus,
    ReportStatus,
    ReviewStatus,
    UserRole,
)
from app.models.jobs import Job, JobReport
from app.models.master import MASTER_TYPES, Location
from app.schemas.admin import validate_master_payload
from app.services.alerts import notify_followers_of_job
from app.services.job_index import reindex_job
from app.services.notifications import Category, notify
from app.services.senders import SenderError, get_email_sender

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- shared helpers


def audit(
    db: Session,
    actor: User | None,
    action: str,
    entity_type: str,
    entity_id: uuid.UUID | str | None,
    details: dict[str, Any] | None = None,
) -> AuditLog:
    """Add (not commit) an audit row describing an admin action."""
    entry = AuditLog(
        actor_id=actor.id if actor is not None else None,
        action=action,
        entity_type=entity_type,
        entity_id=str(entity_id) if entity_id is not None else None,
        details=to_jsonable(details or {}),
    )
    db.add(entry)
    return entry


def _like(term: str) -> str:
    escaped = term.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _enum_value(value: Any) -> Any:
    return value.value if hasattr(value, "value") else value


def _order(column: ColumnElement[Any], order: str) -> ColumnElement[Any]:
    return column.asc() if order == "asc" else column.desc()


def _end_of_day(day: date) -> datetime:
    return datetime.combine(day + timedelta(days=1), time.min, tzinfo=timezone.utc)


def _start_of_day(day: date) -> datetime:
    return datetime.combine(day, time.min, tzinfo=timezone.utc)


def _commit_or_conflict(db: Session, message: str) -> None:
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        logger.warning("Integrity error during admin action: %s", exc.orig)
        raise ConflictError(message) from exc


# =========================================================================== companies

COMPANY_SORTS = {
    "createdAt": Company.created_at,
    "name": Company.name,
    "credits": Company.credits,
    "jobsPosted": Company.jobs_posted,
    "status": Company.status,
}

_RECRUITER_COUNT = (
    select(func.count(User.id))
    .where(User.company_id == Company.id, User.deleted_at.is_(None))
    .correlate(Company)
    .scalar_subquery()
)
_ACTIVE_JOB_COUNT = (
    select(func.count(Job.id))
    .where(Job.company_id == Company.id, Job.status == JobStatus.ACTIVE, Job.deleted_at.is_(None))
    .correlate(Company)
    .scalar_subquery()
)


def _company_select() -> Select[Any]:
    return select(
        Company,
        _RECRUITER_COUNT.label("recruiters"),
        _ACTIVE_JOB_COUNT.label("active_jobs"),
    ).where(Company.deleted_at.is_(None))


def serialize_company(company: Company, recruiters: int, active_jobs: int) -> dict[str, Any]:
    return {
        "id": company.id,
        "name": company.name,
        "logoUrl": company.logo_url,
        "industry": company.industry,
        "companyType": company.company_type,
        "status": company.status,
        "statusReason": company.status_reason,
        "verified": company.verified,
        "recruiters": int(recruiters),
        "jobsPosted": company.jobs_posted,
        "activeJobs": int(active_jobs),
        "credits": company.credits,
        "jobQuota": company.job_quota,
        "createdAt": company.created_at,
        "updatedAt": company.updated_at,
    }


def list_companies(
    db: Session,
    params: PageParams,
    *,
    status: CompanyStatus | None,
    q: str | None,
    verified: bool | None,
    sort: str,
    order: str,
) -> tuple[list[dict[str, Any]], int]:
    stmt = _company_select()
    if status is not None:
        stmt = stmt.where(Company.status == status)
    if q and q.strip():
        stmt = stmt.where(Company.name.ilike(_like(q), escape="\\"))
    if verified is not None:
        stmt = stmt.where(Company.verified.is_(verified))
    stmt = stmt.order_by(_order(COMPANY_SORTS[sort], order), Company.id)
    rows, total = paginate(db, stmt, params)
    return [serialize_company(c, r, a) for c, r, a in rows], total


def _company_row(db: Session, company_id: uuid.UUID) -> Any:
    row = db.execute(_company_select().where(Company.id == company_id)).one_or_none()
    if row is None:
        raise NotFoundError("Company not found")
    return row


def company_detail(db: Session, company_id: uuid.UUID) -> dict[str, Any]:
    company, recruiters, active_jobs = _company_row(db, company_id)
    data = serialize_company(company, recruiters, active_jobs)
    members = db.execute(
        select(User.id, User.name, User.email, User.is_company_admin, User.is_blocked)
        .where(User.company_id == company_id, User.deleted_at.is_(None))
        .order_by(User.created_at)
    ).all()
    data.update(
        {
            "website": company.website,
            "description": company.description,
            "headquarters": company.headquarters,
            "sizeRange": company.size_range,
            "foundedYear": company.founded_year,
            "recruiterList": [
                {
                    "id": m.id,
                    "name": m.name,
                    "email": m.email,
                    "isCompanyAdmin": m.is_company_admin,
                    "isBlocked": m.is_blocked,
                }
                for m in members
            ],
        }
    )
    return data


def _get_company(db: Session, company_id: uuid.UUID, lock: bool = False) -> Company:
    stmt = select(Company).where(Company.id == company_id, Company.deleted_at.is_(None))
    if lock:
        stmt = stmt.with_for_update()
    company = db.scalar(stmt)
    if company is None:
        raise NotFoundError("Company not found")
    return company


def _close_active_jobs(db: Session, company_id: uuid.UUID, reason: str) -> int:
    result = db.execute(
        update(Job)
        .where(Job.company_id == company_id, Job.status == JobStatus.ACTIVE, Job.deleted_at.is_(None))
        .values(status=JobStatus.CLOSED, reject_reason=reason, updated_at=utcnow())
    )
    return int(result.rowcount or 0)


def _notify_company_recruiters(db: Session, company: Company, status: CompanyStatus, reason: str | None) -> int:
    if status == CompanyStatus.APPROVED:
        category = Category.RECRUITER_APPROVED
        title = f"{company.name} has been approved"
        body = f"Good news! {company.name} is now approved and you can start posting jobs."
    elif status in (CompanyStatus.REJECTED, CompanyStatus.BLOCKED):
        category = Category.RECRUITER_REJECTED
        verb = "rejected" if status == CompanyStatus.REJECTED else "blocked"
        title = f"{company.name} has been {verb}"
        body = f"{company.name} was {verb} by the platform administrators. Reason: {reason}"
    else:
        return 0
    user_ids = db.scalars(
        select(User.id).where(User.company_id == company.id, User.deleted_at.is_(None))
    ).all()
    sent = 0
    for user_id in user_ids:
        created = notify(
            db,
            user_id,
            category,
            title,
            body,
            email=True,
            data={"companyId": str(company.id), "status": status.value, "reason": reason},
        )
        sent += 1 if created is not None else 0
    return sent


_COMPANY_STATUS_ACTIONS = {
    CompanyStatus.APPROVED: "COMPANY_APPROVED",
    CompanyStatus.REJECTED: "COMPANY_REJECTED",
    CompanyStatus.BLOCKED: "COMPANY_BLOCKED",
    CompanyStatus.PENDING: "COMPANY_SET_PENDING",
}


def set_company_status(
    db: Session, admin: User, company_id: uuid.UUID, status: CompanyStatus, reason: str | None
) -> dict[str, Any]:
    company = _get_company(db, company_id, lock=True)
    previous = company.status
    company.status = status
    company.status_reason = reason
    closed = 0
    if status == CompanyStatus.BLOCKED:
        closed = _close_active_jobs(db, company.id, f"Company blocked: {reason}")
    db.flush()
    notified = _notify_company_recruiters(db, company, status, reason)
    audit(
        db,
        admin,
        _COMPANY_STATUS_ACTIONS[status],
        "Company",
        company.id,
        {
            "reason": reason,
            "previousStatus": previous,
            "status": status,
            "jobsClosed": closed,
            "recruitersNotified": notified,
        },
    )
    db.commit()
    return company_detail(db, company_id)


def set_company_verified(db: Session, admin: User, company_id: uuid.UUID, verified: bool) -> dict[str, Any]:
    company = _get_company(db, company_id, lock=True)
    company.verified = verified
    audit(db, admin, "COMPANY_VERIFIED" if verified else "COMPANY_UNVERIFIED", "Company", company.id,
          {"verified": verified})
    db.commit()
    return company_detail(db, company_id)


def adjust_credits(db: Session, admin: User, company_id: uuid.UUID, amount: int, reason: str) -> dict[str, Any]:
    company = _get_company(db, company_id, lock=True)  # row lock serialises concurrent adjustments
    new_balance = company.credits + amount
    if new_balance < 0:
        raise AppError(
            422,
            "VALIDATION_ERROR",
            f"Cannot deduct {abs(amount)} credits: company only has {company.credits}",
            [{"field": "amount", "message": "deduction exceeds the current balance"}],
        )
    company.credits = new_balance
    entry = CreditLog(
        company_id=company.id,
        user_id=admin.id,
        delta=amount,
        balance_after=new_balance,
        reason=reason,
        ref_type="ADMIN_ADJUSTMENT",
        ref_id=str(admin.id),
    )
    db.add(entry)
    audit(db, admin, "COMPANY_CREDITS_ADJUSTED", "Company", company.id,
          {"amount": amount, "reason": reason, "balanceAfter": new_balance})
    db.commit()
    data = company_detail(db, company_id)
    data["creditLog"] = {"id": entry.id, "delta": amount, "balanceAfter": new_balance, "reason": reason}
    return data


def set_company_quota(db: Session, admin: User, company_id: uuid.UUID, job_quota: int) -> dict[str, Any]:
    company = _get_company(db, company_id, lock=True)
    previous = company.job_quota
    company.job_quota = job_quota
    audit(db, admin, "COMPANY_QUOTA_UPDATED", "Company", company.id,
          {"previousQuota": previous, "jobQuota": job_quota})
    db.commit()
    return company_detail(db, company_id)


def delete_company(db: Session, admin: User, company_id: uuid.UUID) -> None:
    company = _get_company(db, company_id, lock=True)
    company.deleted_at = utcnow()
    closed = _close_active_jobs(db, company.id, "Company removed by administrator")
    audit(db, admin, "COMPANY_DELETED", "Company", company.id, {"name": company.name, "jobsClosed": closed})
    db.commit()


# =========================================================================== jobs

JOB_SORTS = {
    "createdAt": Job.created_at,
    "postedAt": Job.posted_at,
    "title": Job.title,
    "applications": Job.application_count,
}

_OPEN_REPORTS = (
    select(func.count(JobReport.id))
    .where(JobReport.job_id == Job.id, JobReport.status == ReportStatus.OPEN)
    .correlate(Job)
    .scalar_subquery()
)


def _job_select() -> Select[Any]:
    return (
        select(Job, Company.name.label("company_name"), Company.status.label("company_status"),
               _OPEN_REPORTS.label("open_reports"))
        .join(Company, Company.id == Job.company_id)
        .where(Job.deleted_at.is_(None))
    )


def serialize_job(job: Job, company_name: str, company_status: Any, open_reports: int, detail: bool = False) -> dict[str, Any]:
    data: dict[str, Any] = {
        "id": job.id,
        "title": job.title,
        "companyId": job.company_id,
        "companyName": company_name,
        "companyStatus": company_status,
        "postedBy": job.posted_by,
        "status": job.status,
        "rejectReason": job.reject_reason,
        "locations": list(job.locations or []),
        "industry": job.industry,
        "department": job.department,
        "jobType": job.job_type,
        "workMode": job.work_mode,
        "openReports": int(open_reports),
        "applicationCount": job.application_count,
        "viewCount": job.view_count,
        "postedAt": job.posted_at,
        "expiresAt": job.expires_at,
        "createdAt": job.created_at,
        "updatedAt": job.updated_at,
    }
    if detail:
        data.update(
            {
                "description": job.description,
                "responsibilities": job.responsibilities,
                "requiredSkills": list(job.required_skills or []),
                "preferredSkills": list(job.preferred_skills or []),
                "experienceMin": job.experience_min,
                "experienceMax": job.experience_max,
                "salaryMin": job.salary_min,
                "salaryMax": job.salary_max,
                "hideSalary": job.hide_salary,
                "employmentType": job.employment_type,
                "openings": job.openings,
                "roleCategory": job.role_category,
                "education": job.education,
                "deadline": job.deadline,
            }
        )
    return data


def list_jobs(
    db: Session,
    params: PageParams,
    *,
    status: JobStatus | None,
    q: str | None,
    company_id: uuid.UUID | None,
    sort: str,
    order: str,
) -> tuple[list[dict[str, Any]], int]:
    stmt = _job_select()
    if status is not None:
        stmt = stmt.where(Job.status == status)
    if company_id is not None:
        stmt = stmt.where(Job.company_id == company_id)
    if q and q.strip():
        pattern = _like(q)
        stmt = stmt.where(or_(Job.title.ilike(pattern, escape="\\"), Company.name.ilike(pattern, escape="\\")))
    stmt = stmt.order_by(_order(JOB_SORTS[sort], order).nulls_last(), Job.id)
    rows, total = paginate(db, stmt, params)
    return [serialize_job(*row) for row in rows], total


def moderation_queue(db: Session, params: PageParams) -> tuple[list[dict[str, Any]], int]:
    stmt = (
        _job_select()
        .where(Job.status == JobStatus.PENDING_REVIEW)
        .order_by(Job.updated_at.asc(), Job.id)
    )
    rows, total = paginate(db, stmt, params)
    return [serialize_job(*row) for row in rows], total


def _job_row(db: Session, job_id: uuid.UUID) -> Any:
    row = db.execute(_job_select().where(Job.id == job_id)).one_or_none()
    if row is None:
        raise NotFoundError("Job not found")
    return row


def job_detail(db: Session, job_id: uuid.UUID) -> dict[str, Any]:
    return serialize_job(*_job_row(db, job_id), detail=True)


def _lock_job(db: Session, job_id: uuid.UUID) -> Job:
    job = db.scalar(select(Job).where(Job.id == job_id, Job.deleted_at.is_(None)).with_for_update())
    if job is None:
        raise NotFoundError("Job not found")
    return job


def _invalid_transition(job: Job, target: JobStatus) -> AppError:
    return AppError(409, "INVALID_TRANSITION", f"Job is {job.status.value}; cannot move to {target.value}")


def _approve_job(db: Session, admin: User, job: Job) -> None:
    if job.status == JobStatus.ACTIVE:
        raise _invalid_transition(job, JobStatus.ACTIVE)
    if job.status == JobStatus.DRAFT:
        raise AppError(409, "INVALID_TRANSITION", "Draft jobs have not been submitted by the recruiter")
    company = db.get(Company, job.company_id)
    if company is None or company.deleted_at is not None or company.status == CompanyStatus.BLOCKED:
        raise ConflictError("The job's company is blocked or removed; it cannot be activated")
    previous = job.status
    now = utcnow()
    if job.posted_at is None:
        job.posted_at = now
    if job.expires_at is None or job.expires_at <= now:
        job.expires_at = now + timedelta(days=settings.job_expiry_days)
    job.status = JobStatus.ACTIVE
    job.reject_reason = None
    db.flush()
    reindex_job(db, job.id)
    followers = 0
    if previous == JobStatus.PENDING_REVIEW:
        followers = notify_followers_of_job(db, job)
    if job.posted_by is not None:
        notify(
            db,
            job.posted_by,
            Category.JOB_APPROVED,
            f"Your job '{job.title}' was approved",
            f"'{job.title}' passed moderation and is now live.",
            email=True,
            data={"jobId": str(job.id)},
        )
    audit(db, admin, "JOB_APPROVED", "Job", job.id,
          {"previousStatus": previous, "title": job.title, "followersNotified": followers})


def _reject_job(db: Session, admin: User, job: Job, reason: str) -> None:
    if job.status == JobStatus.REJECTED:
        raise _invalid_transition(job, JobStatus.REJECTED)
    previous = job.status
    job.status = JobStatus.REJECTED
    job.reject_reason = reason
    if job.posted_by is not None:
        notify(
            db,
            job.posted_by,
            Category.JOB_REJECTED,
            f"Your job '{job.title}' was rejected",
            f"'{job.title}' was rejected during moderation. Reason: {reason}",
            email=True,
            data={"jobId": str(job.id), "reason": reason},
        )
    audit(db, admin, "JOB_REJECTED", "Job", job.id, {"reason": reason, "previousStatus": previous, "title": job.title})


def _takedown_job(db: Session, admin: User, job: Job, reason: str, extra: dict[str, Any] | None = None) -> None:
    if job.status == JobStatus.CLOSED:
        raise _invalid_transition(job, JobStatus.CLOSED)
    previous = job.status
    job.status = JobStatus.CLOSED
    job.reject_reason = reason
    if job.posted_by is not None:
        notify(
            db,
            job.posted_by,
            Category.JOB_REJECTED,
            f"Your job '{job.title}' was taken down",
            f"'{job.title}' was taken down by the platform administrators. Reason: {reason}",
            email=True,
            data={"jobId": str(job.id), "reason": reason, "takedown": True},
        )
    audit(db, admin, "JOB_TAKEN_DOWN", "Job", job.id,
          {"reason": reason, "previousStatus": previous, "title": job.title, **(extra or {})})


def set_job_status(
    db: Session, admin: User, job_id: uuid.UUID, status: JobStatus, reason: str | None
) -> dict[str, Any]:
    job = _lock_job(db, job_id)
    if status == JobStatus.ACTIVE:
        _approve_job(db, admin, job)
    elif status == JobStatus.REJECTED:
        _reject_job(db, admin, job, reason or "")
    elif status == JobStatus.CLOSED:
        _takedown_job(db, admin, job, reason or "")
    else:  # guarded by the request schema; defensive for direct callers
        raise BadRequestError("Unsupported target status")
    db.commit()
    return job_detail(db, job_id)


# =========================================================================== job reports


def _report_select() -> Select[Any]:
    return (
        select(
            JobReport,
            Job.title.label("job_title"),
            Job.status.label("job_status"),
            Company.name.label("company_name"),
        )
        .join(Job, Job.id == JobReport.job_id)
        .join(Company, Company.id == Job.company_id)
    )


def serialize_report(report: JobReport, job_title: str, job_status: Any, company_name: str) -> dict[str, Any]:
    return {
        "id": report.id,
        "jobId": report.job_id,
        "jobTitle": job_title,
        "jobStatus": job_status,
        "companyName": company_name,
        "reporterId": report.user_id,
        "reason": report.reason,
        "details": report.details,
        "status": report.status,
        "createdAt": report.created_at,
    }


def list_reports(db: Session, params: PageParams, status: ReportStatus | None) -> tuple[list[dict[str, Any]], int]:
    stmt = _report_select()
    if status is not None:
        stmt = stmt.where(JobReport.status == status)
    rows, total = paginate(db, stmt.order_by(JobReport.created_at.desc(), JobReport.id), params)
    return [serialize_report(*row) for row in rows], total


def update_report(
    db: Session, admin: User, report_id: uuid.UUID, status: ReportStatus, takedown: bool, reason: str | None
) -> dict[str, Any]:
    report = db.scalar(select(JobReport).where(JobReport.id == report_id).with_for_update())
    if report is None:
        raise NotFoundError("Report not found")
    previous = report.status
    job_closed = False
    if takedown:
        job = _lock_job(db, report.job_id)
        if job.status != JobStatus.CLOSED:
            note = reason or f"Taken down after user report ({_enum_value(report.reason)})"
            _takedown_job(db, admin, job, note, {"reportId": str(report.id)})
            job_closed = True
    report.status = status
    audit(
        db, admin, f"JOB_REPORT_{status.value}", "JobReport", report.id,
        {"reason": reason, "previousStatus": previous, "jobId": report.job_id, "takedown": takedown,
         "jobClosed": job_closed},
    )
    db.commit()
    row = db.execute(_report_select().where(JobReport.id == report_id)).one()
    return serialize_report(*row)


# =========================================================================== reviews


def list_reviews(db: Session, params: PageParams, status: ReviewStatus) -> tuple[list[dict[str, Any]], int]:
    stmt = (
        select(CompanyReview, Company.name.label("company_name"), User.name.label("user_name"))
        .join(Company, Company.id == CompanyReview.company_id)
        .join(User, User.id == CompanyReview.user_id)
        .where(CompanyReview.status == status)
    )
    created = CompanyReview.created_at.asc() if status == ReviewStatus.PENDING else CompanyReview.created_at.desc()
    rows, total = paginate(db, stmt.order_by(created, CompanyReview.id), params)
    return [serialize_review(*row) for row in rows], total


def serialize_review(review: CompanyReview, company_name: str, user_name: str) -> dict[str, Any]:
    return {
        "id": review.id,
        "companyId": review.company_id,
        "companyName": company_name,
        "userId": review.user_id,
        "userName": user_name,
        "rating": review.rating,
        "title": review.title,
        "body": review.body,
        "status": review.status,
        "createdAt": review.created_at,
    }


def moderate_review(db: Session, admin: User, review_id: uuid.UUID, status: ReviewStatus) -> dict[str, Any]:
    review = db.scalar(select(CompanyReview).where(CompanyReview.id == review_id).with_for_update())
    if review is None:
        raise NotFoundError("Review not found")
    previous = review.status
    review.status = status
    audit(db, admin, f"REVIEW_{status.value}", "CompanyReview", review.id,
          {"previousStatus": previous, "companyId": review.company_id, "reason": None})
    db.commit()
    row = db.execute(
        select(CompanyReview, Company.name, User.name)
        .join(Company, Company.id == CompanyReview.company_id)
        .join(User, User.id == CompanyReview.user_id)
        .where(CompanyReview.id == review_id)
    ).one()
    return serialize_review(*row)


# =========================================================================== master data


def _master_model(type_key: str) -> type:
    model = MASTER_TYPES.get(type_key)
    if model is None:
        raise NotFoundError(f"Unknown master data type '{type_key}'")
    return model


def serialize_master(type_key: str, row: Any) -> dict[str, Any]:
    data: dict[str, Any] = {"id": row.id, "name": row.name, "createdAt": row.created_at}
    if type_key == "skills":
        data.update({"synonyms": list(row.synonyms or []), "isActive": row.is_active})
    elif type_key == "locations":
        data.update({"state": row.state, "country": row.country})
    elif type_key == "degrees":
        data["specializations"] = list(row.specializations or [])
    elif type_key == "notice-periods":
        data["days"] = row.days
    return data


def _validated(type_key: str, payload: Any) -> dict[str, Any]:
    try:
        return validate_master_payload(type_key, payload)
    except ValidationError as exc:
        details = [
            {"field": ".".join(str(p) for p in err["loc"]), "message": str(err["msg"])} for err in exc.errors()
        ]
        raise AppError(422, "VALIDATION_ERROR", "Validation failed", details) from exc


def _assert_unique(db: Session, type_key: str, model: Any, data: dict[str, Any], exclude_id: uuid.UUID | None) -> None:
    stmt = select(model.id).where(func.lower(model.name) == data["name"].lower())
    if model is Location:
        stmt = stmt.where(func.lower(func.coalesce(Location.state, "")) == (data.get("state") or "").lower())
    if exclude_id is not None:
        stmt = stmt.where(model.id != exclude_id)
    if db.scalar(stmt.limit(1)) is not None:
        label = type_key.replace("-", " ")
        raise ConflictError(f"A {label} entry named '{data['name']}' already exists")


def list_master(db: Session, type_key: str, params: PageParams, q: str | None) -> tuple[list[dict[str, Any]], int]:
    model = _master_model(type_key)
    stmt = select(model)
    if q and q.strip():
        stmt = stmt.where(model.name.ilike(_like(q), escape="\\"))
    stmt = stmt.order_by(func.lower(model.name), model.id)
    rows, total = paginate(db, stmt, params)
    return [serialize_master(type_key, r) for r in rows], total


def _get_master(db: Session, type_key: str, item_id: uuid.UUID) -> Any:
    model = _master_model(type_key)
    row = db.get(model, item_id)
    if row is None:
        raise NotFoundError("Master data item not found")
    return row


def get_master(db: Session, type_key: str, item_id: uuid.UUID) -> dict[str, Any]:
    return serialize_master(type_key, _get_master(db, type_key, item_id))


def create_master(db: Session, admin: User, type_key: str, payload: Any) -> dict[str, Any]:
    model = _master_model(type_key)
    data = _validated(type_key, payload)
    _assert_unique(db, type_key, model, data, None)
    row = model(**data)
    db.add(row)
    db.flush()
    audit(db, admin, "MASTER_CREATED", f"Master:{type_key}", row.id, {"type": type_key, "name": data["name"]})
    _commit_or_conflict(db, f"A {type_key} entry with that name already exists")
    return serialize_master(type_key, row)


def update_master(db: Session, admin: User, type_key: str, item_id: uuid.UUID, payload: Any) -> dict[str, Any]:
    row = _get_master(db, type_key, item_id)
    data = _validated(type_key, payload)
    _assert_unique(db, type_key, type(row), data, row.id)
    previous_name = row.name
    for field, value in data.items():
        setattr(row, field, value)
    audit(db, admin, "MASTER_UPDATED", f"Master:{type_key}", row.id,
          {"type": type_key, "previousName": previous_name, "name": data["name"]})
    _commit_or_conflict(db, f"A {type_key} entry with that name already exists")
    return serialize_master(type_key, row)


def delete_master(db: Session, admin: User, type_key: str, item_id: uuid.UUID) -> None:
    row = _get_master(db, type_key, item_id)
    name = row.name
    db.delete(row)
    audit(db, admin, "MASTER_DELETED", f"Master:{type_key}", item_id, {"type": type_key, "name": name})
    _commit_or_conflict(db, "Item is still referenced and cannot be deleted")


# =========================================================================== users

USER_SORTS = {"createdAt": User.created_at, "name": User.name, "email": User.email}


def user_status(user: User) -> str:
    if user.deleted_at is not None:
        return "deleted"
    return "blocked" if user.is_blocked else "active"


def serialize_user_row(user: User, company_name: str | None) -> dict[str, Any]:
    return {
        "id": user.id,
        "name": user.name,
        "email": user.email,
        "mobile": user.mobile,
        "role": user.role,
        "status": user_status(user),
        "isBlocked": user.is_blocked,
        "blockReason": user.block_reason,
        "emailVerified": user.email_verified,
        "mobileVerified": user.mobile_verified,
        "companyId": user.company_id,
        "companyName": company_name,
        "lastActiveAt": user.last_active_at,
        "createdAt": user.created_at,
        "deletedAt": user.deleted_at,
    }


def _user_select() -> Select[Any]:
    return select(User, Company.name).outerjoin(Company, Company.id == User.company_id)


def list_users(
    db: Session,
    params: PageParams,
    *,
    q: str | None,
    role: UserRole | None,
    status: str | None,
    email_verified: bool | None,
    sort: str,
    order: str,
) -> tuple[list[dict[str, Any]], int]:
    stmt = _user_select()
    if q and q.strip():
        pattern = _like(q)
        stmt = stmt.where(
            or_(
                User.name.ilike(pattern, escape="\\"),
                User.email.ilike(pattern, escape="\\"),
                User.mobile.ilike(pattern, escape="\\"),
            )
        )
    if role is not None:
        stmt = stmt.where(User.role == role)
    if status == "deleted":
        stmt = stmt.where(User.deleted_at.is_not(None))
    elif status == "blocked":
        stmt = stmt.where(User.deleted_at.is_(None), User.is_blocked.is_(True))
    elif status == "active":
        stmt = stmt.where(User.deleted_at.is_(None), User.is_blocked.is_(False))
    else:
        stmt = stmt.where(User.deleted_at.is_(None))
    if email_verified is not None:
        stmt = stmt.where(User.email_verified.is_(email_verified))
    stmt = stmt.order_by(_order(USER_SORTS[sort], order), User.id)
    rows, total = paginate(db, stmt, params)
    return [serialize_user_row(u, c) for u, c in rows], total


def user_detail(db: Session, user_id: uuid.UUID, include_deleted: bool = False) -> dict[str, Any]:
    stmt = _user_select().where(User.id == user_id)
    if not include_deleted:
        stmt = stmt.where(User.deleted_at.is_(None))
    row = db.execute(stmt).one_or_none()
    if row is None:
        raise NotFoundError("User not found")
    user, company_name = row
    data = serialize_user_row(user, company_name)
    data["applicationCount"] = int(
        db.scalar(select(func.count(Application.id)).where(Application.user_id == user_id)) or 0
    )
    data["jobsPosted"] = int(db.scalar(select(func.count(Job.id)).where(Job.posted_by == user_id)) or 0)
    return data


def _get_user(db: Session, user_id: uuid.UUID) -> User:
    user = db.scalar(select(User).where(User.id == user_id, User.deleted_at.is_(None)).with_for_update())
    if user is None:
        raise NotFoundError("User not found")
    return user


def _assert_manageable(admin: User, target: User, verb: str, participle: str) -> None:
    if target.id == admin.id:
        raise BadRequestError(f"You cannot {verb} your own account")
    if target.role == UserRole.ADMIN:
        raise ForbiddenError(f"Administrator accounts cannot be {participle} by other administrators")


def _revoke_refresh_tokens(db: Session, user_id: uuid.UUID) -> int:
    result = db.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=utcnow())
    )
    return int(result.rowcount or 0)


def block_user(db: Session, admin: User, user_id: uuid.UUID, reason: str) -> dict[str, Any]:
    user = _get_user(db, user_id)
    _assert_manageable(admin, user, "block", "blocked")
    user.is_blocked = True
    user.block_reason = reason
    revoked = _revoke_refresh_tokens(db, user.id)
    audit(db, admin, "USER_BLOCKED", "User", user.id,
          {"reason": reason, "email": user.email, "sessionsRevoked": revoked})
    db.commit()
    return user_detail(db, user_id)


def unblock_user(db: Session, admin: User, user_id: uuid.UUID) -> dict[str, Any]:
    user = _get_user(db, user_id)
    was_blocked = user.is_blocked
    user.is_blocked = False
    user.block_reason = None
    audit(db, admin, "USER_UNBLOCKED", "User", user.id, {"email": user.email, "wasBlocked": was_blocked})
    db.commit()
    return user_detail(db, user_id)


def reset_verification(db: Session, admin: User, user_id: uuid.UUID) -> dict[str, Any]:
    user = _get_user(db, user_id)
    now = utcnow()
    user.email_verified = False
    user.mobile_verified = False
    # invalidate older outstanding links, then issue a fresh one
    db.execute(
        update(EmailToken).where(EmailToken.user_id == user.id, EmailToken.used_at.is_(None)).values(used_at=now)
    )
    raw = new_refresh_token()
    db.add(
        EmailToken(
            user_id=user.id,
            token_hash=hash_token(raw),
            expires_at=now + timedelta(hours=settings.email_token_hours),
        )
    )
    audit(db, admin, "USER_VERIFICATION_RESET", "User", user.id, {"email": user.email})
    db.commit()
    link = f"{settings.site_url.rstrip('/')}/verify-email?token={raw}"
    try:
        get_email_sender().send(
            user.email,
            "Verify your email address",
            f"Hi {user.name},\n\nAn administrator reset your verification status. Please verify your email "
            f"by opening this link:\n{link}\n\nVerification token: {raw}\n"
            f"The link expires in {settings.email_token_hours} hours.",
        )
    except SenderError:
        logger.warning("Verification email delivery failed for user %s", user.id, exc_info=True)
    return user_detail(db, user_id)


def delete_user(db: Session, admin: User, user_id: uuid.UUID) -> None:
    user = _get_user(db, user_id)
    _assert_manageable(admin, user, "delete", "deleted")
    user.deleted_at = utcnow()
    revoked = _revoke_refresh_tokens(db, user.id)
    audit(db, admin, "USER_DELETED", "User", user.id,
          {"email": user.email, "role": user.role, "sessionsRevoked": revoked})
    db.commit()


# =========================================================================== audit log


def list_audit_logs(
    db: Session,
    params: PageParams,
    *,
    action: str | None,
    actor_id: uuid.UUID | None,
    entity_type: str | None,
    date_from: date | None,
    date_to: date | None,
) -> tuple[list[dict[str, Any]], int]:
    if date_from is not None and date_to is not None and date_from > date_to:
        raise AppError(
            422, "VALIDATION_ERROR", "Invalid date range",
            [{"field": "from", "message": "'from' must not be after 'to'"}],
        )
    stmt = select(AuditLog, User.name, User.email).outerjoin(User, User.id == AuditLog.actor_id)
    if action:
        stmt = stmt.where(AuditLog.action == action.strip().upper())
    if actor_id is not None:
        stmt = stmt.where(AuditLog.actor_id == actor_id)
    if entity_type:
        stmt = stmt.where(func.lower(AuditLog.entity_type) == entity_type.strip().lower())
    if date_from is not None:
        stmt = stmt.where(AuditLog.created_at >= _start_of_day(date_from))
    if date_to is not None:
        stmt = stmt.where(AuditLog.created_at < _end_of_day(date_to))
    rows, total = paginate(db, stmt.order_by(AuditLog.created_at.desc(), AuditLog.id), params)
    items = [
        {
            "id": log.id,
            "actorId": log.actor_id,
            "actorName": actor_name,
            "actorEmail": actor_email,
            "action": log.action,
            "entityType": log.entity_type,
            "entityId": log.entity_id,
            "details": log.details or {},
            "createdAt": log.created_at,
        }
        for log, actor_name, actor_email in rows
    ]
    return items, total
