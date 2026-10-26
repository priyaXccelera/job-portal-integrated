"""Public-facing read services: job detail (+ unique view counting), company page/reviews, master lists."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.core.responses import PageParams, paginate
from app.models.accounts import User
from app.models.applications import Application
from app.models.company import Company, CompanyFollow, CompanyReview
from app.models.enums import CompanyStatus, JobStatus, ReviewStatus, UserRole
from app.models.jobs import Job, JobView, SavedJob
from app.models.master import MASTER_TYPES, Location, Skill
from app.services import matching
from app.services.search import company_jobs, company_ratings, like_escape

logger = logging.getLogger(__name__)

COMPANY_PAGE_JOBS = 10


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _role(user: User | None) -> UserRole | None:
    return UserRole(user.role) if user is not None else None


def _is_staff_for(user: User | None, company_id: uuid.UUID) -> bool:
    """Admins, and recruiters of the owning company, may see non-public jobs/companies."""
    role = _role(user)
    if role == UserRole.ADMIN:
        return True
    return role == UserRole.RECRUITER and user is not None and user.company_id == company_id


def _publicly_live(job: Job, company: Company | None) -> bool:
    if company is None or company.deleted_at is not None or company.status != CompanyStatus.APPROVED:
        return False
    if job.status != JobStatus.ACTIVE:
        return False
    return job.expires_at is None or job.expires_at > _now()


# --------------------------------------------------------------------------- job detail

def get_visible_job(db: Session, job_id: uuid.UUID, user: User | None) -> tuple[Job, Company, bool]:
    """Load a job honouring visibility. Returns (job, company, publicly_live) or raises 404."""
    job = db.get(Job, job_id)
    if job is None or job.deleted_at is not None:
        raise NotFoundError("Job not found")
    company = db.get(Company, job.company_id)
    if company is None or company.deleted_at is not None:
        raise NotFoundError("Job not found")
    live = _publicly_live(job, company)
    if not live and not _is_staff_for(user, job.company_id):
        raise NotFoundError("Job not found")
    return job, company, live


def record_view(db: Session, user: User, job: Job) -> None:
    """One counted view per user/job/day: insert-or-ignore, bump the counter only when inserted."""
    inserted = db.execute(
        pg_insert(JobView)
        .values(id=uuid.uuid4(), job_id=job.id, user_id=user.id, view_date=_now().date())
        .on_conflict_do_nothing(constraint="uq_job_view_user_job_date")
        .returning(JobView.id)
    ).first()
    if inserted is not None:
        job.view_count = db.execute(
            update(Job).where(Job.id == job.id).values(view_count=Job.view_count + 1).returning(Job.view_count)
        ).scalar_one()
    db.commit()


def _question_dict(q: Any) -> dict[str, Any]:
    # expected_answer is deliberately never exposed
    return {
        "id": q.id,
        "text": q.text,
        "type": q.question_type,
        "options": list(q.options or []),
        "isKnockout": q.is_knockout,
        "isRequired": q.is_required,
    }


def job_detail(db: Session, job_id: uuid.UUID, user: User | None) -> dict[str, Any]:
    job, company, live = get_visible_job(db, job_id, user)
    if user is not None and live:
        record_view(db, user, job)

    ratings = company_ratings(db, [company.id])
    avg, review_count = ratings.get(company.id, (None, 0))
    saved = applied = False
    match_score = None
    if user is not None:
        saved = db.scalar(select(func.count()).select_from(SavedJob).where(SavedJob.user_id == user.id, SavedJob.job_id == job.id)) > 0
        applied = db.scalar(select(func.count()).select_from(Application).where(Application.user_id == user.id, Application.job_id == job.id)) > 0
        if _role(user) == UserRole.JOB_SEEKER:
            match_score = matching.match_score(
                list(job.required_skills or []), matching.candidate_skill_names(db, user.id)
            )
    disclosed = not job.hide_salary
    return {
        "id": job.id,
        "title": job.title,
        "description": job.description,
        "responsibilities": job.responsibilities,
        "requiredSkills": list(job.required_skills or []),
        "preferredSkills": list(job.preferred_skills or []),
        "skills": list(job.required_skills or []),
        "experienceMin": job.experience_min,
        "experienceMax": job.experience_max,
        "salaryMin": job.salary_min if disclosed else None,
        "salaryMax": job.salary_max if disclosed else None,
        "salaryDisclosed": disclosed,
        "jobType": job.job_type,
        "employmentType": job.employment_type,
        "workMode": job.work_mode,
        "locations": list(job.locations or []),
        "openings": job.openings,
        "industry": job.industry,
        "department": job.department,
        "functionalArea": job.department,
        "roleCategory": job.role_category,
        "education": job.education,
        "noticePreference": job.notice_preference,
        "isWalkIn": job.is_walk_in,
        "walkInDetails": job.walk_in_details,
        "deadline": job.deadline,
        "status": job.status,
        "postedAt": job.posted_at,
        "expiresAt": job.expires_at,
        "viewCount": job.view_count,
        "applicationCount": job.application_count,
        "screeningQuestions": [_question_dict(q) for q in job.questions],
        "company": {
            "id": company.id,
            "name": company.name,
            "logoUrl": company.logo_url,
            "rating": avg,
            "reviewCount": review_count,
            "industry": company.industry,
            "companyType": company.company_type,
            "verified": company.verified,
        },
        "isApplied": applied,
        "isSaved": saved,
        "matchScore": match_score,
    }


# --------------------------------------------------------------------------- companies

def get_visible_company(db: Session, company_id: uuid.UUID, user: User | None) -> Company:
    company = db.get(Company, company_id)
    if company is None or company.deleted_at is not None:
        raise NotFoundError("Company not found")
    if company.status != CompanyStatus.APPROVED and not _is_staff_for(user, company.id):
        raise NotFoundError("Company not found")
    return company


def company_page(db: Session, company: Company, user: User | None) -> dict[str, Any]:
    avg, review_count = company_ratings(db, [company.id]).get(company.id, (None, 0))
    followers = db.scalar(
        select(func.count()).select_from(CompanyFollow).where(CompanyFollow.company_id == company.id)
    )
    is_following = False
    if user is not None:
        is_following = (
            db.scalar(
                select(func.count())
                .select_from(CompanyFollow)
                .where(CompanyFollow.company_id == company.id, CompanyFollow.user_id == user.id)
            )
            > 0
        )
    jobs, active_total = company_jobs(db, company.id, user, 1, COMPANY_PAGE_JOBS)
    return {
        "id": company.id,
        "name": company.name,
        "logoUrl": company.logo_url,
        "bannerUrl": company.banner_url,
        "website": company.website,
        "industry": company.industry,
        "companyType": company.company_type,
        "sizeRange": company.size_range,
        "foundedYear": company.founded_year,
        "headquarters": company.headquarters,
        "description": company.description,
        "benefits": company.benefits,
        "gallery": list(company.gallery or []),
        "socialLinks": dict(company.social_links or {}),
        "verified": company.verified,
        "rating": avg,
        "reviewCount": review_count,
        "followersCount": followers or 0,
        "activeJobsCount": active_total,
        "isFollowing": is_following,
        "jobs": jobs,
    }


def company_reviews(db: Session, company_id: uuid.UUID, params: PageParams) -> tuple[list[dict[str, Any]], int]:
    stmt = (
        select(CompanyReview)
        .where(CompanyReview.company_id == company_id, CompanyReview.status == ReviewStatus.APPROVED)
        .order_by(CompanyReview.created_at.desc(), CompanyReview.id)
    )
    rows, total = paginate(db, stmt, params)
    items = [
        {
            "id": r.id,
            "rating": r.rating,
            "title": r.title,
            "body": r.body,
            "createdAt": r.created_at,
            "reviewer": "Verified user",
        }
        for r in rows
    ]
    return items, total


# --------------------------------------------------------------------------- master data

def _master_item(type_key: str, row: Any) -> dict[str, Any]:
    item: dict[str, Any] = {"id": row.id, "name": row.name}
    if type_key == "skills":
        item["synonyms"] = list(row.synonyms or [])
    elif type_key == "locations":
        item["state"] = row.state
        item["country"] = row.country
    elif type_key == "degrees":
        item["specializations"] = list(row.specializations or [])
    elif type_key == "notice-periods":
        item["days"] = row.days
    return item


def master_list(
    db: Session, type_key: str, q: str | None, params: PageParams
) -> tuple[list[dict[str, Any]], int]:
    model = MASTER_TYPES.get(type_key)
    if model is None:
        raise NotFoundError(f"Unknown master type '{type_key}'")
    stmt = select(model)
    if model is Skill:
        stmt = stmt.where(Skill.is_active.is_(True))
    needle = (q or "").strip()
    if needle:
        stmt = stmt.where(model.name.ilike(f"%{like_escape(needle)}%", escape="\\"))
    order = [func.lower(model.name), model.name]
    if model is Location:
        order.append(Location.state)
    rows, total = paginate(db, stmt.order_by(*order, model.id), params)
    return [_master_item(type_key, r) for r in rows], total
