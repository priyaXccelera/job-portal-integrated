"""Recruiter-side applicant pipeline: listing/filtering, detail, status changes, notes, rating, interviews.

All list/detail serialisation is batched (constant query count). Nothing here commits - routers do.
"""

from __future__ import annotations

import logging
import uuid
from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import Select, exists, func, or_, select
from sqlalchemy.orm import Session

from app.core.errors import AppError, ConflictError, ForbiddenError, NotFoundError
from app.models.accounts import User
from app.models.applications import Application, ApplicationNote, Interview
from app.models.enums import ApplicationStatus, InterviewMode
from app.models.jobs import Job
from app.models.master import Skill
from app.models.profile import Education, Employment, JobSeekerProfile, ProfileSkill, Resume
from app.schemas.recruiter_jobs import InterviewIn
from app.services import applications as application_service
from app.services.notifications import Category, notify

logger = logging.getLogger(__name__)

S = ApplicationStatus
TOP_SKILLS = 5
EXPORT_CHUNK = 500
EXPORT_MAX_ROWS = 10_000
SCREENING_VALUES = ("in", "out", "all")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _validation(field_name: str, message: str) -> AppError:
    return AppError(422, "VALIDATION_ERROR", "Validation failed", [{"field": field_name, "message": message}])


def split_csv(value: str | None) -> list[str]:
    return [p.strip() for p in (value or "").split(",") if p.strip()]


def _like_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


# --------------------------------------------------------------------------- access


def get_company_application(db: Session, application_id: uuid.UUID, company_id: uuid.UUID) -> tuple[Application, Job]:
    """Application of one of the company's non-deleted jobs (404 unknown, 403 foreign company)."""
    row = db.execute(
        select(Application, Job).join(Job, Job.id == Application.job_id).where(Application.id == application_id)
    ).first()
    if row is None or row[1].deleted_at is not None:
        raise NotFoundError("Application not found")
    application, job = row
    if job.company_id != company_id:
        raise ForbiddenError("This application belongs to another company")
    return application, job


# --------------------------------------------------------------------------- filtering


@dataclass
class ApplicantFilters:
    statuses: list[ApplicationStatus] = field(default_factory=list)
    experience_min: float | None = None
    experience_max: float | None = None
    locations: list[str] = field(default_factory=list)
    ctc_min: Decimal | None = None
    ctc_max: Decimal | None = None
    skills: list[str] = field(default_factory=list)
    notice_periods: list[str] = field(default_factory=list)
    education: list[str] = field(default_factory=list)
    screening: str = "in"
    q: str | None = None
    sort: str = "match"
    order: str = "desc"

    @staticmethod
    def parse_statuses(value: str | None) -> list[ApplicationStatus]:
        out: list[ApplicationStatus] = []
        for part in split_csv(value):
            try:
                status = ApplicationStatus(part.upper())
            except ValueError:
                raise _validation("status", f"Unknown application status '{part}'") from None
            if status not in out:
                out.append(status)
        return out

    def validate(self) -> ApplicantFilters:
        if self.screening not in SCREENING_VALUES:
            raise _validation("screening", "Must be one of in, out, all")
        if self.sort not in ("match", "date"):
            raise _validation("sort", "Must be match or date")
        if self.order not in ("asc", "desc"):
            raise _validation("order", "Must be asc or desc")
        return self


def applicants_stmt(job_id: uuid.UUID, f: ApplicantFilters) -> Select[Any]:
    stmt = (
        select(Application)
        .join(User, User.id == Application.user_id)
        .outerjoin(JobSeekerProfile, JobSeekerProfile.user_id == Application.user_id)
        .where(Application.job_id == job_id, User.deleted_at.is_(None))
    )
    if f.statuses:
        stmt = stmt.where(Application.status.in_(f.statuses))

    total_years = JobSeekerProfile.experience_years + JobSeekerProfile.experience_months / 12.0
    if f.experience_min is not None:
        stmt = stmt.where(total_years >= f.experience_min)
    if f.experience_max is not None:
        stmt = stmt.where(total_years <= f.experience_max)

    if f.locations:
        lowered = [loc.lower() for loc in f.locations]
        preferred = func.lower(func.concat("||", func.array_to_string(JobSeekerProfile.preferred_locations, "||"), "||"))
        stmt = stmt.where(
            or_(
                func.lower(JobSeekerProfile.current_location).in_(lowered),
                *[preferred.like(f"%||{_like_escape(loc)}||%", escape="\\") for loc in lowered],
            )
        )

    expected_ctc = func.coalesce(Application.expected_ctc, JobSeekerProfile.expected_ctc)
    if f.ctc_min is not None:
        stmt = stmt.where(expected_ctc >= f.ctc_min)
    if f.ctc_max is not None:
        stmt = stmt.where(expected_ctc <= f.ctc_max)

    for skill in f.skills:
        stmt = stmt.where(
            exists(
                select(ProfileSkill.id)
                .join(Skill, Skill.id == ProfileSkill.skill_id)
                .where(ProfileSkill.user_id == Application.user_id, func.lower(Skill.name) == skill.lower())
            )
        )

    if f.notice_periods:
        notice = func.lower(func.coalesce(Application.notice_period, JobSeekerProfile.notice_period))
        stmt = stmt.where(notice.in_([n.lower() for n in f.notice_periods]))

    if f.education:
        stmt = stmt.where(
            exists(
                select(Education.id).where(
                    Education.user_id == Application.user_id,
                    func.lower(Education.degree).in_([e.lower() for e in f.education]),
                )
            )
        )

    if f.screening == "in":
        stmt = stmt.where(Application.screened_out.is_(False))
    elif f.screening == "out":
        stmt = stmt.where(Application.screened_out.is_(True))

    if f.q and f.q.strip():
        stmt = stmt.where(User.name.ilike(f"%{_like_escape(f.q.strip())}%", escape="\\"))

    if f.sort == "match":
        primary = Application.match_score.asc() if f.order == "asc" else Application.match_score.desc()
        stmt = stmt.order_by(primary, Application.applied_at.desc(), Application.id)
    else:
        primary = Application.applied_at.asc() if f.order == "asc" else Application.applied_at.desc()
        stmt = stmt.order_by(primary, Application.id)
    return stmt


# --------------------------------------------------------------------------- serialisation


@dataclass
class _CandidateData:
    users: dict[uuid.UUID, User]
    profiles: dict[uuid.UUID, JobSeekerProfile]
    skills: dict[uuid.UUID, list[tuple[str, Decimal | None]]]
    education: dict[uuid.UUID, list[Education]]


def _load_candidates(db: Session, user_ids: Iterable[uuid.UUID]) -> _CandidateData:
    ids = list(set(user_ids))
    users = {u.id: u for u in db.scalars(select(User).where(User.id.in_(ids)))} if ids else {}
    profiles = (
        {p.user_id: p for p in db.scalars(select(JobSeekerProfile).where(JobSeekerProfile.user_id.in_(ids)))}
        if ids
        else {}
    )
    skills: dict[uuid.UUID, list[tuple[str, Decimal | None]]] = defaultdict(list)
    education: dict[uuid.UUID, list[Education]] = defaultdict(list)
    if ids:
        for user_id, name, years in db.execute(
            select(ProfileSkill.user_id, Skill.name, ProfileSkill.years_of_experience)
            .join(Skill, Skill.id == ProfileSkill.skill_id)
            .where(ProfileSkill.user_id.in_(ids))
            .order_by(ProfileSkill.years_of_experience.desc().nulls_last(), Skill.name)
        ):
            skills[user_id].append((name, years))
        for edu in db.scalars(
            select(Education)
            .where(Education.user_id.in_(ids))
            .order_by(Education.end_year.desc().nulls_last(), Education.start_year.desc().nulls_last())
        ):
            education[edu.user_id].append(edu)
    return _CandidateData(users, profiles, skills, education)


def _education_summary(items: Sequence[Education]) -> dict[str, Any] | None:
    if not items:
        return None
    top = items[0]
    return {
        "degree": top.degree,
        "specialization": top.specialization,
        "institute": top.institute,
        "endYear": top.end_year,
    }


def _candidate_dict(user_id: uuid.UUID, data: _CandidateData) -> dict[str, Any]:
    user = data.users.get(user_id)
    profile = data.profiles.get(user_id)
    return {
        "id": user_id,
        "name": user.name if user else None,
        "email": user.email if user else None,
        "mobile": user.mobile if user else None,
        "headline": profile.headline if profile else None,
        "experienceYears": profile.experience_years if profile else 0,
        "experienceMonths": profile.experience_months if profile else 0,
        "currentLocation": profile.current_location if profile else None,
        "skills": [name for name, _ in data.skills.get(user_id, [])[:TOP_SKILLS]],
        "education": _education_summary(data.education.get(user_id, [])),
        "photoUrl": profile.photo_url if profile else None,
    }


def serialize_applicants(db: Session, apps: Sequence[Application]) -> list[dict[str, Any]]:
    if not apps:
        return []
    data = _load_candidates(db, [a.user_id for a in apps])
    return [
        {
            "applicationId": a.id,
            "status": a.status,
            "appliedAt": a.applied_at,
            "matchScore": a.match_score,
            "screenedOut": a.screened_out,
            "screenReason": a.screen_reason,
            "rating": a.rating,
            "expectedCtc": a.expected_ctc,
            "noticePeriod": a.notice_period,
            "candidate": _candidate_dict(a.user_id, data),
            "resumeId": a.resume_id,
        }
        for a in apps
    ]


CSV_HEADER = [
    "Application ID",
    "Name",
    "Email",
    "Mobile",
    "Status",
    "Applied At",
    "Match Score",
    "Experience (years)",
    "Current Location",
    "Expected CTC",
    "Notice Period",
    "Screened Out",
    "Screen Reason",
    "Rating",
    "Skills",
    "Education",
]


def export_rows(db: Session, stmt: Select[Any]) -> list[list[Any]]:
    """CSV rows for every matching applicant (chunked, batch-loaded, capped)."""
    rows: list[list[Any]] = []
    offset = 0
    while offset < EXPORT_MAX_ROWS:
        chunk = list(db.scalars(stmt.limit(EXPORT_CHUNK).offset(offset)))
        if not chunk:
            break
        data = _load_candidates(db, [a.user_id for a in chunk])
        for a in chunk:
            cand = _candidate_dict(a.user_id, data)
            edu = cand["education"]
            rows.append(
                [
                    str(a.id),
                    cand["name"],
                    cand["email"],
                    cand["mobile"],
                    a.status.value if isinstance(a.status, ApplicationStatus) else a.status,
                    a.applied_at,
                    a.match_score,
                    round(cand["experienceYears"] + cand["experienceMonths"] / 12, 1),
                    cand["currentLocation"],
                    a.expected_ctc,
                    a.notice_period,
                    a.screened_out,
                    a.screen_reason,
                    a.rating,
                    [name for name, _ in data.skills.get(a.user_id, [])],
                    ", ".join(p for p in (edu["degree"], edu["specialization"]) if p) if edu else "",
                ]
            )
        if len(chunk) < EXPORT_CHUNK:
            break
        offset += EXPORT_CHUNK
    return rows


# --------------------------------------------------------------------------- detail


def _note_dicts(db: Session, notes: Sequence[ApplicationNote]) -> list[dict[str, Any]]:
    author_ids = {n.author_id for n in notes if n.author_id}
    names = (
        {uid: name for uid, name in db.execute(select(User.id, User.name).where(User.id.in_(author_ids)))}
        if author_ids
        else {}
    )
    return [
        {
            "id": n.id,
            "applicationId": n.application_id,
            "note": n.note,
            "authorId": n.author_id,
            "authorName": names.get(n.author_id),
            "createdAt": n.created_at,
        }
        for n in notes
    ]


def _interview_dicts(db: Session, application_id: uuid.UUID) -> list[dict[str, Any]]:
    interviews = db.scalars(
        select(Interview).where(Interview.application_id == application_id).order_by(Interview.created_at.desc())
    )
    return [
        {
            "id": i.id,
            "scheduledAt": i.scheduled_at,
            "dateTime": i.scheduled_at,
            "mode": i.mode,
            "locationOrLink": i.location_or_link,
            "notes": i.notes,
            "candidateResponse": i.candidate_response,
            "responseNote": i.response_note,
            "createdAt": i.created_at,
        }
        for i in interviews
    ]


def mark_viewed(db: Session, application: Application, actor: User) -> bool:
    """APPLIED -> VIEWED (notifies the candidate). Any other status is left untouched."""
    if ApplicationStatus(application.status) != S.APPLIED:
        return False
    application_service.change_status(db, application, S.VIEWED, actor=actor)
    return True


def application_detail(db: Session, application: Application) -> dict[str, Any]:
    base = application_service.serialize_application(db, application, view="recruiter")
    data = _load_candidates(db, [application.user_id])
    candidate = _candidate_dict(application.user_id, data)
    profile = data.profiles.get(application.user_id)
    candidate["skills"] = [{"name": n, "yearsOfExperience": y} for n, y in data.skills.get(application.user_id, [])]
    candidate["education"] = [
        {
            "degree": e.degree,
            "specialization": e.specialization,
            "institute": e.institute,
            "startYear": e.start_year,
            "endYear": e.end_year,
            "grade": e.grade,
        }
        for e in data.education.get(application.user_id, [])
    ]
    employments = db.scalars(
        select(Employment)
        .where(Employment.user_id == application.user_id)
        .order_by(Employment.is_current.desc(), Employment.start_date.desc().nulls_last())
        .limit(10)
    )
    candidate["employment"] = [
        {
            "companyName": e.company_name,
            "designation": e.designation,
            "startDate": e.start_date,
            "endDate": e.end_date,
            "isCurrent": e.is_current,
        }
        for e in employments
    ]
    if profile is not None:
        candidate.update(
            {
                "summary": profile.summary,
                "preferredLocations": list(profile.preferred_locations or []),
                "currentCtc": profile.current_ctc,
                "profileExpectedCtc": profile.expected_ctc,
                "profileNoticePeriod": profile.notice_period,
                "workStatus": profile.work_status,
                "languages": profile.languages,
                "onlineProfiles": profile.online_profiles,
            }
        )
    resume = db.get(Resume, application.resume_id) if application.resume_id else None
    notes = db.scalars(
        select(ApplicationNote)
        .where(ApplicationNote.application_id == application.id)
        .order_by(ApplicationNote.created_at.desc())
    ).all()
    base.update(
        {
            "candidate": candidate,
            "notes": _note_dicts(db, notes),
            "interviews": _interview_dicts(db, application.id),
            "screening": {"screenedOut": application.screened_out, "reason": application.screen_reason},
            "resume": (
                {
                    "id": resume.id,
                    "fileName": resume.file_name,
                    "contentType": resume.content_type,
                    "sizeBytes": resume.size_bytes,
                    "downloadUrl": f"/api/v1/recruiter/applications/{application.id}/resume",
                }
                if resume is not None
                else None
            ),
        }
    )
    return base


# --------------------------------------------------------------------------- status changes


def change_status_as_recruiter(
    db: Session, application: Application, status: ApplicationStatus, actor: User, message: str | None
) -> Application:
    if ApplicationStatus(status) == S.WITHDRAWN:
        raise ConflictError("Only the candidate can withdraw an application", code="INVALID_TRANSITION")
    return application_service.change_status(db, application, status, actor=actor, message=message)


def bulk_change_status(
    db: Session,
    company_id: uuid.UUID,
    actor: User,
    application_ids: Sequence[uuid.UUID],
    status: ApplicationStatus,
    message: str | None,
) -> dict[str, Any]:
    """Apply a transition to many applications; each one is validated individually."""
    unique_ids = list(dict.fromkeys(application_ids))
    rows = {
        app.id: (app, job)
        for app, job in db.execute(
            select(Application, Job).join(Job, Job.id == Application.job_id).where(Application.id.in_(unique_ids))
        )
    }
    updated: list[uuid.UUID] = []
    failed: list[dict[str, Any]] = []
    for app_id in unique_ids:
        row = rows.get(app_id)
        if row is None or row[1].deleted_at is not None:
            failed.append({"id": app_id, "code": "NOT_FOUND", "message": "Application not found"})
            continue
        application, job = row
        if job.company_id != company_id:
            failed.append({"id": app_id, "code": "FORBIDDEN", "message": "Application belongs to another company"})
            continue
        try:
            change_status_as_recruiter(db, application, status, actor, message)
        except AppError as exc:
            failed.append({"id": app_id, "code": exc.code, "message": exc.message})
            continue
        updated.append(app_id)
    return {"updated": updated, "failed": failed}


# --------------------------------------------------------------------------- notes / rating


def add_note(db: Session, application: Application, author: User, text: str) -> dict[str, Any]:
    note = ApplicationNote(id=uuid.uuid4(), application_id=application.id, author_id=author.id, note=text)
    db.add(note)
    db.flush()
    return _note_dicts(db, [note])[0]


def notes_stmt(application_id: uuid.UUID) -> Select[Any]:
    return (
        select(ApplicationNote)
        .where(ApplicationNote.application_id == application_id)
        .order_by(ApplicationNote.created_at.desc(), ApplicationNote.id)
    )


def serialize_notes(db: Session, notes: Sequence[ApplicationNote]) -> list[dict[str, Any]]:
    return _note_dicts(db, notes)


def set_rating(application: Application, rating: int) -> Application:
    application.rating = rating
    application.updated_at = _now()
    return application


# --------------------------------------------------------------------------- interviews

_MODE_LABEL = {InterviewMode.VIDEO: "Video call", InterviewMode.PHONE: "Phone call", InterviewMode.IN_PERSON: "In person"}


def schedule_interview(db: Session, application: Application, job: Job, actor: User, data: InterviewIn) -> Interview:
    """Create an interview and move the application to INTERVIEW_SCHEDULED (chaining via SHORTLISTED)."""
    current = ApplicationStatus(application.status)
    when = data.date_time.astimezone(timezone.utc)
    message = f"Interview scheduled for {when.strftime('%Y-%m-%d %H:%M')} UTC ({data.mode.value})"
    if current in (S.APPLIED, S.VIEWED):
        application_service.change_status(db, application, S.SHORTLISTED, actor=actor, notify_candidate=False)
        current = S.SHORTLISTED
    if current == S.SHORTLISTED:
        application_service.change_status(
            db, application, S.INTERVIEW_SCHEDULED, actor=actor, message=message, notify_candidate=False
        )
    elif current != S.INTERVIEW_SCHEDULED:
        raise ConflictError(
            f"Cannot schedule an interview for an application in {current.value} status", code="INVALID_TRANSITION"
        )

    interview = Interview(
        id=uuid.uuid4(),
        application_id=application.id,
        scheduled_at=when,
        mode=data.mode,
        location_or_link=data.location_or_link,
        notes=data.notes,
        created_by=actor.id,
    )
    db.add(interview)
    db.flush()

    where_label = "Meeting link" if data.mode == InterviewMode.VIDEO else (
        "Phone" if data.mode == InterviewMode.PHONE else "Address"
    )
    body = (
        f"An interview has been scheduled for your application to {job.title}.\n\n"
        f"Date & time: {when.strftime('%A, %d %B %Y %H:%M')} UTC\n"
        f"Mode: {_MODE_LABEL[data.mode]}\n"
        f"{where_label}: {data.location_or_link}"
    )
    if data.notes:
        body += f"\nNotes: {data.notes}"
    notify(
        db,
        application.user_id,
        Category.INTERVIEW_SCHEDULED,
        f"Interview scheduled: {job.title}",
        body,
        data={
            "applicationId": str(application.id),
            "jobId": str(job.id),
            "interviewId": str(interview.id),
            "scheduledAt": when.isoformat(),
            "mode": data.mode.value,
            "locationOrLink": data.location_or_link,
        },
    )
    return interview


def interview_dict(interview: Interview, application: Application) -> dict[str, Any]:
    return {
        "id": interview.id,
        "applicationId": application.id,
        "applicationStatus": application.status,
        "dateTime": interview.scheduled_at,
        "scheduledAt": interview.scheduled_at,
        "mode": interview.mode,
        "locationOrLink": interview.location_or_link,
        "notes": interview.notes,
        "candidateResponse": interview.candidate_response,
        "createdAt": interview.created_at,
    }


__all__ = [
    "ApplicantFilters",
    "CSV_HEADER",
    "add_note",
    "application_detail",
    "applicants_stmt",
    "bulk_change_status",
    "change_status_as_recruiter",
    "export_rows",
    "get_company_application",
    "interview_dict",
    "mark_viewed",
    "notes_stmt",
    "schedule_interview",
    "serialize_applicants",
    "serialize_notes",
    "set_rating",
    "split_csv",
]
