"""Recruiter dashboard aggregates (a handful of grouped queries, no per-job lookups)."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.applications import Application, Interview
from app.models.enums import ApplicationStatus, JobStatus
from app.models.jobs import Job

S = ApplicationStatus
TOP_JOBS = 10

# funnel key -> application status
FUNNEL_STAGES: dict[str, ApplicationStatus] = {
    "applied": S.APPLIED,
    "viewed": S.VIEWED,
    "shortlisted": S.SHORTLISTED,
    "interviewScheduled": S.INTERVIEW_SCHEDULED,
    "offered": S.OFFERED,
    "hired": S.HIRED,
    "rejected": S.REJECTED,
}


def build_dashboard(db: Session, company_id: uuid.UUID, now: datetime | None = None) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_end = start_of_day + timedelta(days=7)

    job_counts = dict(
        db.execute(
            select(Job.status, func.count())
            .where(
                Job.company_id == company_id,
                Job.deleted_at.is_(None),
                Job.status.in_([JobStatus.ACTIVE, JobStatus.PENDING_REVIEW]),
            )
            .group_by(Job.status)
        ).all()
    )

    total_applicants, new_today = db.execute(
        select(
            func.count(Application.id).filter(Application.status != S.WITHDRAWN),
            func.count(Application.id).filter(
                Application.status != S.WITHDRAWN, Application.applied_at >= start_of_day
            ),
        )
        .join(Job, Job.id == Application.job_id)
        .where(Job.company_id == company_id, Job.deleted_at.is_(None))
    ).one()

    interviews = db.scalar(
        select(func.count(func.distinct(Interview.application_id)))
        .join(Application, Application.id == Interview.application_id)
        .join(Job, Job.id == Application.job_id)
        .where(
            Job.company_id == company_id,
            Job.deleted_at.is_(None),
            Application.status == S.INTERVIEW_SCHEDULED,
            Interview.scheduled_at >= start_of_day,
            Interview.scheduled_at < week_end,
        )
    )

    activity = func.greatest(func.max(Application.applied_at), Job.posted_at, Job.created_at)
    stage_columns = [func.count(Application.id).filter(Application.status == s) for s in FUNNEL_STAGES.values()]
    rows = db.execute(
        select(Job.id, Job.title, Job.view_count, Job.application_count, *stage_columns)
        .select_from(Job)
        .outerjoin(Application, Application.job_id == Job.id)
        .where(Job.company_id == company_id, Job.deleted_at.is_(None))
        .group_by(Job.id)
        .order_by(activity.desc(), Job.id)
        .limit(TOP_JOBS)
    ).all()

    funnel: list[dict[str, Any]] = []
    views: list[dict[str, Any]] = []
    for job_id, title, view_count, application_count, *stages in rows:
        entry: dict[str, Any] = {"jobId": job_id, "title": title}
        entry.update({key: int(count) for key, count in zip(FUNNEL_STAGES, stages, strict=True)})
        funnel.append(entry)
        views.append(
            {"jobId": job_id, "title": title, "views": int(view_count or 0), "applications": int(application_count or 0)}
        )

    return {
        "activeJobs": int(job_counts.get(JobStatus.ACTIVE, 0)),
        "pendingReview": int(job_counts.get(JobStatus.PENDING_REVIEW, 0)),
        "totalApplicants": int(total_applicants or 0),
        "newApplicantsToday": int(new_today or 0),
        "interviewsThisWeek": int(interviews or 0),
        "funnel": funnel,
        "viewsVsApplications": views,
    }
