"""Recruiter-side candidate actions: detail view, profile-view tracking, unlock, invite and folders."""

from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy import Select, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.deps import RecruiterContext
from app.core.errors import BadRequestError, ConflictError, ForbiddenError, NotFoundError
from app.core.responses import PageParams, paginate
from app.config import settings
from app.db import utcnow
from app.models.accounts import User
from app.models.applications import Application
from app.models.company import (
    CandidateFolder,
    CandidateInvite,
    Company,
    FolderCandidate,
)
from app.models.enums import CompanyStatus, JobStatus
from app.models.jobs import Job
from app.models.master import Skill
from app.models.profile import (
    Certification,
    Education,
    Employment,
    JobSeekerProfile,
    Project,
    ProfileSkill,
    ProfileView,
)
from app.services import candidate_search, credits, profile_service
from app.services.notifications import Category, notify

logger = logging.getLogger(__name__)


# ======================================================================================= guards


def require_approved(company: Company) -> None:
    if company.status != CompanyStatus.APPROVED:
        raise ForbiddenError(
            "Your company must be approved before you can use the candidate database",
            code="COMPANY_NOT_APPROVED",
        )


def get_visible_candidate(
    db: Session, company: Company, candidate_id: uuid.UUID
) -> tuple[User, JobSeekerProfile]:
    """Load a candidate honouring profile visibility; 404 when not visible to this company."""
    row = db.execute(
        candidate_search.visible_candidates_stmt(company.id).where(User.id == candidate_id)
    ).first()
    if row is None:
        raise NotFoundError("Candidate not found")
    return row[0], row[1]


# ======================================================================================= detail


def record_profile_view(db: Session, ctx: RecruiterContext, candidate_id: uuid.UUID) -> bool:
    """Record a profile view (once per recruiter+candidate per day); notify once per company per day.

    Returns True when a new view row was written. Does not commit.
    """
    now = utcnow()
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    # serialise concurrent views of the same recruiter/candidate pair so the dedupe is race-free
    lock_key = f"profile-view:{ctx.user.id}:{candidate_id}"
    db.execute(select(func.pg_advisory_xact_lock(func.hashtextextended(lock_key, 0))))
    already_viewed = db.scalar(
        select(ProfileView.id)
        .where(
            ProfileView.candidate_id == candidate_id,
            ProfileView.recruiter_id == ctx.user.id,
            ProfileView.viewed_at >= day_start,
        )
        .limit(1)
    )
    if already_viewed is not None:
        return False
    company_seen_today = db.scalar(
        select(ProfileView.id)
        .where(
            ProfileView.candidate_id == candidate_id,
            ProfileView.company_id == ctx.company.id,
            ProfileView.viewed_at >= day_start,
        )
        .limit(1)
    )
    db.add(
        ProfileView(
            id=uuid.uuid4(),
            candidate_id=candidate_id,
            recruiter_id=ctx.user.id,
            company_id=ctx.company.id,
            viewed_at=now,
        )
    )
    db.flush()
    if company_seen_today is None:
        notify(
            db,
            candidate_id,
            Category.PROFILE_VIEWED,
            "Your profile was viewed",
            f"{ctx.company.name} viewed your profile.",
            email=False,
            data={"companyId": ctx.company.id, "companyName": ctx.company.name},
        )
    return True


def candidate_detail(
    db: Session, company: Company, user: User, profile: JobSeekerProfile
) -> dict[str, Any]:
    """Full candidate profile; contact details and photo only when the company unlocked them."""
    detail = candidate_search.serialize_candidates(db, company, [(user, profile)])[0]
    unlocked = bool(detail["isUnlocked"])
    skills = db.execute(
        select(ProfileSkill, Skill.name)
        .join(Skill, Skill.id == ProfileSkill.skill_id)
        .where(ProfileSkill.user_id == user.id)
        .order_by(ProfileSkill.years_of_experience.desc().nulls_last(), func.lower(Skill.name))
    ).all()
    employments = db.scalars(
        select(Employment)
        .where(Employment.user_id == user.id)
        .order_by(Employment.is_current.desc(), Employment.start_date.desc().nulls_last())
    ).all()
    educations = db.scalars(
        select(Education)
        .where(Education.user_id == user.id)
        .order_by(Education.end_year.desc().nulls_last())
    ).all()
    projects = db.scalars(select(Project).where(Project.user_id == user.id).order_by(Project.start_date.desc().nulls_last())).all()
    certifications = db.scalars(
        select(Certification).where(Certification.user_id == user.id).order_by(Certification.issued_date.desc().nulls_last())
    ).all()
    detail.update(
        {
            "summary": profile.summary,
            "currentCtc": profile.current_ctc,
            "workStatus": profile.work_status,
            "activelyLooking": bool(profile.actively_looking),
            "preferredLocations": list(profile.preferred_locations or []),
            "skills": [profile_service.serialize_skill(ps, name) for ps, name in skills],
            "employments": [profile_service.serialize_employment(e) for e in employments],
            "educations": [profile_service.serialize_education(e) for e in educations],
            "projects": [profile_service.serialize_project(p) for p in projects],
            "certifications": [profile_service.serialize_certification(c) for c in certifications],
            "languages": list(profile.languages or []),
            "careerPreferences": profile_service.career_preferences_dict(profile),
        }
    )
    if unlocked:
        detail["onlineProfiles"] = profile_service.online_profiles_dict(profile)
    return detail


def unlock_candidate(db: Session, ctx: RecruiterContext, candidate_id: uuid.UUID) -> dict[str, Any]:
    """Unlock a visible candidate (charged once); caller commits."""
    require_approved(ctx.company)
    user, profile = get_visible_candidate(db, ctx.company, candidate_id)
    _, charged = credits.unlock_contact(db, ctx.company, candidate_id, ctx.user)
    detail = candidate_detail(db, ctx.company, user, profile)
    return {"candidate": detail, "charged": charged, "balance": ctx.company.credits}


# ======================================================================================= invite


def serialize_invite(invite: CandidateInvite) -> dict[str, Any]:
    return {
        "id": invite.id,
        "candidateId": invite.candidate_id,
        "jobId": invite.job_id,
        "message": invite.message,
        "createdAt": invite.created_at,
    }


def invite_candidate(
    db: Session, ctx: RecruiterContext, candidate_id: uuid.UUID, job_id: uuid.UUID, message: str | None
) -> dict[str, Any]:
    """Invite a visible candidate to apply for an active job of this company; caller commits."""
    company = ctx.company
    require_approved(company)
    candidate, _ = get_visible_candidate(db, company, candidate_id)
    job = db.get(Job, job_id)
    if job is None or job.company_id != company.id or job.deleted_at is not None:
        raise NotFoundError("Job not found")
    if job.status != JobStatus.ACTIVE:
        raise BadRequestError("Candidates can only be invited to ACTIVE jobs")

    credits.lock_company(db, company)  # serialises the duplicate check + charge per company
    duplicate = db.scalar(
        select(CandidateInvite.id).where(
            CandidateInvite.company_id == company.id,
            CandidateInvite.candidate_id == candidate_id,
            CandidateInvite.job_id == job_id,
        )
    )
    if duplicate is not None:
        raise ConflictError("This candidate has already been invited to this job")
    already_applied = db.scalar(
        select(Application.id).where(Application.job_id == job_id, Application.user_id == candidate_id)
    )
    if already_applied is not None:
        raise ConflictError("This candidate has already applied to this job")

    cost = settings.invite_credit_cost
    if cost > 0:
        credits.spend(db, company, cost, "Invite to apply", ctx.user.id, "JOB", job_id)
    invite = CandidateInvite(
        id=uuid.uuid4(),
        company_id=company.id,
        candidate_id=candidate_id,
        job_id=job_id,
        recruiter_id=ctx.user.id,
        message=message,
        created_at=utcnow(),
    )
    db.add(invite)
    db.flush()
    body = f"{company.name} invited you to apply for {job.title}."
    if message:
        body += f"\n\n{message}"
    notify(
        db,
        candidate.id,
        Category.SYSTEM,
        f"Invitation to apply: {job.title}",
        body,
        email=True,
        data={"jobId": job.id, "companyId": company.id, "type": "CANDIDATE_INVITE"},
    )
    result = serialize_invite(invite)
    result["jobTitle"] = job.title
    result["balance"] = company.credits
    return result


# ======================================================================================= folders


def serialize_folder(folder: CandidateFolder, candidate_count: int) -> dict[str, Any]:
    return {
        "id": folder.id,
        "name": folder.name,
        "candidateCount": candidate_count,
        "createdBy": folder.created_by,
        "createdAt": folder.created_at,
    }


def folders_stmt(company_id: uuid.UUID) -> Select[Any]:
    return (
        select(CandidateFolder, func.count(FolderCandidate.id))
        .outerjoin(FolderCandidate, FolderCandidate.folder_id == CandidateFolder.id)
        .where(CandidateFolder.company_id == company_id)
        .group_by(CandidateFolder.id)
        .order_by(func.lower(CandidateFolder.name), CandidateFolder.id)
    )


def get_folder(db: Session, company: Company, folder_id: uuid.UUID) -> CandidateFolder:
    folder = db.get(CandidateFolder, folder_id)
    if folder is None or folder.company_id != company.id:
        raise NotFoundError("Folder not found")
    return folder


def _assert_unique_folder_name(
    db: Session, company_id: uuid.UUID, name: str, exclude_id: uuid.UUID | None = None
) -> None:
    stmt = select(CandidateFolder.id).where(
        CandidateFolder.company_id == company_id, func.lower(CandidateFolder.name) == name.lower()
    )
    if exclude_id is not None:
        stmt = stmt.where(CandidateFolder.id != exclude_id)
    if db.scalar(stmt.limit(1)) is not None:
        raise ConflictError("A folder with this name already exists")


def create_folder(db: Session, ctx: RecruiterContext, name: str) -> dict[str, Any]:
    _assert_unique_folder_name(db, ctx.company.id, name)
    folder = CandidateFolder(
        id=uuid.uuid4(), company_id=ctx.company.id, name=name, created_by=ctx.user.id, created_at=utcnow()
    )
    db.add(folder)
    db.flush()
    return serialize_folder(folder, 0)


def rename_folder(db: Session, ctx: RecruiterContext, folder_id: uuid.UUID, name: str) -> dict[str, Any]:
    folder = get_folder(db, ctx.company, folder_id)
    _assert_unique_folder_name(db, ctx.company.id, name, exclude_id=folder.id)
    folder.name = name
    db.flush()
    count = db.scalar(select(func.count()).select_from(FolderCandidate).where(FolderCandidate.folder_id == folder.id))
    return serialize_folder(folder, count or 0)


def delete_folder(db: Session, ctx: RecruiterContext, folder_id: uuid.UUID) -> None:
    folder = get_folder(db, ctx.company, folder_id)
    db.delete(folder)  # folder_candidates cascade at the DB level
    db.flush()


def folder_candidates(
    db: Session, ctx: RecruiterContext, folder_id: uuid.UUID, params: PageParams
) -> tuple[list[dict[str, Any]], int]:
    require_approved(ctx.company)
    folder = get_folder(db, ctx.company, folder_id)
    stmt = (
        select(User, JobSeekerProfile, FolderCandidate)
        .select_from(FolderCandidate)
        .join(User, User.id == FolderCandidate.candidate_id)
        .join(JobSeekerProfile, JobSeekerProfile.user_id == User.id)
        .where(FolderCandidate.folder_id == folder.id, *candidate_search.visibility_conditions(ctx.company.id))
        .order_by(FolderCandidate.created_at.desc(), FolderCandidate.id)
    )
    rows, total = paginate(db, stmt, params)
    items = candidate_search.serialize_candidates(db, ctx.company, [(r[0], r[1]) for r in rows])
    for item, row in zip(items, rows, strict=True):
        item["note"] = row[2].note
        item["addedAt"] = row[2].created_at
    return items, total


def add_folder_candidate(
    db: Session, ctx: RecruiterContext, folder_id: uuid.UUID, candidate_id: uuid.UUID, note: str | None
) -> dict[str, Any]:
    require_approved(ctx.company)
    folder = get_folder(db, ctx.company, folder_id)
    user, profile = get_visible_candidate(db, ctx.company, candidate_id)
    exists_row = db.scalar(
        select(FolderCandidate.id).where(
            FolderCandidate.folder_id == folder.id, FolderCandidate.candidate_id == candidate_id
        )
    )
    if exists_row is not None:
        raise ConflictError("Candidate is already in this folder")
    entry = FolderCandidate(
        id=uuid.uuid4(), folder_id=folder.id, candidate_id=candidate_id, note=note, created_at=utcnow()
    )
    db.add(entry)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise ConflictError("Candidate is already in this folder") from exc
    item = candidate_search.serialize_candidates(db, ctx.company, [(user, profile)])[0]
    item["note"] = entry.note
    item["addedAt"] = entry.created_at
    item["folderId"] = folder.id
    return item


def remove_folder_candidate(
    db: Session, ctx: RecruiterContext, folder_id: uuid.UUID, candidate_id: uuid.UUID
) -> None:
    folder = get_folder(db, ctx.company, folder_id)
    entry = db.scalar(
        select(FolderCandidate).where(
            FolderCandidate.folder_id == folder.id, FolderCandidate.candidate_id == candidate_id
        )
    )
    if entry is None:
        raise NotFoundError("Candidate is not in this folder")
    db.delete(entry)
    db.flush()
