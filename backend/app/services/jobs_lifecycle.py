"""Job lifecycle: publish / pause / close / refresh / duplicate and the scheduled expiry jobs.

Quota rule: a job consumes one unit of ``Company.jobs_posted`` the first time it is published
(``posted_at`` is stamped for both ACTIVE and PENDING_REVIEW outcomes, so ``posted_at IS NOT NULL``
means "already counted"). Re-publishing, resuming or refreshing never consume quota again.
Methods never commit except the module-level scheduler helpers (``expire_jobs`` and
``notify_expiring_soon``).
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.config import settings
from app.core.errors import AppError, ConflictError, ForbiddenError
from app.models.accounts import Notification, User
from app.models.company import Company
from app.models.enums import CompanyStatus, JobStatus, QuestionType
from app.models.jobs import Job, ScreeningQuestion
from app.services.alerts import notify_followers_of_job
from app.services.job_index import reindex_job
from app.services.notifications import Category, notify

logger = logging.getLogger(__name__)

J = JobStatus

# target -> statuses it can be reached from (ACTIVE handled separately, it is a publish)
_PUBLISH_FROM = {J.DRAFT, J.REJECTED, J.EXPIRED, J.PAUSED, J.CLOSED}
_TRANSITIONS: dict[JobStatus, set[JobStatus]] = {
    J.PAUSED: {J.ACTIVE},
    J.CLOSED: {J.ACTIVE, J.PAUSED, J.PENDING_REVIEW, J.DRAFT},
    J.DRAFT: {J.PENDING_REVIEW},
}
_REFRESHABLE = {J.ACTIVE, J.PAUSED, J.EXPIRED, J.CLOSED}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _invalid(current: JobStatus, target: JobStatus, hint: str | None = None) -> ConflictError:
    message = f"Cannot move job from {current.value} to {target.value}"
    if hint:
        message += f". {hint}"
    return ConflictError(message, code="INVALID_TRANSITION")


class JobLifecycleService:
    def __init__(self, db: Session) -> None:
        self.db = db

    # ----------------------------------------------------------------- helpers

    def _locked_company(self, company_id: uuid.UUID) -> Company:
        company = self.db.scalar(
            select(Company).where(Company.id == company_id).with_for_update().execution_options(populate_existing=True)
        )
        if company is None or company.deleted_at is not None:
            raise ForbiddenError("Company is not available", code="COMPANY_NOT_APPROVED")
        if CompanyStatus(company.status) in (CompanyStatus.BLOCKED, CompanyStatus.REJECTED):
            raise ForbiddenError(
                f"Company is {CompanyStatus(company.status).value.lower()} and cannot publish jobs",
                code="COMPANY_NOT_APPROVED",
            )
        return company

    @staticmethod
    def _assert_deadline_open(job: Job) -> None:
        if job.deadline is not None and job.deadline < _now().date():
            raise AppError(
                422,
                "VALIDATION_ERROR",
                "The job deadline is in the past; edit the job before publishing",
                [{"field": "deadline", "message": "deadline must not be in the past"}],
            )

    def _outcome_status(self, company: Company) -> JobStatus:
        return J.ACTIVE if CompanyStatus(company.status) == CompanyStatus.APPROVED else J.PENDING_REVIEW

    # ----------------------------------------------------------------- publish

    def publish(self, job: Job, *, resume: bool = False) -> Job:
        """Publish a job: ACTIVE for approved companies, PENDING_REVIEW otherwise.

        ``resume`` (PAUSED -> ACTIVE) keeps the original posting date and never touches quota.
        """
        company = self._locked_company(job.company_id)
        self._assert_deadline_open(job)
        now = _now()
        first_publish = job.posted_at is None
        if first_publish:
            if company.jobs_posted >= company.job_quota:
                raise AppError(
                    403,
                    "QUOTA_EXCEEDED",
                    f"Job posting quota of {company.job_quota} reached",
                )
            company.jobs_posted += 1

        if not resume or first_publish:
            job.posted_at = now
            job.expires_at = now + timedelta(days=settings.job_expiry_days)
        elif job.expires_at is None or job.expires_at <= now:
            job.expires_at = now + timedelta(days=settings.job_expiry_days)

        job.status = self._outcome_status(company)
        job.reject_reason = None
        job.updated_at = now
        reindex_job(self.db, job.id)
        if first_publish and job.status == J.ACTIVE:
            notified = notify_followers_of_job(self.db, job)
            logger.info("Job %s published; notified %d followers", job.id, notified)
        return job

    # ----------------------------------------------------------------- status machine

    def change_status(self, job: Job, target: JobStatus, reason: str | None = None) -> Job:
        current = JobStatus(job.status)
        target = JobStatus(target)
        if target == J.ACTIVE:
            if current == J.REJECTED:
                raise _invalid(current, target, "Edit the rejected job to address the feedback, then publish it again")
            if current not in _PUBLISH_FROM:
                raise _invalid(current, target)
            self.publish(job, resume=current == J.PAUSED)
        else:
            if current not in _TRANSITIONS.get(target, set()):
                raise _invalid(current, target)
            job.status = target
            job.updated_at = _now()
        logger.info("Job %s: %s -> %s (reason=%s)", job.id, current.value, job.status.value, reason)
        return job

    # ----------------------------------------------------------------- refresh / duplicate

    def refresh(self, job: Job) -> Job:
        """Repost: reset posted_at / expires_at; EXPIRED and CLOSED jobs become publishable again."""
        current = JobStatus(job.status)
        if current not in _REFRESHABLE or job.posted_at is None:
            raise ConflictError(
                f"Only previously published ACTIVE, PAUSED, EXPIRED or CLOSED jobs can be refreshed (job is {current.value})",
                code="INVALID_TRANSITION",
            )
        if current in (J.EXPIRED, J.CLOSED):
            return self.publish(job)
        self._locked_company(job.company_id)  # blocked / rejected companies cannot repost
        now = _now()
        job.posted_at = now
        job.expires_at = now + timedelta(days=settings.job_expiry_days)
        job.updated_at = now
        reindex_job(self.db, job.id)
        return job

    def duplicate(self, job: Job, actor_id: uuid.UUID) -> Job:
        """DRAFT copy including screening questions; counters and dates reset."""
        today = _now().date()
        copy = Job(
            id=uuid.uuid4(),
            company_id=job.company_id,
            posted_by=actor_id,
            title=job.title,
            description=job.description,
            responsibilities=job.responsibilities,
            required_skills=list(job.required_skills or []),
            preferred_skills=list(job.preferred_skills or []),
            experience_min=job.experience_min,
            experience_max=job.experience_max,
            salary_min=job.salary_min,
            salary_max=job.salary_max,
            hide_salary=job.hide_salary,
            job_type=job.job_type,
            employment_type=job.employment_type,
            work_mode=job.work_mode,
            locations=list(job.locations or []),
            openings=job.openings,
            industry=job.industry,
            department=job.department,
            role_category=job.role_category,
            education=job.education,
            notice_preference=job.notice_preference,
            is_walk_in=job.is_walk_in,
            walk_in_details=dict(job.walk_in_details) if job.walk_in_details else None,
            deadline=job.deadline if job.deadline and job.deadline >= today else None,
            status=J.DRAFT,
            view_count=0,
            application_count=0,
            posted_at=None,
            expires_at=None,
        )
        self.db.add(copy)
        self.db.flush()
        originals = self.db.scalars(
            select(ScreeningQuestion).where(ScreeningQuestion.job_id == job.id).order_by(ScreeningQuestion.position)
        )
        for question in originals:
            self.db.add(
                ScreeningQuestion(
                    id=uuid.uuid4(),
                    job_id=copy.id,
                    text=question.text,
                    question_type=QuestionType(question.question_type),
                    options=list(question.options or []),
                    is_knockout=question.is_knockout,
                    expected_answer=question.expected_answer,
                    is_required=question.is_required,
                    position=question.position,
                )
            )
        reindex_job(self.db, copy.id)
        return copy


# --------------------------------------------------------------------------- scheduled helpers


def expire_jobs(db: Session, now: datetime | None = None) -> int:
    """ACTIVE, non-deleted jobs past ``expires_at`` (or whose deadline day has passed) -> EXPIRED."""
    now = now or _now()
    stmt = (
        update(Job)
        .where(
            Job.status == J.ACTIVE,
            Job.deleted_at.is_(None),
            (Job.expires_at < now) | (Job.deadline < now.astimezone(timezone.utc).date()),
        )
        .values(status=J.EXPIRED, updated_at=now)
        .execution_options(synchronize_session=False)
        .returning(Job.id)
    )
    expired = list(db.scalars(stmt).all())
    db.commit()
    if expired:
        logger.info("Expired %d jobs", len(expired))
    return len(expired)


def notify_expiring_soon(db: Session, now: datetime | None = None, days: int | None = None) -> int:
    """Notify the posting recruiter once per posting cycle about ACTIVE jobs expiring within ``days``."""
    now = now or _now()
    horizon = now + timedelta(days=days if days is not None else settings.expiring_soon_days)
    jobs = list(
        db.scalars(
            select(Job).where(
                Job.status == J.ACTIVE,
                Job.deleted_at.is_(None),
                Job.posted_by.is_not(None),
                Job.expires_at.is_not(None),
                Job.expires_at >= now,
                Job.expires_at <= horizon,
            )
        )
    )
    if not jobs:
        return 0

    job_ids = [str(j.id) for j in jobs]
    job_key = Notification.data["jobId"].as_string()
    already: dict[str, datetime] = {
        key: last
        for key, last in db.execute(
            select(job_key, func.max(Notification.created_at))
            .where(Notification.category == Category.JOB_EXPIRING.value, job_key.in_(job_ids))
            .group_by(job_key)
        ).all()
    }
    active_users = set(
        db.scalars(
            select(User.id).where(
                User.id.in_({j.posted_by for j in jobs}), User.deleted_at.is_(None), User.is_blocked.is_(False)
            )
        )
    )
    sent = 0
    for job in jobs:
        last = already.get(str(job.id))
        if job.posted_by not in active_users or (last is not None and (job.posted_at is None or last >= job.posted_at)):
            continue
        remaining = max(1, (job.expires_at - now).days)
        created = notify(
            db,
            job.posted_by,
            Category.JOB_EXPIRING,
            f"Job expiring soon: {job.title}",
            f'Your job "{job.title}" expires on {job.expires_at.date().isoformat()} '
            f"(in about {remaining} day{'s' if remaining != 1 else ''}). Refresh it to keep it visible.",
            data={"jobId": str(job.id), "expiresAt": job.expires_at.isoformat()},
        )
        if created is not None:
            sent += 1
    db.commit()
    return sent
