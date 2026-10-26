"""Recruiter job CRUD: sanitising, question builder, listing and serialisation.

Status/quota rules live in :mod:`app.services.jobs_lifecycle`; this module never changes
``Job.status`` except for the documented REJECTED -> DRAFT reset on edit.
Nothing here commits - the router owns the transaction.
"""

from __future__ import annotations

import html
import json
import logging
import re
import uuid
from collections import defaultdict
from collections.abc import Iterable, Sequence
from datetime import datetime, timezone
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urlparse

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.core.errors import AppError, ConflictError, ForbiddenError, NotFoundError
from app.models.applications import Application, ApplicationAnswer
from app.models.enums import ApplicationStatus, JobStatus, QuestionType
from app.models.jobs import Job, ScreeningQuestion
from app.schemas.recruiter_jobs import JobIn, QuestionIn
from app.services.job_index import reindex_job

logger = logging.getLogger(__name__)

SORT_COLUMNS = {
    "postedat": Job.posted_at,
    "createdat": Job.created_at,
    "applicationcount": Job.application_count,
    "viewcount": Job.view_count,
}


# --------------------------------------------------------------------------- HTML sanitising

_ALLOWED_TAGS = {
    "p", "br", "hr", "b", "i", "u", "s", "strong", "em", "small", "sub", "sup", "ul", "ol", "li",
    "h1", "h2", "h3", "h4", "h5", "h6", "a", "span", "div", "blockquote", "code", "pre",
    "table", "thead", "tbody", "tr", "th", "td",
}  # fmt: skip
_VOID_TAGS = {"br", "hr"}
_DROP_WITH_CONTENT = {"script", "style", "iframe", "object", "embed", "noscript", "template", "svg", "math"}
_SAFE_SCHEMES = {"http", "https", "mailto", "tel"}


class _HtmlSanitizer(HTMLParser):
    """Allow-list sanitiser: keeps basic formatting, drops scripts, event handlers and unsafe URLs."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.out: list[str] = []
        self._open: list[str] = []
        self._skip_depth = 0

    @staticmethod
    def _safe_href(value: str | None) -> str | None:
        if not value:
            return None
        cleaned = re.sub(r"[\x00-\x20]+", "", value)
        scheme = urlparse(cleaned).scheme.lower()
        if scheme and scheme not in _SAFE_SCHEMES:
            return None
        return value.strip()

    def _render_start(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        rendered = f"<{tag}"
        if tag == "a":
            href = self._safe_href(dict(attrs).get("href"))
            if href:
                rendered += f' href="{html.escape(href, quote=True)}" rel="noopener noreferrer"'
        self.out.append(rendered + (" />" if tag in _VOID_TAGS else ">"))

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in _DROP_WITH_CONTENT:
            self._skip_depth += 1
            return
        if self._skip_depth or tag not in _ALLOWED_TAGS:
            return
        self._render_start(tag, attrs)
        if tag not in _VOID_TAGS:
            self._open.append(tag)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in _DROP_WITH_CONTENT or self._skip_depth or tag not in _ALLOWED_TAGS:
            return
        self._render_start(tag, attrs)

    def handle_endtag(self, tag: str) -> None:
        if tag in _DROP_WITH_CONTENT:
            self._skip_depth = max(0, self._skip_depth - 1)
            return
        if self._skip_depth or tag not in _ALLOWED_TAGS or tag in _VOID_TAGS or tag not in self._open:
            return
        while self._open:
            top = self._open.pop()
            self.out.append(f"</{top}>")
            if top == tag:
                break

    def handle_data(self, data: str) -> None:
        if not self._skip_depth:
            self.out.append(html.escape(data, quote=False))

    def result(self) -> str:
        while self._open:
            self.out.append(f"</{self._open.pop()}>")
        return "".join(self.out)


def sanitize_html(value: str | None) -> str | None:
    """Strip scripts, event-handler attributes, unsafe URLs and unknown tags from rich text."""
    if value is None:
        return None
    parser = _HtmlSanitizer()
    parser.feed(value)
    parser.close()
    return parser.result().strip()


# --------------------------------------------------------------------------- serialisation


def _expected_out(question: ScreeningQuestion) -> Any:
    raw = question.expected_answer
    if raw is None:
        return None
    if question.question_type == QuestionType.MULTIPLE_CHOICE:
        try:
            parsed = json.loads(raw)
        except ValueError:
            return [raw]
        return parsed if isinstance(parsed, list) else [str(parsed)]
    return raw


def _expected_in(data: QuestionIn) -> str | None:
    expected = data.expected_answer
    if expected is None:
        return None
    if data.type == QuestionType.MULTIPLE_CHOICE:
        return json.dumps(expected if isinstance(expected, list) else [expected])
    return str(expected)


def question_dict(question: ScreeningQuestion) -> dict[str, Any]:
    return {
        "id": question.id,
        "text": question.text,
        "type": question.question_type,
        "options": list(question.options or []),
        "isKnockout": question.is_knockout,
        "expectedAnswer": _expected_out(question),
        "isRequired": question.is_required,
        "position": question.position,
    }


def load_questions(db: Session, job_ids: Iterable[uuid.UUID]) -> dict[uuid.UUID, list[ScreeningQuestion]]:
    """Batch-load questions for many jobs (one query)."""
    ids = list(job_ids)
    out: dict[uuid.UUID, list[ScreeningQuestion]] = defaultdict(list)
    if not ids:
        return out
    stmt = (
        select(ScreeningQuestion)
        .where(ScreeningQuestion.job_id.in_(ids))
        .order_by(ScreeningQuestion.position, ScreeningQuestion.id)
    )
    for question in db.scalars(stmt):
        out[question.job_id].append(question)
    return out


def status_counts(db: Session, job_ids: Iterable[uuid.UUID]) -> dict[uuid.UUID, dict[str, int]]:
    """Applicant counts per job and status in one grouped query."""
    ids = list(job_ids)
    out: dict[uuid.UUID, dict[str, int]] = {jid: {} for jid in ids}
    if not ids:
        return out
    rows = db.execute(
        select(Application.job_id, Application.status, func.count())
        .where(Application.job_id.in_(ids))
        .group_by(Application.job_id, Application.status)
    ).all()
    for job_id, status, count in rows:
        out[job_id][ApplicationStatus(status).value] = int(count)
    return out


def job_dict(
    job: Job,
    questions: Sequence[ScreeningQuestion] | None = None,
    counts: dict[str, int] | None = None,
) -> dict[str, Any]:
    data: dict[str, Any] = {
        "id": job.id,
        "companyId": job.company_id,
        "postedBy": job.posted_by,
        "title": job.title,
        "description": job.description,
        "responsibilities": job.responsibilities,
        "requiredSkills": list(job.required_skills or []),
        "preferredSkills": list(job.preferred_skills or []),
        "experienceMin": job.experience_min,
        "experienceMax": job.experience_max,
        "salaryMin": job.salary_min,
        "salaryMax": job.salary_max,
        "hideSalary": job.hide_salary,
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
        "rejectReason": job.reject_reason,
        "postedAt": job.posted_at,
        "expiresAt": job.expires_at,
        "viewCount": job.view_count,
        "applicationCount": job.application_count,
        "createdAt": job.created_at,
        "updatedAt": job.updated_at,
    }
    if counts is not None:
        data["applicantCounts"] = counts
    if questions is not None:
        data["questions"] = [question_dict(q) for q in questions]
    return data


def serialize_jobs(db: Session, jobs: Sequence[Job], detail: bool = False) -> list[dict[str, Any]]:
    """Batched serialiser: constant number of queries regardless of list size."""
    ids = [j.id for j in jobs]
    counts = status_counts(db, ids)
    questions = load_questions(db, ids) if detail else None
    return [
        job_dict(j, questions.get(j.id, []) if questions is not None else None, counts.get(j.id, {})) for j in jobs
    ]


# --------------------------------------------------------------------------- access helpers


def get_company_job(db: Session, job_id: uuid.UUID, company_id: uuid.UUID, lock: bool = False) -> Job:
    """Existing non-deleted job of the recruiter's company (404 unknown, 403 foreign)."""
    stmt = select(Job).where(Job.id == job_id)
    if lock:
        stmt = stmt.with_for_update().execution_options(populate_existing=True)
    job = db.scalar(stmt)
    if job is None or job.deleted_at is not None:
        raise NotFoundError("Job not found")
    if job.company_id != company_id:
        raise ForbiddenError("This job belongs to another company")
    return job


# --------------------------------------------------------------------------- listing


def list_stmt(
    company_id: uuid.UUID, statuses: list[JobStatus], q: str | None, sort: str, order: str
) -> Select[Any]:
    stmt = select(Job).where(Job.company_id == company_id, Job.deleted_at.is_(None))
    if statuses:
        stmt = stmt.where(Job.status.in_(statuses))
    if q and q.strip():
        pattern = "%" + q.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        stmt = stmt.where(Job.title.ilike(pattern, escape="\\"))
    column = SORT_COLUMNS[sort]
    ordered = column.asc().nulls_last() if order == "asc" else column.desc().nulls_last()
    return stmt.order_by(ordered, Job.created_at.desc(), Job.id)


def parse_sort(sort: str | None, order: str | None) -> tuple[str, str]:
    key = (sort or "createdAt").replace("_", "").lower()
    if key not in SORT_COLUMNS:
        raise AppError(
            422,
            "VALIDATION_ERROR",
            "Invalid sort",
            [{"field": "sort", "message": "Must be one of postedAt, createdAt, applicationCount, viewCount"}],
        )
    direction = (order or "desc").lower()
    if direction not in ("asc", "desc"):
        raise AppError(422, "VALIDATION_ERROR", "Invalid order", [{"field": "order", "message": "Must be asc or desc"}])
    return key, direction


def parse_statuses(value: str | None) -> list[JobStatus]:
    out: list[JobStatus] = []
    for part in (value or "").split(","):
        part = part.strip()
        if not part:
            continue
        try:
            status = JobStatus(part.upper())
        except ValueError:
            raise AppError(
                422,
                "VALIDATION_ERROR",
                "Invalid status filter",
                [{"field": "status", "message": f"Unknown job status '{part}'"}],
            ) from None
        if status not in out:
            out.append(status)
    return out


# --------------------------------------------------------------------------- create / update / delete


def _apply_fields(job: Job, data: JobIn) -> None:
    job.title = data.title
    job.description = sanitize_html(data.description)
    job.responsibilities = sanitize_html(data.responsibilities)
    job.required_skills = list(data.required_skills)
    job.preferred_skills = list(data.preferred_skills)
    job.experience_min = data.experience_min
    job.experience_max = data.experience_max
    job.salary_min = data.salary_min
    job.salary_max = data.salary_max
    job.hide_salary = data.hide_salary
    job.job_type = data.job_type
    job.employment_type = data.employment_type
    job.work_mode = data.work_mode
    job.locations = list(data.locations)
    job.openings = data.openings
    job.industry = data.industry
    job.department = data.department
    job.role_category = data.role_category
    job.education = data.education
    job.notice_preference = data.notice_preference
    job.is_walk_in = data.is_walk_in
    job.walk_in_details = data.walk_in_details.model_dump(mode="json") if data.walk_in_details else None
    job.deadline = data.deadline


def _apply_question(question: ScreeningQuestion, data: QuestionIn, position: int) -> None:
    question.text = data.text
    question.question_type = data.type
    question.options = list(data.options)
    question.is_knockout = data.is_knockout
    question.expected_answer = _expected_in(data)
    question.is_required = data.is_required
    question.position = position


def create_job(db: Session, user_id: uuid.UUID, company_id: uuid.UUID, data: JobIn) -> Job:
    job = Job(
        id=uuid.uuid4(),
        company_id=company_id,
        posted_by=user_id,
        status=JobStatus.DRAFT,
        view_count=0,
        application_count=0,
    )
    _apply_fields(job, data)
    db.add(job)
    db.flush()
    for position, q in enumerate(data.questions):
        question = ScreeningQuestion(id=uuid.uuid4(), job_id=job.id)
        _apply_question(question, q, position)
        db.add(question)
    reindex_job(db, job.id)
    return job


def _sync_questions(db: Session, job: Job, items: list[QuestionIn]) -> None:
    existing = {q.id: q for q in db.scalars(select(ScreeningQuestion).where(ScreeningQuestion.job_id == job.id))}
    provided = {q.id for q in items if q.id is not None}
    unknown = provided - set(existing)
    if unknown:
        raise AppError(
            422,
            "VALIDATION_ERROR",
            "Unknown question id",
            [{"field": "questions", "message": f"Question {qid} does not belong to this job"} for qid in unknown],
        )
    if len(provided) != len([q for q in items if q.id is not None]):
        raise AppError(422, "VALIDATION_ERROR", "Duplicate question id", [{"field": "questions", "message": "Duplicate id"}])

    removed = [qid for qid in existing if qid not in provided]
    if removed:
        answered = set(
            db.scalars(select(ApplicationAnswer.question_id).where(ApplicationAnswer.question_id.in_(removed)).distinct())
        )
        if answered:
            raise ConflictError(
                "Questions that applicants have already answered cannot be removed; keep them or send their ids",
            )
        for qid in removed:
            db.delete(existing[qid])

    for position, q in enumerate(items):
        if q.id is not None:
            _apply_question(existing[q.id], q, position)
        else:
            question = ScreeningQuestion(id=uuid.uuid4(), job_id=job.id)
            _apply_question(question, q, position)
            db.add(question)
    db.flush()
    db.expire(job, ["questions"])


def update_job(db: Session, job: Job, data: JobIn) -> Job:
    """Edit a job in place. REJECTED jobs go back to DRAFT; other statuses are preserved."""
    _apply_fields(job, data)
    _sync_questions(db, job, data.questions)
    if job.status == JobStatus.REJECTED:
        job.status = JobStatus.DRAFT
    job.updated_at = datetime.now(timezone.utc)
    reindex_job(db, job.id)
    return job


def soft_delete(job: Job) -> None:
    now = datetime.now(timezone.utc)
    job.deleted_at = now
    job.status = JobStatus.CLOSED
    job.updated_at = now
