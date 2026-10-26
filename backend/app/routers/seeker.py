"""Job-seeker actions: saved jobs, applications, alerts, follows, reviews, reports and searches."""

from __future__ import annotations

import logging
import uuid
from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import require_roles
from app.core.errors import AppError, ConflictError, NotFoundError
from app.core.responses import PageParams, ok, page_params, paged, paginate
from app.db import get_db, utcnow
from app.models.accounts import User
from app.models.applications import Application, Interview
from app.models.enums import ApplicationStatus, InterviewResponse, UserRole
from app.models.jobs import Job
from app.schemas.seeker import (
    ApplyRequest,
    InterviewResponseRequest,
    JobAlertIn,
    JobAlertPatch,
    JobReportIn,
    ReviewIn,
    SavedSearchIn,
    WithdrawRequest,
)
from app.services import alerts as alert_service
from app.services import applications as application_service
from app.services import search as search_service
from app.services import seeker_actions as actions
from app.services.notifications import Category, notify

logger = logging.getLogger(__name__)

router = APIRouter(tags=["seeker"])

seeker_only = require_roles(UserRole.JOB_SEEKER)


# --------------------------------------------------------------------------- saved jobs & recommendations
# Static paths first: they must be registered before any parametrised /jobs/{id} route.


@router.get("/jobs/saved", summary="List saved jobs")
def list_saved_jobs(
    sort: Literal["savedAt", "postedAt"] = Query("savedAt"),
    order: Literal["asc", "desc"] = Query("desc"),
    params: PageParams = Depends(page_params),
    user: User = Depends(seeker_only),
    db: Session = Depends(get_db),
):
    rows, total = paginate(db, actions.saved_jobs_stmt(user.id, sort, order), params)
    jobs = [job for job, _ in rows]
    items = search_service.serialize_jobs(db, jobs, user)
    saved_at = {job.id: ts for job, ts in rows}
    for job, item in zip(jobs, items, strict=False):
        item["savedAt"] = saved_at[job.id]
    return paged(items, params.page, params.page_size, total)


@router.get("/jobs/recommended", summary="Jobs recommended from the seeker profile")
def recommended_jobs(
    params: PageParams = Depends(page_params),
    user: User = Depends(seeker_only),
    db: Session = Depends(get_db),
):
    items, total = search_service.recommended(db, user, params.page, params.page_size)
    return paged(items, params.page, params.page_size, total)


@router.get("/jobs/based-on-searches", summary="Jobs based on recent searches")
def jobs_based_on_searches(
    params: PageParams = Depends(page_params),
    user: User = Depends(seeker_only),
    db: Session = Depends(get_db),
):
    items, total = search_service.based_on_recent_searches(db, user, params.page, params.page_size)
    return paged(items, params.page, params.page_size, total)


@router.post("/jobs/{job_id}/save", summary="Save a job (idempotent)")
def save_job(job_id: uuid.UUID, user: User = Depends(seeker_only), db: Session = Depends(get_db)):
    created = actions.save_job(db, user.id, job_id)
    db.commit()
    return ok({"jobId": job_id, "saved": True}, status_code=201 if created else 200)


@router.delete("/jobs/{job_id}/save", summary="Remove a saved job")
def unsave_job(job_id: uuid.UUID, user: User = Depends(seeker_only), db: Session = Depends(get_db)):
    removed = actions.unsave_job(db, user.id, job_id)
    db.commit()
    return ok({"jobId": job_id, "saved": False, "removed": removed})


@router.post("/jobs/{job_id}/report", summary="Report a job as fake/spam/misleading")
def report_job(
    job_id: uuid.UUID,
    body: JobReportIn,
    user: User = Depends(seeker_only),
    db: Session = Depends(get_db),
):
    report = actions.report_job(db, user.id, job_id, body.reason, body.details)
    db.commit()
    return ok(actions.serialize_report(report), status_code=201)


# --------------------------------------------------------------------------- applications


@router.post("/jobs/{job_id}/apply", summary="Apply to a job")
def apply_to_job(
    job_id: uuid.UUID,
    body: ApplyRequest,
    user: User = Depends(seeker_only),
    db: Session = Depends(get_db),
):
    job = actions.get_existing_job(db, job_id)
    application = application_service.apply_to_job(
        db,
        user,
        job,
        resume_id=body.resume_id,
        cover_note=body.cover_note,
        answers=[{"questionId": a.question_id, "answer": a.answer} for a in body.answers],
        expected_ctc=body.expected_ctc,
        notice_period=body.notice_period,
    )
    db.commit()
    db.refresh(application)
    return ok(application_service.serialize_application(db, application, "seeker"), status_code=201)


def _parse_statuses(raw: str | None) -> list[ApplicationStatus]:
    if not raw:
        return []
    statuses: list[ApplicationStatus] = []
    for part in raw.split(","):
        part = part.strip().upper()
        if not part:
            continue
        try:
            statuses.append(ApplicationStatus(part))
        except ValueError:
            raise AppError(
                422,
                "VALIDATION_ERROR",
                "Validation failed",
                [{"field": "status", "message": f"Unknown application status: {part}"}],
            ) from None
    return statuses


@router.get("/applications/me", summary="My applications")
def my_applications(
    status: str | None = Query(None, description="Comma-separated application statuses"),
    sort: Literal["appliedAt", "updatedAt"] = Query("appliedAt"),
    order: Literal["asc", "desc"] = Query("desc"),
    params: PageParams = Depends(page_params),
    user: User = Depends(seeker_only),
    db: Session = Depends(get_db),
):
    stmt = select(Application).where(Application.user_id == user.id)
    statuses = _parse_statuses(status)
    if statuses:
        stmt = stmt.where(Application.status.in_(statuses))
    column = Application.updated_at if sort == "updatedAt" else Application.applied_at
    stmt = stmt.order_by(column.asc() if order == "asc" else column.desc(), Application.id)
    rows, total = paginate(db, stmt, params)
    items = application_service.serialize_applications(db, rows, view="seeker")
    return paged(items, params.page, params.page_size, total)


def _own_application(db: Session, user: User, application_id: uuid.UUID) -> Application:
    application = db.scalar(
        select(Application).where(Application.id == application_id, Application.user_id == user.id)
    )
    if application is None:
        raise NotFoundError("Application not found")
    return application


@router.get("/applications/{application_id}", summary="Application detail with timeline")
def application_detail(
    application_id: uuid.UUID, user: User = Depends(seeker_only), db: Session = Depends(get_db)
):
    application = _own_application(db, user, application_id)
    return ok(application_service.serialize_application(db, application, "seeker"))


@router.post("/applications/{application_id}/withdraw", summary="Withdraw an application")
def withdraw_application(
    application_id: uuid.UUID,
    body: WithdrawRequest | None = None,
    user: User = Depends(seeker_only),
    db: Session = Depends(get_db),
):
    application = _own_application(db, user, application_id)
    reason = body.reason if body is not None else None
    application_service.change_status(
        db, application, ApplicationStatus.WITHDRAWN, actor=user, message=reason or "Withdrawn by candidate"
    )
    db.commit()
    db.refresh(application)
    return ok(application_service.serialize_application(db, application, "seeker"))


@router.post("/applications/{application_id}/interview-response", summary="Confirm or ask to reschedule")
def interview_response(
    application_id: uuid.UUID,
    body: InterviewResponseRequest,
    user: User = Depends(seeker_only),
    db: Session = Depends(get_db),
):
    application = _own_application(db, user, application_id)
    interview = db.scalar(
        select(Interview)
        .where(Interview.application_id == application.id)
        .order_by(Interview.created_at.desc())
        .limit(1)
    )
    if interview is None:
        raise ConflictError("No interview has been scheduled for this application")
    if ApplicationStatus(application.status) in (
        ApplicationStatus.REJECTED,
        ApplicationStatus.WITHDRAWN,
        ApplicationStatus.HIRED,
    ):
        raise ConflictError("This application is closed; the interview can no longer be answered")

    interview.candidate_response = InterviewResponse(body.response)
    interview.response_note = body.note
    job = db.get(Job, application.job_id)
    recruiter_id = interview.created_by or (job.posted_by if job is not None else None)
    if recruiter_id is not None:
        job_title = job.title if job is not None else "the job"
        verb = "confirmed" if body.response == InterviewResponse.CONFIRM else "requested to reschedule"
        text = f"{user.name} has {verb} the interview for {job_title}."
        if body.note:
            text += f"\n\nNote: {body.note}"
        notify(
            db,
            recruiter_id,
            Category.INTERVIEW_RESPONSE,
            f"Interview {verb}: {job_title}",
            text,
            data={
                "applicationId": str(application.id),
                "interviewId": str(interview.id),
                "response": InterviewResponse(body.response).value,
            },
        )
    application.updated_at = utcnow()
    db.commit()
    db.refresh(application)
    return ok(application_service.serialize_application(db, application, "seeker"))


# --------------------------------------------------------------------------- job alerts


@router.get("/job-alerts", summary="List my job alerts")
def list_job_alerts(
    params: PageParams = Depends(page_params),
    user: User = Depends(seeker_only),
    db: Session = Depends(get_db),
):
    rows, total = paginate(db, alert_service.alerts_stmt(user.id), params)
    return paged([alert_service.serialize_alert(a) for a in rows], params.page, params.page_size, total)


@router.post("/job-alerts", summary="Create a job alert")
def create_job_alert(body: JobAlertIn, user: User = Depends(seeker_only), db: Session = Depends(get_db)):
    alert = alert_service.create_alert(db, user.id, body.model_dump())
    db.commit()
    db.refresh(alert)
    return ok(alert_service.serialize_alert(alert), status_code=201)


@router.get("/job-alerts/{alert_id}", summary="Get a job alert")
def get_job_alert(alert_id: uuid.UUID, user: User = Depends(seeker_only), db: Session = Depends(get_db)):
    return ok(alert_service.serialize_alert(alert_service.get_alert(db, user.id, alert_id)))


@router.put("/job-alerts/{alert_id}", summary="Replace a job alert")
def replace_job_alert(
    alert_id: uuid.UUID,
    body: JobAlertIn,
    user: User = Depends(seeker_only),
    db: Session = Depends(get_db),
):
    alert = alert_service.get_alert(db, user.id, alert_id)
    fields = body.model_dump()
    fields["name"] = fields["name"] or alert.name
    alert_service.update_alert(db, alert, fields)
    db.commit()
    db.refresh(alert)
    return ok(alert_service.serialize_alert(alert))


@router.patch("/job-alerts/{alert_id}", summary="Partially update a job alert")
def patch_job_alert(
    alert_id: uuid.UUID,
    body: JobAlertPatch,
    user: User = Depends(seeker_only),
    db: Session = Depends(get_db),
):
    alert = alert_service.get_alert(db, user.id, alert_id)
    alert_service.update_alert(db, alert, body.model_dump(exclude_unset=True))
    db.commit()
    db.refresh(alert)
    return ok(alert_service.serialize_alert(alert))


@router.post("/job-alerts/{alert_id}/pause", summary="Pause a job alert")
def pause_job_alert(alert_id: uuid.UUID, user: User = Depends(seeker_only), db: Session = Depends(get_db)):
    alert = alert_service.get_alert(db, user.id, alert_id)
    alert_service.update_alert(db, alert, {"is_paused": True})
    db.commit()
    db.refresh(alert)
    return ok(alert_service.serialize_alert(alert))


@router.post("/job-alerts/{alert_id}/resume", summary="Resume a job alert")
def resume_job_alert(alert_id: uuid.UUID, user: User = Depends(seeker_only), db: Session = Depends(get_db)):
    alert = alert_service.get_alert(db, user.id, alert_id)
    alert_service.update_alert(db, alert, {"is_paused": False})
    db.commit()
    db.refresh(alert)
    return ok(alert_service.serialize_alert(alert))


@router.delete("/job-alerts/{alert_id}", summary="Delete a job alert")
def delete_job_alert(alert_id: uuid.UUID, user: User = Depends(seeker_only), db: Session = Depends(get_db)):
    alert = alert_service.get_alert(db, user.id, alert_id)
    db.delete(alert)
    db.commit()
    return ok({"id": alert_id, "deleted": True})


# --------------------------------------------------------------------------- companies


@router.get("/companies/following", summary="Companies I follow")
def following_companies(
    params: PageParams = Depends(page_params),
    user: User = Depends(seeker_only),
    db: Session = Depends(get_db),
):
    rows, total = paginate(db, actions.following_stmt(user.id), params)
    return paged(actions.serialize_following(db, rows), params.page, params.page_size, total)


@router.post("/companies/{company_id}/follow", summary="Follow a company (idempotent)")
def follow_company(company_id: uuid.UUID, user: User = Depends(seeker_only), db: Session = Depends(get_db)):
    created = actions.follow_company(db, user.id, company_id)
    db.commit()
    return ok({"companyId": company_id, "following": True}, status_code=201 if created else 200)


@router.delete("/companies/{company_id}/follow", summary="Unfollow a company")
def unfollow_company(company_id: uuid.UUID, user: User = Depends(seeker_only), db: Session = Depends(get_db)):
    removed = actions.unfollow_company(db, user.id, company_id)
    db.commit()
    return ok({"companyId": company_id, "following": False, "removed": removed})


@router.post("/companies/{company_id}/reviews", summary="Review a company (moderated)")
def review_company(
    company_id: uuid.UUID,
    body: ReviewIn,
    user: User = Depends(seeker_only),
    db: Session = Depends(get_db),
):
    review = actions.add_review(db, user.id, company_id, body.rating, body.title, body.body)
    db.commit()
    return ok(actions.serialize_review(review), status_code=201)


# --------------------------------------------------------------------------- searches


@router.get("/searches/recent", summary="Recent searches")
def recent_searches(
    params: PageParams = Depends(page_params),
    user: User = Depends(seeker_only),
    db: Session = Depends(get_db),
):
    rows, total = paginate(db, actions.recent_searches_stmt(user.id), params)
    return paged([actions.serialize_recent_search(r) for r in rows], params.page, params.page_size, total)


@router.delete("/searches/recent", summary="Clear recent searches")
def clear_recent_searches(user: User = Depends(seeker_only), db: Session = Depends(get_db)):
    removed = actions.clear_recent_searches(db, user.id)
    db.commit()
    return ok({"cleared": removed})


@router.get("/searches/saved", summary="Saved searches")
def saved_searches(
    params: PageParams = Depends(page_params),
    user: User = Depends(seeker_only),
    db: Session = Depends(get_db),
):
    rows, total = paginate(db, actions.saved_searches_stmt(user.id), params)
    return paged([actions.serialize_saved_search(r) for r in rows], params.page, params.page_size, total)


@router.post("/searches/saved", summary="Save a search")
def create_saved_search(body: SavedSearchIn, user: User = Depends(seeker_only), db: Session = Depends(get_db)):
    item = actions.create_saved_search(db, user.id, body.name, body.query, body.filters)
    db.commit()
    db.refresh(item)
    return ok(actions.serialize_saved_search(item), status_code=201)


@router.delete("/searches/saved/{search_id}", summary="Delete a saved search")
def delete_saved_search(search_id: uuid.UUID, user: User = Depends(seeker_only), db: Session = Depends(get_db)):
    actions.delete_saved_search(db, user.id, search_id)
    db.commit()
    return ok({"id": search_id, "deleted": True})
