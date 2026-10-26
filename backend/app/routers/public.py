"""Public routes: job search, job detail, suggestions, company pages and master data."""

from __future__ import annotations

import uuid
from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.deps import get_db, optional_user
from app.core.errors import AppError
from app.core.ratelimit import rate_limit
from app.core.responses import PageParams, ok, page_params, paged
from app.models.accounts import User
from app.services import search as search_service
from app.services import search_public
from app.services.search import FRESHNESS_DAYS, JobSearchFilters, split_csv

router = APIRouter(tags=["public"])


def _validation_error(field: str, message: str) -> AppError:
    return AppError(422, "VALIDATION_ERROR", message, [{"field": field, "message": message}])


# --------------------------------------------------------------------------- search

@router.get("/jobs/search", dependencies=[Depends(rate_limit("search"))])
def search_jobs(
    q: str | None = Query(None, max_length=200),
    location: str | None = Query(None, description="Comma separated cities"),
    experience: float | None = Query(None, ge=0, le=60),
    salary_min: float | None = Query(None, alias="salaryMin", ge=0),
    salary_max: float | None = Query(None, alias="salaryMax", ge=0),
    department: str | None = None,
    role_category: str | None = Query(None, alias="roleCategory"),
    industry: str | None = None,
    company_type: str | None = Query(None, alias="companyType"),
    company: str | None = Query(None, description="Comma separated company ids or names"),
    job_type: str | None = Query(None, alias="jobType"),
    employment_type: str | None = Query(None, alias="employmentType"),
    work_mode: str | None = Query(None, alias="workMode"),
    education: str | None = None,
    freshness: int | None = Query(None, description="1, 3, 7, 15 or 30 days"),
    posted_by: str | None = Query(None, alias="postedBy", description="company | consultancy"),
    walk_in: bool = Query(False, alias="walkIn"),
    sort: Literal["relevance", "date"] | None = None,
    params: PageParams = Depends(page_params),
    user: User | None = Depends(optional_user),
    db: Session = Depends(get_db),
):
    if freshness is not None and freshness not in FRESHNESS_DAYS:
        raise _validation_error("freshness", f"freshness must be one of {', '.join(map(str, FRESHNESS_DAYS))}")
    posted_by_norm = posted_by.strip().lower() if posted_by else None
    if posted_by_norm not in (None, "company", "consultancy"):
        raise _validation_error("postedBy", "postedBy must be 'company' or 'consultancy'")
    if salary_min is not None and salary_max is not None and salary_min > salary_max:
        raise _validation_error("salaryMin", "salaryMin cannot exceed salaryMax")

    keyword = q.strip() if q and q.strip() else None
    filters = JobSearchFilters(
        q=keyword,
        location=split_csv(location),
        experience=experience,
        salary_min=salary_min,
        salary_max=salary_max,
        department=split_csv(department),
        role_category=split_csv(role_category),
        industry=split_csv(industry),
        company_type=split_csv(company_type),
        company=split_csv(company),
        job_type=split_csv(job_type),
        employment_type=split_csv(employment_type),
        work_mode=split_csv(work_mode),
        education=split_csv(education),
        freshness=freshness,
        posted_by=posted_by_norm,
        walk_in=walk_in,
    )
    effective_sort = sort or ("relevance" if keyword else "date")
    items, total, facets = search_service.search_jobs(
        db, filters, params.page, params.page_size, effective_sort, user
    )
    return paged(items, params.page, params.page_size, total, facets=facets)


# --------------------------------------------------------------------------- job detail

@router.get("/jobs/{job_id}/similar")
def similar_jobs(
    job_id: uuid.UUID,
    limit: int = Query(10, ge=1, le=50),
    user: User | None = Depends(optional_user),
    db: Session = Depends(get_db),
):
    job, _company, _live = search_public.get_visible_job(db, job_id, user)
    return ok(search_service.similar(db, job, user, limit))


@router.get("/jobs/{job_id}/company-jobs")
def jobs_of_same_company(
    job_id: uuid.UUID,
    params: PageParams = Depends(page_params),
    user: User | None = Depends(optional_user),
    db: Session = Depends(get_db),
):
    job, _company, _live = search_public.get_visible_job(db, job_id, user)
    items, total = search_service.company_jobs(
        db, job.company_id, user, params.page, params.page_size, exclude_job_id=job.id
    )
    return paged(items, params.page, params.page_size, total)


@router.get("/jobs/{job_id}")
def job_detail(
    job_id: uuid.UUID,
    user: User | None = Depends(optional_user),
    db: Session = Depends(get_db),
):
    return ok(search_public.job_detail(db, job_id, user))


# --------------------------------------------------------------------------- suggestions

@router.get("/suggestions", dependencies=[Depends(rate_limit("search"))])
def suggestions(
    q: str = Query(..., min_length=1, max_length=100),
    type: Literal["job", "skill", "company", "location"] | None = None,  # noqa: A002
    limit: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db),
    _user: User | None = Depends(optional_user),
):
    return ok(search_service.suggest(db, type, q, limit))


# --------------------------------------------------------------------------- companies

@router.get("/companies/{company_id}")
def company_detail(
    company_id: uuid.UUID,
    user: User | None = Depends(optional_user),
    db: Session = Depends(get_db),
):
    company = search_public.get_visible_company(db, company_id, user)
    return ok(search_public.company_page(db, company, user))


@router.get("/companies/{company_id}/jobs")
def company_active_jobs(
    company_id: uuid.UUID,
    params: PageParams = Depends(page_params),
    user: User | None = Depends(optional_user),
    db: Session = Depends(get_db),
):
    company = search_public.get_visible_company(db, company_id, user)
    items, total = search_service.company_jobs(db, company.id, user, params.page, params.page_size)
    return paged(items, params.page, params.page_size, total)


@router.get("/companies/{company_id}/reviews")
def company_review_list(
    company_id: uuid.UUID,
    params: PageParams = Depends(page_params),
    user: User | None = Depends(optional_user),
    db: Session = Depends(get_db),
):
    company = search_public.get_visible_company(db, company_id, user)
    items, total = search_public.company_reviews(db, company.id, params)
    return paged(items, params.page, params.page_size, total)


# --------------------------------------------------------------------------- master data

@router.get("/master/{master_type}")
def master_data(
    master_type: str,
    q: str | None = Query(None, max_length=100),
    params: PageParams = Depends(page_params),
    db: Session = Depends(get_db),
    _user: User | None = Depends(optional_user),
):
    items, total = search_public.master_list(db, master_type, q, params)
    return paged(items, params.page, params.page_size, total)
