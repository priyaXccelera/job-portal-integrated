"""Recruiter job management, applicant pipeline, interviews and dashboard.

Thin HTTP layer: business rules live in app.services.{job_service, jobs_lifecycle,
applicant_service, dashboard}. Every route requires a recruiter with a company.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from decimal import Decimal

from fastapi import APIRouter, Depends, Query
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.deps import RecruiterContext, get_db, recruiter_ctx
from app.core.errors import AppError, NotFoundError
from app.core.responses import PageParams, csv_response, ok, page_params, paged, paginate
from app.models.enums import ApplicationStatus, JobStatus
from app.models.profile import Resume
from app.schemas.recruiter_jobs import (
    ApplicationStatusIn,
    BulkRejectIn,
    BulkStatusIn,
    InterviewIn,
    JobIn,
    JobStatusIn,
    NoteIn,
    RatingIn,
)
from app.services import applicant_service as applicants
from app.services import job_service as jobs
from app.services.dashboard import build_dashboard
from app.services.jobs_lifecycle import JobLifecycleService
from app.services.profile_service import resume_file_path

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/recruiter", tags=["recruiter-jobs"])


@contextmanager
def _atomic(db: Session) -> Iterator[None]:
    """Roll the whole request back when a business rule or DB error aborts it."""
    try:
        yield
    except (AppError, SQLAlchemyError):
        db.rollback()
        raise


def _job_response(db: Session, job_id: uuid.UUID, company_id: uuid.UUID, status_code: int = 200) -> JSONResponse:
    job = jobs.get_company_job(db, job_id, company_id)
    return ok(jobs.serialize_jobs(db, [job], detail=True)[0], status_code=status_code)


# =========================================================================== dashboard


@router.get("/dashboard")
def dashboard(ctx: RecruiterContext = Depends(recruiter_ctx), db: Session = Depends(get_db)):
    return ok(build_dashboard(db, ctx.company.id))


# =========================================================================== jobs


@router.post("/jobs", status_code=201)
def create_job(body: JobIn, ctx: RecruiterContext = Depends(recruiter_ctx), db: Session = Depends(get_db)):
    with _atomic(db):
        job = jobs.create_job(db, ctx.user.id, ctx.company.id, body)
        if body.publish:
            JobLifecycleService(db).publish(job)
        db.commit()
    return _job_response(db, job.id, ctx.company.id, status_code=201)


@router.get("/jobs")
def list_jobs(
    status: str | None = Query(None, description="Comma-separated job statuses"),
    q: str | None = Query(None, max_length=200, description="Title search"),
    sort: str = Query("createdAt", description="postedAt | createdAt | applicationCount | viewCount"),
    order: str = Query("desc", description="asc | desc"),
    params: PageParams = Depends(page_params),
    ctx: RecruiterContext = Depends(recruiter_ctx),
    db: Session = Depends(get_db),
):
    sort_key, direction = jobs.parse_sort(sort, order)
    stmt = jobs.list_stmt(ctx.company.id, jobs.parse_statuses(status), q, sort_key, direction)
    rows, total = paginate(db, stmt, params)
    return paged(jobs.serialize_jobs(db, rows), params.page, params.page_size, total)


@router.get("/jobs/{job_id}")
def get_job(job_id: uuid.UUID, ctx: RecruiterContext = Depends(recruiter_ctx), db: Session = Depends(get_db)):
    return _job_response(db, job_id, ctx.company.id)


@router.put("/jobs/{job_id}")
def update_job(
    job_id: uuid.UUID, body: JobIn, ctx: RecruiterContext = Depends(recruiter_ctx), db: Session = Depends(get_db)
):
    with _atomic(db):
        job = jobs.get_company_job(db, job_id, ctx.company.id, lock=True)
        jobs.update_job(db, job, body)
        if body.publish and job.status == JobStatus.DRAFT:
            JobLifecycleService(db).publish(job)
        logger.info("Job %s edited by %s (status %s)", job.id, ctx.user.id, job.status.value)
        db.commit()
    return _job_response(db, job_id, ctx.company.id)


@router.delete("/jobs/{job_id}")
def delete_job(job_id: uuid.UUID, ctx: RecruiterContext = Depends(recruiter_ctx), db: Session = Depends(get_db)):
    with _atomic(db):
        job = jobs.get_company_job(db, job_id, ctx.company.id, lock=True)
        jobs.soft_delete(job)
        db.commit()
    return ok({"id": job_id, "deleted": True})


@router.patch("/jobs/{job_id}/status")
def change_job_status(
    job_id: uuid.UUID,
    body: JobStatusIn,
    ctx: RecruiterContext = Depends(recruiter_ctx),
    db: Session = Depends(get_db),
):
    with _atomic(db):
        job = jobs.get_company_job(db, job_id, ctx.company.id, lock=True)
        JobLifecycleService(db).change_status(job, body.status, body.reason)
        db.commit()
    return _job_response(db, job_id, ctx.company.id)


@router.post("/jobs/{job_id}/duplicate", status_code=201)
def duplicate_job(job_id: uuid.UUID, ctx: RecruiterContext = Depends(recruiter_ctx), db: Session = Depends(get_db)):
    with _atomic(db):
        job = jobs.get_company_job(db, job_id, ctx.company.id)
        copy = JobLifecycleService(db).duplicate(job, ctx.user.id)
        db.commit()
    return _job_response(db, copy.id, ctx.company.id, status_code=201)


@router.post("/jobs/{job_id}/refresh")
def refresh_job(job_id: uuid.UUID, ctx: RecruiterContext = Depends(recruiter_ctx), db: Session = Depends(get_db)):
    with _atomic(db):
        job = jobs.get_company_job(db, job_id, ctx.company.id, lock=True)
        JobLifecycleService(db).refresh(job)
        db.commit()
    return _job_response(db, job_id, ctx.company.id)


# =========================================================================== applicants


def _applicant_filters(
    status: str | None = Query(None, description="Comma-separated application statuses"),
    experience_min: float | None = Query(None, alias="experienceMin", ge=0),
    experience_max: float | None = Query(None, alias="experienceMax", ge=0),
    location: str | None = Query(None, description="Comma-separated locations"),
    ctc_min: Decimal | None = Query(None, alias="ctcMin", ge=0),
    ctc_max: Decimal | None = Query(None, alias="ctcMax", ge=0),
    skills: str | None = Query(None, description="Comma-separated; candidate must have all"),
    notice_period: str | None = Query(None, alias="noticePeriod"),
    education: str | None = Query(None),
    screening: str = Query("in", description="in | out | all"),
    q: str | None = Query(None, max_length=200),
    sort: str = Query("match", description="match | date"),
    order: str = Query("desc", description="asc | desc"),
) -> applicants.ApplicantFilters:
    return applicants.ApplicantFilters(
        statuses=applicants.ApplicantFilters.parse_statuses(status),
        experience_min=experience_min,
        experience_max=experience_max,
        locations=applicants.split_csv(location),
        ctc_min=ctc_min,
        ctc_max=ctc_max,
        skills=applicants.split_csv(skills),
        notice_periods=applicants.split_csv(notice_period),
        education=applicants.split_csv(education),
        screening=screening.lower(),
        q=q,
        sort=sort.lower(),
        order=order.lower(),
    ).validate()


@router.get("/jobs/{job_id}/applicants/export")
def export_applicants(
    job_id: uuid.UUID,
    filters: applicants.ApplicantFilters = Depends(_applicant_filters),
    ctx: RecruiterContext = Depends(recruiter_ctx),
    db: Session = Depends(get_db),
) -> StreamingResponse:
    job = jobs.get_company_job(db, job_id, ctx.company.id)
    rows = applicants.export_rows(db, applicants.applicants_stmt(job.id, filters))
    return csv_response(f"applicants-{job.id}.csv", applicants.CSV_HEADER, rows)


@router.get("/jobs/{job_id}/applicants")
def list_applicants(
    job_id: uuid.UUID,
    filters: applicants.ApplicantFilters = Depends(_applicant_filters),
    params: PageParams = Depends(page_params),
    ctx: RecruiterContext = Depends(recruiter_ctx),
    db: Session = Depends(get_db),
):
    job = jobs.get_company_job(db, job_id, ctx.company.id)
    rows, total = paginate(db, applicants.applicants_stmt(job.id, filters), params)
    return paged(applicants.serialize_applicants(db, rows), params.page, params.page_size, total)


# =========================================================================== applications
# NOTE: static bulk routes are declared before the /applications/{application_id} routes.


@router.post("/applications/bulk-status")
def bulk_status(body: BulkStatusIn, ctx: RecruiterContext = Depends(recruiter_ctx), db: Session = Depends(get_db)):
    with _atomic(db):
        result = applicants.bulk_change_status(
            db, ctx.company.id, ctx.user, body.application_ids, body.status, body.message
        )
        db.commit()
    return ok(result)


@router.post("/applications/bulk-reject")
def bulk_reject(body: BulkRejectIn, ctx: RecruiterContext = Depends(recruiter_ctx), db: Session = Depends(get_db)):
    with _atomic(db):
        result = applicants.bulk_change_status(
            db, ctx.company.id, ctx.user, body.application_ids, ApplicationStatus.REJECTED, body.message
        )
        db.commit()
    return ok(result)


@router.get("/applications/{application_id}")
def get_application(
    application_id: uuid.UUID, ctx: RecruiterContext = Depends(recruiter_ctx), db: Session = Depends(get_db)
):
    with _atomic(db):
        application, _job = applicants.get_company_application(db, application_id, ctx.company.id)
        if applicants.mark_viewed(db, application, ctx.user):
            db.commit()
    return ok(applicants.application_detail(db, application))


@router.patch("/applications/{application_id}/status")
def change_application_status(
    application_id: uuid.UUID,
    body: ApplicationStatusIn,
    ctx: RecruiterContext = Depends(recruiter_ctx),
    db: Session = Depends(get_db),
):
    with _atomic(db):
        application, _job = applicants.get_company_application(db, application_id, ctx.company.id)
        applicants.change_status_as_recruiter(db, application, body.status, ctx.user, body.message)
        db.commit()
    return ok(applicants.application_detail(db, application))


@router.post("/applications/{application_id}/notes", status_code=201)
def add_note(
    application_id: uuid.UUID,
    body: NoteIn,
    ctx: RecruiterContext = Depends(recruiter_ctx),
    db: Session = Depends(get_db),
):
    with _atomic(db):
        application, _job = applicants.get_company_application(db, application_id, ctx.company.id)
        note = applicants.add_note(db, application, ctx.user, body.note)
        db.commit()
    return ok(note, status_code=201)


@router.get("/applications/{application_id}/notes")
def list_notes(
    application_id: uuid.UUID,
    params: PageParams = Depends(page_params),
    ctx: RecruiterContext = Depends(recruiter_ctx),
    db: Session = Depends(get_db),
):
    application, _job = applicants.get_company_application(db, application_id, ctx.company.id)
    rows, total = paginate(db, applicants.notes_stmt(application.id), params)
    return paged(applicants.serialize_notes(db, rows), params.page, params.page_size, total)


@router.put("/applications/{application_id}/rating")
def rate_application(
    application_id: uuid.UUID,
    body: RatingIn,
    ctx: RecruiterContext = Depends(recruiter_ctx),
    db: Session = Depends(get_db),
):
    with _atomic(db):
        application, _job = applicants.get_company_application(db, application_id, ctx.company.id)
        applicants.set_rating(application, body.rating)
        db.commit()
    return ok({"applicationId": application.id, "rating": application.rating})


@router.get("/applications/{application_id}/resume")
def download_resume(
    application_id: uuid.UUID, ctx: RecruiterContext = Depends(recruiter_ctx), db: Session = Depends(get_db)
):
    application, _job = applicants.get_company_application(db, application_id, ctx.company.id)
    resume = db.get(Resume, application.resume_id) if application.resume_id else None
    if resume is None:
        raise NotFoundError("This application has no resume")
    path = resume_file_path(resume)
    return FileResponse(
        path,
        media_type=resume.content_type or "application/octet-stream",
        filename=resume.file_name,
    )


@router.post("/applications/{application_id}/interview", status_code=201)
def schedule_interview(
    application_id: uuid.UUID,
    body: InterviewIn,
    ctx: RecruiterContext = Depends(recruiter_ctx),
    db: Session = Depends(get_db),
):
    with _atomic(db):
        application, job = applicants.get_company_application(db, application_id, ctx.company.id)
        interview = applicants.schedule_interview(db, application, job, ctx.user, body)
        db.commit()
    return ok(applicants.interview_dict(interview, application), status_code=201)
