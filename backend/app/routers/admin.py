"""Admin API: companies, moderation, reports, reviews, master data, users, analytics, audit log.

Every route requires the ADMIN role; handlers are thin and delegate to ``admin_service`` / ``analytics``.
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import Any, Literal

from fastapi import APIRouter, Body, Depends, Query
from sqlalchemy.orm import Session

from app.core.deps import get_db, require_roles
from app.core.responses import PageParams, csv_response, ok, page_params, paged
from app.models.accounts import User
from app.models.enums import CompanyStatus, JobStatus, ReportStatus, ReviewStatus, UserRole
from app.schemas.admin import (
    CompanyStatusUpdate,
    CompanyVerifyUpdate,
    CreditAdjustment,
    JobReportUpdate,
    JobStatusUpdate,
    QuotaUpdate,
    ReviewModeration,
    UserBlock,
)
from app.services import admin_service as svc
from app.services import analytics

router = APIRouter(prefix="/admin", tags=["admin"])

admin_only = require_roles(UserRole.ADMIN)

SortOrder = Literal["asc", "desc"]


# ------------------------------------------------------------------------- companies


@router.get("/companies")
def list_companies(
    status: CompanyStatus | None = None,
    q: str | None = Query(None, max_length=200),
    verified: bool | None = None,
    sort: Literal["createdAt", "name", "credits", "jobsPosted", "status"] = "createdAt",
    order: SortOrder = "desc",
    params: PageParams = Depends(page_params),
    db: Session = Depends(get_db),
    _admin: User = Depends(admin_only),
):
    items, total = svc.list_companies(db, params, status=status, q=q, verified=verified, sort=sort, order=order)
    return paged(items, params.page, params.page_size, total)


@router.get("/companies/{company_id}")
def get_company(company_id: uuid.UUID, db: Session = Depends(get_db), _admin: User = Depends(admin_only)):
    return ok(svc.company_detail(db, company_id))


@router.patch("/companies/{company_id}/status")
def update_company_status(
    company_id: uuid.UUID,
    body: CompanyStatusUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(admin_only),
):
    return ok(svc.set_company_status(db, admin, company_id, body.status, body.reason))


@router.patch("/companies/{company_id}/verify")
def update_company_verified(
    company_id: uuid.UUID,
    body: CompanyVerifyUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(admin_only),
):
    return ok(svc.set_company_verified(db, admin, company_id, body.verified))


@router.post("/companies/{company_id}/credits")
def adjust_company_credits(
    company_id: uuid.UUID,
    body: CreditAdjustment,
    db: Session = Depends(get_db),
    admin: User = Depends(admin_only),
):
    return ok(svc.adjust_credits(db, admin, company_id, body.amount, body.reason))


@router.patch("/companies/{company_id}/quota")
def update_company_quota(
    company_id: uuid.UUID,
    body: QuotaUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(admin_only),
):
    return ok(svc.set_company_quota(db, admin, company_id, body.job_quota))


@router.delete("/companies/{company_id}")
def delete_company(company_id: uuid.UUID, db: Session = Depends(get_db), admin: User = Depends(admin_only)):
    svc.delete_company(db, admin, company_id)
    return ok({"id": company_id, "deleted": True})


# ------------------------------------------------------------------------- jobs


@router.get("/jobs")
def list_jobs(
    status: JobStatus | None = None,
    q: str | None = Query(None, max_length=200),
    company_id: uuid.UUID | None = Query(None, alias="companyId"),
    sort: Literal["createdAt", "postedAt", "title", "applications"] = "createdAt",
    order: SortOrder = "desc",
    params: PageParams = Depends(page_params),
    db: Session = Depends(get_db),
    _admin: User = Depends(admin_only),
):
    items, total = svc.list_jobs(db, params, status=status, q=q, company_id=company_id, sort=sort, order=order)
    return paged(items, params.page, params.page_size, total)


# static path: must be declared before /jobs/{job_id}
@router.get("/jobs/moderation")
def job_moderation_queue(
    params: PageParams = Depends(page_params),
    db: Session = Depends(get_db),
    _admin: User = Depends(admin_only),
):
    items, total = svc.moderation_queue(db, params)
    return paged(items, params.page, params.page_size, total)


@router.get("/jobs/{job_id}")
def get_job(job_id: uuid.UUID, db: Session = Depends(get_db), _admin: User = Depends(admin_only)):
    return ok(svc.job_detail(db, job_id))


@router.patch("/jobs/{job_id}/status")
def update_job_status(
    job_id: uuid.UUID,
    body: JobStatusUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(admin_only),
):
    return ok(svc.set_job_status(db, admin, job_id, body.status, body.reason))


# ------------------------------------------------------------------------- job reports


@router.get("/job-reports")
def list_job_reports(
    status: ReportStatus | None = None,
    params: PageParams = Depends(page_params),
    db: Session = Depends(get_db),
    _admin: User = Depends(admin_only),
):
    items, total = svc.list_reports(db, params, status)
    return paged(items, params.page, params.page_size, total)


@router.patch("/job-reports/{report_id}")
def update_job_report(
    report_id: uuid.UUID,
    body: JobReportUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(admin_only),
):
    return ok(svc.update_report(db, admin, report_id, body.status, body.takedown, body.reason))


# ------------------------------------------------------------------------- reviews


@router.get("/reviews")
def list_reviews(
    status: ReviewStatus = ReviewStatus.PENDING,
    params: PageParams = Depends(page_params),
    db: Session = Depends(get_db),
    _admin: User = Depends(admin_only),
):
    items, total = svc.list_reviews(db, params, status)
    return paged(items, params.page, params.page_size, total)


@router.patch("/reviews/{review_id}")
def moderate_review(
    review_id: uuid.UUID,
    body: ReviewModeration,
    db: Session = Depends(get_db),
    admin: User = Depends(admin_only),
):
    return ok(svc.moderate_review(db, admin, review_id, body.status))


# ------------------------------------------------------------------------- master data


@router.get("/master/{type_key}")
def list_master(
    type_key: str,
    q: str | None = Query(None, max_length=200),
    params: PageParams = Depends(page_params),
    db: Session = Depends(get_db),
    _admin: User = Depends(admin_only),
):
    items, total = svc.list_master(db, type_key, params, q)
    return paged(items, params.page, params.page_size, total)


@router.post("/master/{type_key}")
def create_master(
    type_key: str,
    body: dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
    admin: User = Depends(admin_only),
):
    return ok(svc.create_master(db, admin, type_key, body), status_code=201)


@router.get("/master/{type_key}/{item_id}")
def get_master(
    type_key: str, item_id: uuid.UUID, db: Session = Depends(get_db), _admin: User = Depends(admin_only)
):
    return ok(svc.get_master(db, type_key, item_id))


@router.put("/master/{type_key}/{item_id}")
def update_master(
    type_key: str,
    item_id: uuid.UUID,
    body: dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
    admin: User = Depends(admin_only),
):
    return ok(svc.update_master(db, admin, type_key, item_id, body))


@router.delete("/master/{type_key}/{item_id}")
def delete_master(
    type_key: str, item_id: uuid.UUID, db: Session = Depends(get_db), admin: User = Depends(admin_only)
):
    svc.delete_master(db, admin, type_key, item_id)
    return ok({"id": item_id, "deleted": True})


# ------------------------------------------------------------------------- users


@router.get("/users")
def list_users(
    q: str | None = Query(None, max_length=200),
    role: UserRole | None = None,
    status: Literal["blocked", "active", "deleted"] | None = None,
    email_verified: bool | None = Query(None, alias="emailVerified"),
    sort: Literal["createdAt", "name", "email"] = "createdAt",
    order: SortOrder = "desc",
    params: PageParams = Depends(page_params),
    db: Session = Depends(get_db),
    _admin: User = Depends(admin_only),
):
    items, total = svc.list_users(
        db, params, q=q, role=role, status=status, email_verified=email_verified, sort=sort, order=order
    )
    return paged(items, params.page, params.page_size, total)


@router.get("/users/{user_id}")
def get_user(user_id: uuid.UUID, db: Session = Depends(get_db), _admin: User = Depends(admin_only)):
    return ok(svc.user_detail(db, user_id, include_deleted=True))


@router.patch("/users/{user_id}/block")
def block_user(
    user_id: uuid.UUID, body: UserBlock, db: Session = Depends(get_db), admin: User = Depends(admin_only)
):
    return ok(svc.block_user(db, admin, user_id, body.reason))


@router.patch("/users/{user_id}/unblock")
def unblock_user(user_id: uuid.UUID, db: Session = Depends(get_db), admin: User = Depends(admin_only)):
    return ok(svc.unblock_user(db, admin, user_id))


@router.post("/users/{user_id}/reset-verification")
def reset_user_verification(user_id: uuid.UUID, db: Session = Depends(get_db), admin: User = Depends(admin_only)):
    return ok(svc.reset_verification(db, admin, user_id))


@router.delete("/users/{user_id}")
def delete_user(user_id: uuid.UUID, db: Session = Depends(get_db), admin: User = Depends(admin_only)):
    svc.delete_user(db, admin, user_id)
    return ok({"id": user_id, "deleted": True})


# ------------------------------------------------------------------------- analytics & audit


@router.get("/analytics")
def get_analytics(
    date_from: date | None = Query(None, alias="from", description="YYYY-MM-DD (default: 30 days ago)"),
    date_to: date | None = Query(None, alias="to", description="YYYY-MM-DD (default: today)"),
    db: Session = Depends(get_db),
    _admin: User = Depends(admin_only),
):
    rng = analytics.resolve_range(date_from, date_to)
    return ok(analytics.build_analytics(db, rng))


@router.get("/analytics/export")
def export_analytics(
    date_from: date | None = Query(None, alias="from"),
    date_to: date | None = Query(None, alias="to"),
    db: Session = Depends(get_db),
    _admin: User = Depends(admin_only),
):
    rng = analytics.resolve_range(date_from, date_to)
    data = analytics.build_analytics(db, rng)
    filename = f"analytics_{rng.start_date.isoformat()}_{rng.end_date.isoformat()}.csv"
    return csv_response(filename, analytics.CSV_HEADER, analytics.analytics_csv_rows(data))


@router.get("/audit-logs")
def list_audit_logs(
    action: str | None = Query(None, max_length=100),
    actor_id: uuid.UUID | None = Query(None, alias="actorId"),
    entity_type: str | None = Query(None, alias="entityType", max_length=64),
    date_from: date | None = Query(None, alias="from"),
    date_to: date | None = Query(None, alias="to"),
    params: PageParams = Depends(page_params),
    db: Session = Depends(get_db),
    _admin: User = Depends(admin_only),
):
    items, total = svc.list_audit_logs(
        db, params, action=action, actor_id=actor_id, entity_type=entity_type, date_from=date_from, date_to=date_to
    )
    return paged(items, params.page, params.page_size, total)
