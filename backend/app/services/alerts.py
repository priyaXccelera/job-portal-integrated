"""Job-alert matching/dispatch and new-job notifications to company followers."""

from __future__ import annotations

import logging
import re
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from typing import Any

from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session

from app.config import settings
from app.core.errors import ConflictError, NotFoundError
from app.models.accounts import User
from app.models.company import Company, CompanyFollow
from app.models.enums import AlertFrequency, CompanyStatus, JobStatus, WorkMode
from app.models.jobs import Job, JobAlert
from app.services.notifications import Category, notify

logger = logging.getLogger(__name__)

MAX_ALERTS_PER_USER = 10
MAX_CANDIDATE_JOBS = 2000
TOP_JOBS_IN_BODY = 5
_TOKEN_SPLIT = re.compile(r"[,\s]+")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def _tokens(keywords: str | None) -> list[str]:
    return [t.casefold() for t in _TOKEN_SPLIT.split(keywords or "") if t]


def _haystack(job: Job, company_name: str) -> str:
    parts = [job.title or "", company_name or "", job.description or ""]
    parts.extend(job.required_skills or [])
    parts.extend(job.preferred_skills or [])
    return " ".join(parts).casefold()


def _job_matches(alert: JobAlert, job: Job, haystack: str) -> bool:
    tokens = _tokens(alert.keywords)
    if tokens and not any(tok in haystack for tok in tokens):
        return False

    alert_locations = {loc.strip().casefold() for loc in (alert.locations or []) if loc.strip()}
    if alert_locations:
        job_locations = {loc.strip().casefold() for loc in (job.locations or [])}
        is_remote = job.work_mode is not None and WorkMode(job.work_mode) == WorkMode.REMOTE
        if not (alert_locations & job_locations) and not is_remote:
            return False

    if alert.experience is not None:
        exp = Decimal(alert.experience)
        if job.experience_min is not None and exp < job.experience_min:
            return False
        if job.experience_max is not None and exp > job.experience_max:
            return False

    if alert.salary_min is not None and job.salary_max is not None and job.salary_max < alert.salary_min:
        return False
    return True


def _active_alerts(db: Session, frequency: AlertFrequency) -> list[JobAlert]:
    stmt = (
        select(JobAlert)
        .join(User, User.id == JobAlert.user_id)
        .where(
            JobAlert.frequency == AlertFrequency(frequency),
            JobAlert.is_paused.is_(False),
            User.deleted_at.is_(None),
            User.is_blocked.is_(False),
        )
        .order_by(JobAlert.created_at)
    )
    return list(db.scalars(stmt).all())


def _match(db: Session, thresholds: dict[uuid.UUID, tuple[JobAlert, datetime]]) -> list[tuple[JobAlert, list[Job]]]:
    """Match alerts against recent jobs using one jobs query for all of them."""
    if not thresholds:
        return []
    now = _now()
    oldest = min(threshold for _, threshold in thresholds.values())
    rows = db.execute(
        select(Job, Company.name)
        .join(Company, Company.id == Job.company_id)
        .where(
            Job.status == JobStatus.ACTIVE,
            Job.deleted_at.is_(None),
            Company.deleted_at.is_(None),
            Company.status == CompanyStatus.APPROVED,
            Job.posted_at.is_not(None),
            Job.posted_at > oldest,
            or_(Job.expires_at.is_(None), Job.expires_at > now),
            or_(Job.deadline.is_(None), Job.deadline >= now.date()),
        )
        .order_by(Job.posted_at.desc())
        .limit(MAX_CANDIDATE_JOBS)
    ).all()
    candidates = [(job, _haystack(job, company_name)) for job, company_name in rows]

    result: list[tuple[JobAlert, list[Job]]] = []
    for alert, threshold in thresholds.values():
        matched = [
            job
            for job, haystack in candidates
            if _aware(job.posted_at) > threshold and _job_matches(alert, job, haystack)
        ]
        if matched:
            result.append((alert, matched))
    return result


def match_alerts(db: Session, since: datetime, frequency: AlertFrequency) -> list[tuple[JobAlert, list[Job]]]:
    """Non-paused alerts of ``frequency`` with jobs posted after max(since, alert.last_sent_at)."""
    since = _aware(since)
    thresholds = {
        a.id: (a, max(since, _aware(a.last_sent_at)) if a.last_sent_at else since)
        for a in _active_alerts(db, frequency)
    }
    return _match(db, thresholds)


def _alert_message(alert: JobAlert, jobs: list[Job]) -> tuple[str, str]:
    count = len(jobs)
    title = f"Job alert '{alert.name}': {count} new job{'s' if count != 1 else ''}"
    lines = [f"- {job.title}" + (f" ({', '.join(job.locations[:2])})" if job.locations else "") for job in jobs[:TOP_JOBS_IN_BODY]]
    if count > TOP_JOBS_IN_BODY:
        lines.append(f"...and {count - TOP_JOBS_IN_BODY} more")
    body = f"New jobs matching your alert '{alert.name}':\n" + "\n".join(lines)
    return title, body


def dispatch_alerts(db: Session, frequency: AlertFrequency, now: datetime | None = None) -> int:
    """Send one notification per alert having matches; updates last_sent_at and commits."""
    frequency = AlertFrequency(frequency)
    now = _aware(now) if now else _now()
    alerts = _active_alerts(db, frequency)

    thresholds: dict[uuid.UUID, tuple[JobAlert, datetime]] = {}
    for alert in alerts:
        if frequency == AlertFrequency.instant:
            threshold = (
                _aware(alert.last_sent_at)
                if alert.last_sent_at
                else now - timedelta(minutes=settings.scheduler_alert_instant_minutes)
            )
        else:
            window = timedelta(days=1 if frequency == AlertFrequency.daily else 7)
            threshold = now - window
            if alert.last_sent_at:
                threshold = max(threshold, _aware(alert.last_sent_at))
        thresholds[alert.id] = (alert, threshold)

    sent = 0
    for alert, jobs in _match(db, thresholds):
        title, body = _alert_message(alert, jobs)
        notification = notify(
            db,
            alert.user_id,
            Category.JOB_ALERT,
            title,
            body,
            data={"alertId": str(alert.id), "jobIds": [str(j.id) for j in jobs]},
        )
        alert.last_sent_at = now
        if notification is not None:
            sent += 1
    db.commit()
    logger.info("Dispatched %d %s job alert notification(s)", sent, frequency.value)
    return sent


def notify_followers_of_job(db: Session, job: Job) -> int:
    """Notify every follower of the job's company about a new job. Does not commit."""
    follower_ids = list(
        db.scalars(
            select(CompanyFollow.user_id)
            .join(User, User.id == CompanyFollow.user_id)
            .where(
                CompanyFollow.company_id == job.company_id,
                User.deleted_at.is_(None),
                User.is_blocked.is_(False),
            )
        ).all()
    )
    if not follower_ids:
        return 0
    company = db.get(Company, job.company_id)
    company_name = company.name if company is not None else "A company you follow"
    title = f"{company_name} posted a new job: {job.title}"
    body = f"{company_name} is hiring for {job.title}."
    count = 0
    for user_id in follower_ids:
        created = notify(
            db,
            user_id,
            Category.NEW_JOB_FROM_COMPANY,
            title,
            body,
            email=False,
            data={"jobId": str(job.id), "companyId": str(job.company_id)},
        )
        if created is not None:
            count += 1
    return count


# --------------------------------------------------------------------------- alert CRUD

_UPDATABLE = {"name", "keywords", "locations", "experience", "salary_min", "frequency", "is_paused"}


def alerts_stmt(user_id: uuid.UUID) -> Select[Any]:
    return select(JobAlert).where(JobAlert.user_id == user_id).order_by(JobAlert.created_at.desc(), JobAlert.id)


def get_alert(db: Session, user_id: uuid.UUID, alert_id: uuid.UUID) -> JobAlert:
    alert = db.scalar(select(JobAlert).where(JobAlert.id == alert_id, JobAlert.user_id == user_id))
    if alert is None:
        raise NotFoundError("Job alert not found")
    return alert


def _default_name(keywords: str | None, locations: list[str]) -> str:
    parts = [p for p in (keywords, ", ".join(locations[:2]) if locations else None) if p]
    return (" in ".join(parts) if parts else "Job alert")[:150]


def create_alert(db: Session, user_id: uuid.UUID, fields: dict[str, Any]) -> JobAlert:
    """Create an alert (max MAX_ALERTS_PER_USER per user). Does not commit."""
    existing = db.scalar(select(func.count()).select_from(JobAlert).where(JobAlert.user_id == user_id)) or 0
    if existing >= MAX_ALERTS_PER_USER:
        raise ConflictError(f"You can have at most {MAX_ALERTS_PER_USER} job alerts", code="CONFLICT")
    keywords = fields.get("keywords")
    locations = list(fields.get("locations") or [])
    alert = JobAlert(
        id=uuid.uuid4(),
        user_id=user_id,
        name=fields.get("name") or _default_name(keywords, locations),
        keywords=keywords,
        locations=locations,
        experience=fields.get("experience"),
        salary_min=fields.get("salary_min"),
        frequency=AlertFrequency(fields.get("frequency") or AlertFrequency.daily),
        is_paused=False,
    )
    db.add(alert)
    db.flush()
    return alert


def update_alert(db: Session, alert: JobAlert, fields: dict[str, Any]) -> JobAlert:
    """Apply the given (already validated) fields to ``alert``. Does not commit."""
    for key, value in fields.items():
        if key not in _UPDATABLE:
            continue
        if key == "name":
            if value is None:
                continue  # a name cannot be cleared; keep the current one
        elif key == "locations":
            value = list(value or [])
        elif key == "frequency":
            if value is None:
                continue
            value = AlertFrequency(value)
        elif key == "is_paused":
            if value is None:
                continue
            value = bool(value)
        setattr(alert, key, value)
    alert.updated_at = _now()
    db.flush()
    return alert


def serialize_alert(alert: JobAlert) -> dict[str, Any]:
    return {
        "id": alert.id,
        "name": alert.name,
        "keywords": alert.keywords,
        "locations": list(alert.locations or []),
        "experience": alert.experience,
        "salaryMin": alert.salary_min,
        "frequency": alert.frequency,
        "isPaused": alert.is_paused,
        "lastSentAt": alert.last_sent_at,
        "createdAt": alert.created_at,
        "updatedAt": alert.updated_at,
    }
