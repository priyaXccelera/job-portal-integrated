"""Application lifecycle: apply, screening, status state machine and serialization."""

from __future__ import annotations

import json
import logging
import uuid
from collections.abc import Iterable, Sequence
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import AppError, BadRequestError, ConflictError, NotFoundError
from app.models.accounts import User
from app.models.applications import Application, ApplicationAnswer, Interview, StatusHistory
from app.models.company import Company
from app.models.enums import ApplicationStatus, JobStatus, QuestionType
from app.models.jobs import Job, ScreeningQuestion
from app.models.profile import Resume
from app.services.matching import candidate_skill_names, match_score
from app.services.notifications import Category, notify

logger = logging.getLogger(__name__)

S = ApplicationStatus

ALLOWED_TRANSITIONS: dict[ApplicationStatus, set[ApplicationStatus]] = {
    S.APPLIED: {S.VIEWED, S.SHORTLISTED, S.REJECTED, S.WITHDRAWN},
    S.VIEWED: {S.SHORTLISTED, S.REJECTED, S.WITHDRAWN},
    S.SHORTLISTED: {S.INTERVIEW_SCHEDULED, S.OFFERED, S.REJECTED, S.WITHDRAWN},
    S.INTERVIEW_SCHEDULED: {S.SHORTLISTED, S.OFFERED, S.REJECTED, S.WITHDRAWN},
    S.OFFERED: {S.HIRED, S.REJECTED, S.WITHDRAWN},
    S.HIRED: set(),
    S.REJECTED: set(),
    S.WITHDRAWN: set(),
}

_STATUS_CATEGORY: dict[ApplicationStatus, Category] = {
    S.VIEWED: Category.APPLICATION_VIEWED,
    S.SHORTLISTED: Category.APPLICATION_SHORTLISTED,
    S.INTERVIEW_SCHEDULED: Category.INTERVIEW_SCHEDULED,
}

_YES = {"yes", "y", "true"}
_NO = {"no", "n", "false"}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _validation_error(message: str, details: list[dict[str, Any]]) -> AppError:
    return AppError(422, "VALIDATION_ERROR", message, details)


# --------------------------------------------------------------------------- screening


def _accepted_options(expected: str | None) -> list[str]:
    """Parse the accepted options of a MULTIPLE_CHOICE knockout question."""
    if expected is None or not expected.strip():
        return []
    raw = expected.strip()
    try:
        parsed = json.loads(raw)
    except ValueError:
        parsed = None
    if isinstance(parsed, list):
        return [str(p).strip().lower() for p in parsed if str(p).strip()]
    if isinstance(parsed, str):
        return [parsed.strip().lower()] if parsed.strip() else []
    return [part.strip().lower() for part in raw.split(",") if part.strip()]


def _passes_knockout(question: ScreeningQuestion, answer: str | None) -> bool:
    text = (answer or "").strip()
    if not text:
        return False  # a missing answer to a knockout question is a failure
    qtype = QuestionType(question.question_type)
    if qtype == QuestionType.TEXT:
        return True
    expected = (question.expected_answer or "").strip()
    if qtype == QuestionType.YES_NO:
        if not expected:
            return True
        norm = text.lower()
        norm = "yes" if norm in _YES else "no" if norm in _NO else norm
        return norm == expected.lower()
    accepted = _accepted_options(question.expected_answer)
    return True if not accepted else text.lower() in accepted


def screen_answers(
    questions: Sequence[ScreeningQuestion], answers: Iterable[dict[str, Any]]
) -> tuple[bool, str | None]:
    """Evaluate knockout questions only. Returns ``(screened_out, reason)``."""
    by_question = {str(a.get("questionId")): a.get("answer") for a in answers}
    for question in questions:
        if not question.is_knockout:
            continue
        if not _passes_knockout(question, by_question.get(str(question.id))):
            return True, f"Failed knockout question: {question.text}"
    return False, None


def _validate_answers(questions: Sequence[ScreeningQuestion], answers: list[dict[str, Any]]) -> None:
    """Raise 422 for unknown question ids, invalid choices or unanswered required questions."""
    known = {str(q.id): q for q in questions}
    details: list[dict[str, Any]] = []
    given: dict[str, str] = {}
    for idx, item in enumerate(answers):
        qid = str(item.get("questionId"))
        if qid not in known:
            details.append({"field": f"answers.{idx}.questionId", "message": "Unknown screening question"})
            continue
        given[qid] = (item.get("answer") or "").strip()
    for qid, answer in given.items():
        question = known[qid]
        if not answer:
            continue
        qtype = QuestionType(question.question_type)
        if qtype == QuestionType.YES_NO and answer.lower() not in _YES | _NO:
            details.append({"field": f"answers.{qid}", "message": "Answer must be YES or NO"})
        elif qtype == QuestionType.MULTIPLE_CHOICE and question.options:
            if answer.lower() not in {o.strip().lower() for o in question.options}:
                details.append({"field": f"answers.{qid}", "message": "Answer must be one of the listed options"})
    for question in questions:
        if question.is_required and not given.get(str(question.id)):
            details.append({"field": f"answers.{question.id}", "message": f"Answer required: {question.text}"})
    if details:
        raise _validation_error("Screening questions are not answered correctly", details)


# --------------------------------------------------------------------------- apply


def _job_open_or_raise(job: Job) -> None:
    now = _now()
    if job.deleted_at is not None or JobStatus(job.status) != JobStatus.ACTIVE:
        raise BadRequestError("This job is no longer accepting applications", code="JOB_CLOSED")
    if job.expires_at is not None and job.expires_at <= now:
        raise BadRequestError("This job has expired", code="JOB_CLOSED")
    if job.deadline is not None and job.deadline < now.date():
        raise BadRequestError("The application deadline for this job has passed", code="JOB_CLOSED")


def apply_to_job(
    db: Session,
    user: User,
    job: Job,
    *,
    resume_id: uuid.UUID | None,
    cover_note: str | None,
    answers: list[dict[str, Any]],
    expected_ctc: Decimal | None,
    notice_period: str | None,
) -> Application:
    """Create an application. Does not commit (caller commits)."""
    _job_open_or_raise(job)

    existing = db.scalar(
        select(Application.id).where(Application.job_id == job.id, Application.user_id == user.id)
    )
    if existing is not None:
        raise ConflictError("You have already applied to this job", code="DUPLICATE_APPLICATION")

    if resume_id is not None:
        resume = db.scalar(select(Resume).where(Resume.id == resume_id, Resume.user_id == user.id))
        if resume is None:
            raise NotFoundError("Resume not found")
    else:
        resume = db.scalar(
            select(Resume)
            .where(Resume.user_id == user.id, Resume.is_default.is_(True))
            .order_by(Resume.created_at.desc())
            .limit(1)
        )

    questions = list(job.questions)
    _validate_answers(questions, answers)
    screened_out, reason = screen_answers(questions, answers)

    score = match_score(list(job.required_skills or []), candidate_skill_names(db, user.id))
    now = _now()
    application = Application(
        id=uuid.uuid4(),
        job_id=job.id,
        user_id=user.id,
        resume_id=resume.id if resume is not None else None,
        cover_note=cover_note,
        expected_ctc=expected_ctc,
        notice_period=notice_period,
        status=S.APPLIED,
        screened_out=screened_out,
        screen_reason=reason,
        match_score=int(score["percentage"]),
        applied_at=now,
        updated_at=now,
    )
    try:
        with db.begin_nested():
            db.add(application)
            db.flush()
    except IntegrityError as exc:  # uq_application_job_user lost a race
        raise ConflictError("You have already applied to this job", code="DUPLICATE_APPLICATION") from exc

    seen: set[str] = set()
    for item in answers:
        qid = str(item["questionId"])
        if qid in seen:
            continue
        seen.add(qid)
        db.add(
            ApplicationAnswer(
                id=uuid.uuid4(),
                application_id=application.id,
                question_id=uuid.UUID(qid),
                answer=(item.get("answer") or "").strip() or None,
            )
        )
    db.add(
        StatusHistory(
            id=uuid.uuid4(),
            application_id=application.id,
            status=S.APPLIED,
            message="Application submitted",
            changed_by=user.id,
            created_at=now,
        )
    )
    db.execute(
        update(Job)
        .where(Job.id == job.id)
        .values(application_count=Job.application_count + 1)
        .execution_options(synchronize_session=False)
    )
    db.expire(job, ["application_count"])

    if job.posted_by is not None:
        notify(
            db,
            job.posted_by,
            Category.NEW_APPLICANT,
            f"New applicant for {job.title}",
            f"{user.name} applied to {job.title}.",
            email=not screened_out,
            data={"applicationId": str(application.id), "jobId": str(job.id), "candidateId": str(user.id)},
        )
    db.flush()
    return application


# --------------------------------------------------------------------------- state machine


def change_status(
    db: Session,
    application: Application,
    new_status: ApplicationStatus,
    actor: User,
    message: str | None = None,
    notify_candidate: bool = True,
) -> Application:
    """Validate and apply a status transition; never commits."""
    current = ApplicationStatus(application.status)
    new_status = ApplicationStatus(new_status)
    allowed = ALLOWED_TRANSITIONS.get(current, set())
    if new_status not in allowed:
        listing = ", ".join(sorted(s.value for s in allowed)) or "none (terminal status)"
        raise ConflictError(
            f"Cannot move application from {current.value} to {new_status.value}. Allowed: {listing}",
            code="INVALID_TRANSITION",
        )

    now = _now()
    application.status = new_status
    application.updated_at = now
    if new_status == S.VIEWED and application.viewed_at is None:
        application.viewed_at = now
    db.add(
        StatusHistory(
            id=uuid.uuid4(),
            application_id=application.id,
            status=new_status,
            message=message,
            changed_by=actor.id,
            created_at=now,
        )
    )
    if new_status == S.WITHDRAWN:
        db.execute(
            update(Job)
            .where(Job.id == application.job_id)
            .values(application_count=func.greatest(Job.application_count - 1, 0))
            .execution_options(synchronize_session=False)
        )
        job_obj = db.get(Job, application.job_id)
        if job_obj is not None:
            db.expire(job_obj, ["application_count"])
    db.flush()

    job = db.get(Job, application.job_id)
    job_title = job.title if job is not None else "the job"
    payload = {"applicationId": str(application.id), "jobId": str(application.job_id), "status": new_status.value}
    if actor.id == application.user_id:
        if job is not None and job.posted_by is not None:
            body = f"{actor.name} withdrew their application for {job_title}."
            if message:
                body += f" Reason: {message}"
            notify(db, job.posted_by, Category.STATUS_CHANGE, f"Application withdrawn: {job_title}", body, data=payload)
    elif notify_candidate:
        category = _STATUS_CATEGORY.get(new_status, Category.STATUS_CHANGE)
        title = f"Application update: {job_title}"
        body = f"Your application for {job_title} is now {new_status.value.replace('_', ' ').title()}."
        if message:
            body += f"\n\n{message}"
        notify(db, application.user_id, category, title, body, data=payload)
    return application


# --------------------------------------------------------------------------- serialization


def _job_summary(job: Job | None, company: Company | None) -> dict[str, Any] | None:
    if job is None:
        return None
    return {
        "id": job.id,
        "title": job.title,
        "status": job.status,
        "locations": list(job.locations or []),
        "jobType": job.job_type,
        "employmentType": job.employment_type,
        "workMode": job.work_mode,
        "experienceMin": job.experience_min,
        "experienceMax": job.experience_max,
        "company": (
            {"id": company.id, "name": company.name, "logoUrl": company.logo_url} if company is not None else None
        ),
    }


def _interview_dict(interview: Interview | None) -> dict[str, Any] | None:
    if interview is None:
        return None
    return {
        "id": interview.id,
        "scheduledAt": interview.scheduled_at,
        "mode": interview.mode,
        "locationOrLink": interview.location_or_link,
        "notes": interview.notes,
        "candidateResponse": interview.candidate_response,
        "responseNote": interview.response_note,
    }


def serialize_applications(
    db: Session, apps: Sequence[Application], view: str = "seeker", detail: bool = False
) -> list[dict[str, Any]]:
    """Batched serializer (constant number of queries regardless of page size)."""
    if not apps:
        return []
    app_ids = [a.id for a in apps]
    job_ids = {a.job_id for a in apps}
    jobs = {j.id: j for j in db.scalars(select(Job).where(Job.id.in_(job_ids)))}
    company_ids = {j.company_id for j in jobs.values()}
    companies = {c.id: c for c in db.scalars(select(Company).where(Company.id.in_(company_ids)))} if company_ids else {}

    latest_interview: dict[uuid.UUID, Interview] = {}
    for interview in db.scalars(
        select(Interview).where(Interview.application_id.in_(app_ids)).order_by(Interview.created_at.desc())
    ):
        latest_interview.setdefault(interview.application_id, interview)

    timelines: dict[uuid.UUID, list[StatusHistory]] = {}
    answers: dict[uuid.UUID, list[tuple[ApplicationAnswer, str | None]]] = {}
    candidates: dict[uuid.UUID, User] = {}
    if detail:
        for entry in db.scalars(
            select(StatusHistory).where(StatusHistory.application_id.in_(app_ids)).order_by(StatusHistory.created_at)
        ):
            timelines.setdefault(entry.application_id, []).append(entry)
        for ans, qtext in db.execute(
            select(ApplicationAnswer, ScreeningQuestion.text)
            .outerjoin(ScreeningQuestion, ScreeningQuestion.id == ApplicationAnswer.question_id)
            .where(ApplicationAnswer.application_id.in_(app_ids))
        ).all():
            answers.setdefault(ans.application_id, []).append((ans, qtext))
    if view == "recruiter":
        user_ids = {a.user_id for a in apps}
        candidates = {u.id: u for u in db.scalars(select(User).where(User.id.in_(user_ids)))}

    out: list[dict[str, Any]] = []
    for a in apps:
        job = jobs.get(a.job_id)
        item: dict[str, Any] = {
            "id": a.id,
            "jobId": a.job_id,
            "status": a.status,
            "appliedAt": a.applied_at,
            "updatedAt": a.updated_at,
            "viewedAt": a.viewed_at,
            "resumeId": a.resume_id,
            "coverNote": a.cover_note,
            "expectedCtc": a.expected_ctc,
            "noticePeriod": a.notice_period,
            "matchScore": a.match_score,
            "job": _job_summary(job, companies.get(job.company_id) if job is not None else None),
            "interview": _interview_dict(latest_interview.get(a.id)),
        }
        if view == "recruiter":
            cand = candidates.get(a.user_id)
            item.update(
                {
                    "candidate": {"id": a.user_id, "name": cand.name if cand is not None else None},
                    "screenedOut": a.screened_out,
                    "screenReason": a.screen_reason,
                    "rating": a.rating,
                }
            )
        if detail:
            item["timeline"] = [
                {"status": h.status, "message": h.message, "createdAt": h.created_at}
                for h in timelines.get(a.id, [])
            ]
            item["answers"] = [
                {"questionId": ans.question_id, "question": qtext, "answer": ans.answer}
                for ans, qtext in answers.get(a.id, [])
            ]
        out.append(item)
    return out


def serialize_application(db: Session, app: Application, view: str = "seeker") -> dict[str, Any]:
    """Full detail serializer. Seeker view never exposes recruiter notes, rating or screening outcome."""
    return serialize_applications(db, [app], view=view, detail=True)[0]
