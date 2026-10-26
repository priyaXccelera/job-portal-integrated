"""Recruiter company management, credits, candidate database and talent pools."""

from __future__ import annotations

import logging
import uuid
from typing import Literal

from fastapi import APIRouter, Depends, File, Query, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.core.deps import RecruiterContext, get_db, recruiter_ctx
from app.core.errors import AppError
from app.core.responses import PageParams, ok, page_params, paged, paginate
from app.models.company import CreditLog
from app.schemas.recruiter import (
    CandidateInviteCreate,
    CompanyUpdate,
    FolderCandidateIn,
    FolderIn,
    InvitationCreate,
)
from app.services import candidate_search, candidate_service, company_service, credits
from app.services.candidate_search import CandidateFilters, split_csv

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/recruiter", tags=["recruiter"])

CREDIT_LOG_PREVIEW = 20


# --------------------------------------------------------------------------- company


@router.get("/company", summary="Own company profile, status, credits and quota")
def get_company(ctx: RecruiterContext = Depends(recruiter_ctx), db: Session = Depends(get_db)):
    return ok(company_service.serialize_company(db, ctx.company, ctx.is_company_admin))


@router.put("/company", summary="Update company profile (company admin only)")
def update_company(
    body: CompanyUpdate, ctx: RecruiterContext = Depends(recruiter_ctx), db: Session = Depends(get_db)
):
    data = company_service.update_company(db, ctx, body)
    db.commit()
    return ok(data)


@router.post("/company/logo", summary="Upload company logo (company admin only)")
def upload_logo(
    file: UploadFile = File(...), ctx: RecruiterContext = Depends(recruiter_ctx), db: Session = Depends(get_db)
):
    return ok(company_service.save_company_image(db, ctx, "logo", file.filename, file.content_type, file.file))


@router.post("/company/banner", summary="Upload company banner (company admin only)")
def upload_banner(
    file: UploadFile = File(...), ctx: RecruiterContext = Depends(recruiter_ctx), db: Session = Depends(get_db)
):
    return ok(company_service.save_company_image(db, ctx, "banner", file.filename, file.content_type, file.file))


@router.get("/company/recruiters", summary="Recruiters of the company")
def list_team(
    params: PageParams = Depends(page_params),
    ctx: RecruiterContext = Depends(recruiter_ctx),
    db: Session = Depends(get_db),
):
    rows, total = paginate(db, company_service.team_stmt(ctx.company.id), params)
    return paged([company_service.serialize_member(u) for u in rows], params.page, params.page_size, total)


@router.post("/company/invitations", summary="Invite a recruiter by email (company admin only)")
def create_invitation(
    body: InvitationCreate, ctx: RecruiterContext = Depends(recruiter_ctx), db: Session = Depends(get_db)
):
    data, raw_token, link = company_service.create_invitation(db, ctx, body.email)
    db.commit()
    company_service.send_invitation_email(body.email, ctx.company.name, ctx.user.name, link)
    if settings.expose_dev_codes:
        data["devToken"] = raw_token
    return ok(data, status_code=201)


@router.get("/company/invitations", summary="Company invitations (company admin only)")
def list_invitations(
    status: str | None = Query(None, description="PENDING | ACCEPTED | REVOKED | EXPIRED"),
    params: PageParams = Depends(page_params),
    ctx: RecruiterContext = Depends(recruiter_ctx),
    db: Session = Depends(get_db),
):
    company_service.require_company_admin(ctx)
    rows, total = paginate(db, company_service.invitations_stmt(ctx.company.id, status), params)
    return paged([company_service.serialize_invitation(i) for i in rows], params.page, params.page_size, total)


@router.delete("/company/invitations/{invitation_id}", summary="Revoke a pending invitation")
def revoke_invitation(
    invitation_id: uuid.UUID, ctx: RecruiterContext = Depends(recruiter_ctx), db: Session = Depends(get_db)
):
    data = company_service.revoke_invitation(db, ctx, invitation_id)
    db.commit()
    return ok(data)


# --------------------------------------------------------------------------- credits


def _balance_summary(ctx: RecruiterContext) -> dict:
    company = ctx.company
    return {
        "balance": company.credits,
        "jobQuota": company.job_quota,
        "jobsPosted": company.jobs_posted,
        "quotaRemaining": max(company.job_quota - company.jobs_posted, 0),
    }


def _log_stmt(company_id: uuid.UUID, order: str):
    stmt = select(CreditLog).where(CreditLog.company_id == company_id)
    if order == "asc":
        return stmt.order_by(CreditLog.created_at.asc(), CreditLog.id.asc())
    return stmt.order_by(CreditLog.created_at.desc(), CreditLog.id.desc())


@router.get("/credits", summary="Credit balance, job quota and latest credit log entries")
def get_credits(ctx: RecruiterContext = Depends(recruiter_ctx), db: Session = Depends(get_db)):
    rows = db.scalars(_log_stmt(ctx.company.id, "desc").limit(CREDIT_LOG_PREVIEW)).all()
    data = _balance_summary(ctx)
    data["log"] = [credits.serialize_log(r) for r in rows]
    return ok(data)


@router.get("/credits/log", summary="Paged credit usage log, newest first")
def get_credit_log(
    sort: Literal["createdAt"] = Query("createdAt"),
    order: Literal["asc", "desc"] = Query("desc"),
    params: PageParams = Depends(page_params),
    ctx: RecruiterContext = Depends(recruiter_ctx),
    db: Session = Depends(get_db),
):
    rows, total = paginate(db, _log_stmt(ctx.company.id, order), params)
    return paged([credits.serialize_log(r) for r in rows], params.page, params.page_size, total)


# --------------------------------------------------------------------------- candidate database
# Static /candidates/search is declared before /candidates/{candidate_id}.


def _range_check(low: float | None, high: float | None, field: str) -> None:
    if low is not None and high is not None and low > high:
        message = f"{field}Min must not exceed {field}Max"
        raise AppError(422, "VALIDATION_ERROR", message, [{"field": f"{field}Min", "message": message}])


@router.get("/candidates/search", summary="Search the candidate database (approved companies only)")
def search_candidates(
    q: str | None = Query(None, max_length=500, description="Boolean keywords: AND / OR / NOT, quotes, parentheses"),
    skills: str | None = Query(None, description="Comma separated; all must match"),
    experience_min: float | None = Query(None, alias="experienceMin", ge=0, le=60),
    experience_max: float | None = Query(None, alias="experienceMax", ge=0, le=60),
    location: str | None = Query(None, description="Comma separated; current or preferred location"),
    ctc_min: float | None = Query(None, alias="ctcMin", ge=0),
    ctc_max: float | None = Query(None, alias="ctcMax", ge=0),
    notice_period: str | None = Query(None, alias="noticePeriod"),
    education: str | None = Query(None),
    industry: str | None = Query(None),
    last_active_days: int | None = Query(None, alias="lastActiveDays", ge=1, le=3650),
    sort: Literal["relevance", "experience", "lastActive"] = Query("relevance"),
    params: PageParams = Depends(page_params),
    ctx: RecruiterContext = Depends(recruiter_ctx),
    db: Session = Depends(get_db),
):
    candidate_service.require_approved(ctx.company)
    _range_check(experience_min, experience_max, "experience")
    _range_check(ctc_min, ctc_max, "ctc")
    filters = CandidateFilters(
        q=q,
        skills=split_csv(skills),
        experience_min=experience_min,
        experience_max=experience_max,
        locations=split_csv(location),
        ctc_min=ctc_min,
        ctc_max=ctc_max,
        notice_periods=split_csv(notice_period),
        education=split_csv(education),
        industries=split_csv(industry),
        last_active_days=last_active_days,
        sort=sort,
    )
    items, total = candidate_search.search_candidates(db, ctx.company, filters, params.page, params.page_size)
    return paged(items, params.page, params.page_size, total)


@router.get("/candidates/{candidate_id}", summary="Candidate profile (masked until unlocked); records a profile view")
def get_candidate(
    candidate_id: uuid.UUID, ctx: RecruiterContext = Depends(recruiter_ctx), db: Session = Depends(get_db)
):
    candidate_service.require_approved(ctx.company)
    user, profile = candidate_service.get_visible_candidate(db, ctx.company, candidate_id)
    candidate_service.record_profile_view(db, ctx, candidate_id)
    detail = candidate_service.candidate_detail(db, ctx.company, user, profile)
    db.commit()
    return ok(detail)


@router.post("/candidates/{candidate_id}/unlock", summary="Unlock candidate contact details (charged once)")
def unlock_candidate(
    candidate_id: uuid.UUID, ctx: RecruiterContext = Depends(recruiter_ctx), db: Session = Depends(get_db)
):
    result = candidate_service.unlock_candidate(db, ctx, candidate_id)
    db.commit()
    return ok(result, status_code=201 if result["charged"] else 200)


@router.post("/candidates/{candidate_id}/invite", summary="Invite a candidate to apply for an active job")
def invite_candidate(
    candidate_id: uuid.UUID,
    body: CandidateInviteCreate,
    ctx: RecruiterContext = Depends(recruiter_ctx),
    db: Session = Depends(get_db),
):
    result = candidate_service.invite_candidate(db, ctx, candidate_id, body.job_id, body.message)
    db.commit()
    return ok(result, status_code=201)


# --------------------------------------------------------------------------- folders (talent pools)


@router.get("/folders", summary="Talent pool folders with candidate counts")
def list_folders(
    params: PageParams = Depends(page_params),
    ctx: RecruiterContext = Depends(recruiter_ctx),
    db: Session = Depends(get_db),
):
    rows, total = paginate(db, candidate_service.folders_stmt(ctx.company.id), params)
    items = [candidate_service.serialize_folder(folder, count) for folder, count in rows]
    return paged(items, params.page, params.page_size, total)


@router.post("/folders", summary="Create a folder")
def create_folder(body: FolderIn, ctx: RecruiterContext = Depends(recruiter_ctx), db: Session = Depends(get_db)):
    data = candidate_service.create_folder(db, ctx, body.name)
    db.commit()
    return ok(data, status_code=201)


@router.put("/folders/{folder_id}", summary="Rename a folder")
def rename_folder(
    folder_id: uuid.UUID,
    body: FolderIn,
    ctx: RecruiterContext = Depends(recruiter_ctx),
    db: Session = Depends(get_db),
):
    data = candidate_service.rename_folder(db, ctx, folder_id, body.name)
    db.commit()
    return ok(data)


@router.delete("/folders/{folder_id}", summary="Delete a folder and its candidate links")
def delete_folder(folder_id: uuid.UUID, ctx: RecruiterContext = Depends(recruiter_ctx), db: Session = Depends(get_db)):
    candidate_service.delete_folder(db, ctx, folder_id)
    db.commit()
    return ok({"id": folder_id, "deleted": True})


@router.get("/folders/{folder_id}/candidates", summary="Candidates in a folder (masked until unlocked)")
def list_folder_candidates(
    folder_id: uuid.UUID,
    params: PageParams = Depends(page_params),
    ctx: RecruiterContext = Depends(recruiter_ctx),
    db: Session = Depends(get_db),
):
    items, total = candidate_service.folder_candidates(db, ctx, folder_id, params)
    return paged(items, params.page, params.page_size, total)


@router.post("/folders/{folder_id}/candidates", summary="Add a visible candidate to a folder")
def add_folder_candidate(
    folder_id: uuid.UUID,
    body: FolderCandidateIn,
    ctx: RecruiterContext = Depends(recruiter_ctx),
    db: Session = Depends(get_db),
):
    data = candidate_service.add_folder_candidate(db, ctx, folder_id, body.candidate_id, body.note)
    db.commit()
    return ok(data, status_code=201)


@router.delete("/folders/{folder_id}/candidates/{candidate_id}", summary="Remove a candidate from a folder")
def remove_folder_candidate(
    folder_id: uuid.UUID,
    candidate_id: uuid.UUID,
    ctx: RecruiterContext = Depends(recruiter_ctx),
    db: Session = Depends(get_db),
):
    candidate_service.remove_folder_candidate(db, ctx, folder_id, candidate_id)
    db.commit()
    return ok({"folderId": folder_id, "candidateId": candidate_id, "removed": True})
