"""Recruiter candidate database: boolean keyword parser, visibility rules, filters and masking.

Boolean grammar (precedence NOT > AND > OR, implicit AND between adjacent terms)::

    or_expr  := and_expr ( OR and_expr )*
    and_expr := not_expr ( [AND] not_expr )*
    not_expr := NOT not_expr | atom
    atom     := WORD | "quoted phrase" | '(' or_expr ')'

Operators are case-insensitive keywords; quote a word to search for it literally.
"""

from __future__ import annotations

import logging
import re
import uuid
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

from sqlalchemy import ColumnElement, Select, and_, case, func, not_, or_, select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.core.responses import PageParams, paginate
from app.db import utcnow
from app.models.accounts import User
from app.models.applications import Application
from app.models.company import Company
from app.models.enums import UserRole, Visibility
from app.models.jobs import Job
from app.models.master import Skill
from app.models.profile import (
    Education,
    Employment,
    HiddenCompany,
    JobSeekerProfile,
    ProfileSkill,
)
from app.services import credits

logger = logging.getLogger(__name__)

MAX_QUERY_LENGTH = 500
MAX_TERMS = 25
MAX_DEPTH = 8
MAX_SKILLS_IN_LIST = 10
SORTS = ("relevance", "experience", "lastActive")

# ======================================================================================= boolean parser


class BooleanSyntaxError(ValueError):
    """Raised for a malformed boolean keyword query."""


@dataclass(frozen=True)
class Term:
    text: str


@dataclass(frozen=True)
class Not:
    node: Node


@dataclass(frozen=True)
class And:
    nodes: tuple[Node, ...]


@dataclass(frozen=True)
class Or:
    nodes: tuple[Node, ...]


Node = Term | Not | And | Or

_LP, _RP, _AND, _OR, _NOT, _TERM = "LP", "RP", "AND", "OR", "NOT", "TERM"
_OPERATORS = {"and": _AND, "or": _OR, "not": _NOT}


def _tokenize(q: str) -> list[tuple[str, str]]:
    tokens: list[tuple[str, str]] = []
    i, n = 0, len(q)
    while i < n:
        ch = q[i]
        if ch.isspace():
            i += 1
        elif ch == "(":
            tokens.append((_LP, ch))
            i += 1
        elif ch == ")":
            tokens.append((_RP, ch))
            i += 1
        elif ch == '"':
            end = q.find('"', i + 1)
            if end == -1:
                raise BooleanSyntaxError("Unclosed quote in keyword query")
            phrase = q[i + 1 : end].strip()
            if not phrase:
                raise BooleanSyntaxError("Empty quoted phrase in keyword query")
            tokens.append((_TERM, phrase))
            i = end + 1
        else:
            j = i
            while j < n and not q[j].isspace() and q[j] not in '()"':
                j += 1
            word = q[i:j]
            tokens.append((_OPERATORS.get(word.lower(), _TERM), word))
            i = j
    return tokens


class _Parser:
    def __init__(self, tokens: list[tuple[str, str]]) -> None:
        self.tokens = tokens
        self.pos = 0
        self.terms = 0

    def _peek(self) -> str | None:
        return self.tokens[self.pos][0] if self.pos < len(self.tokens) else None

    def _next(self) -> tuple[str, str]:
        token = self.tokens[self.pos]
        self.pos += 1
        return token

    def parse(self) -> Node:
        node = self._or(0)
        if self.pos < len(self.tokens):
            kind, text = self.tokens[self.pos]
            if kind == _RP:
                raise BooleanSyntaxError("Unbalanced closing parenthesis in keyword query")
            raise BooleanSyntaxError(f"Unexpected '{text}' in keyword query")
        return node

    def _or(self, depth: int) -> Node:
        if depth > MAX_DEPTH:
            raise BooleanSyntaxError("Keyword query is nested too deeply")
        parts = [self._and(depth)]
        while self._peek() == _OR:
            self._next()
            parts.append(self._and(depth))
        return parts[0] if len(parts) == 1 else Or(tuple(parts))

    def _and(self, depth: int) -> Node:
        parts = [self._not(depth)]
        while True:
            kind = self._peek()
            if kind == _AND:
                self._next()
                parts.append(self._not(depth))
            elif kind in (_TERM, _NOT, _LP):  # implicit AND
                parts.append(self._not(depth))
            else:
                break
        return parts[0] if len(parts) == 1 else And(tuple(parts))

    def _not(self, depth: int) -> Node:
        if self._peek() == _NOT:
            self._next()
            return Not(self._not(depth))
        return self._atom(depth)

    def _atom(self, depth: int) -> Node:
        kind = self._peek()
        if kind is None:
            raise BooleanSyntaxError("Keyword query ends unexpectedly (missing operand)")
        if kind == _LP:
            self._next()
            node = self._or(depth + 1)
            if self._peek() != _RP:
                raise BooleanSyntaxError("Missing closing parenthesis in keyword query")
            self._next()
            return node
        if kind == _TERM:
            self.terms += 1
            if self.terms > MAX_TERMS:
                raise BooleanSyntaxError(f"Keyword query has more than {MAX_TERMS} terms")
            return Term(self._next()[1])
        text = self.tokens[self.pos][1]
        raise BooleanSyntaxError(f"Unexpected '{text}' in keyword query (missing operand)")


def parse_boolean(q: str | None) -> Node | None:
    """Parse a boolean keyword query into an AST (``None`` for a blank query).

    Raises :class:`BooleanSyntaxError` for malformed input.
    """
    if q is None or not q.strip():
        return None
    if len(q) > MAX_QUERY_LENGTH:
        raise BooleanSyntaxError(f"Keyword query is longer than {MAX_QUERY_LENGTH} characters")
    return _Parser(_tokenize(q)).parse()


def positive_terms(node: Node | None) -> list[str]:
    """Distinct terms that are not under a NOT (used for relevance ranking)."""
    found: list[str] = []

    def walk(n: Node, negated: bool) -> None:
        if isinstance(n, Term):
            if not negated and n.text.lower() not in (t.lower() for t in found):
                found.append(n.text)
        elif isinstance(n, Not):
            walk(n.node, not negated)
        else:
            for child in n.nodes:
                walk(child, negated)

    if node is not None:
        walk(node, False)
    return found


def like_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _contains(column: ColumnElement, text: str) -> ColumnElement[bool]:
    # coalesce so a NULL column never turns NOT(term) into NULL (which would drop the row)
    return func.coalesce(column, "").ilike(f"%{like_escape(text)}%", escape="\\")


def _skill_match(text: str) -> ColumnElement[bool]:
    return (
        select(ProfileSkill.id)
        .join(Skill, Skill.id == ProfileSkill.skill_id)
        .where(ProfileSkill.user_id == User.id, Skill.name.ilike(f"%{like_escape(text)}%", escape="\\"))
        .exists()
    )


def _employment_match(text: str) -> ColumnElement[bool]:
    return (
        select(Employment.id)
        .where(
            Employment.user_id == User.id,
            or_(_contains(Employment.designation, text), _contains(Employment.company_name, text)),
        )
        .exists()
    )


def term_clause(text: str) -> ColumnElement[bool]:
    """Does the candidate match ``text`` in headline, summary, skills, employments or location?"""
    return or_(
        _contains(JobSeekerProfile.headline, text),
        _contains(JobSeekerProfile.summary, text),
        _contains(JobSeekerProfile.current_location, text),
        _skill_match(text),
        _employment_match(text),
    )


def term_score(text: str) -> ColumnElement[int]:
    """Relevance weight of a single term: headline 3, skills 2, everything else 1."""
    return (
        case((_contains(JobSeekerProfile.headline, text), 3), else_=0)
        + case((_skill_match(text), 2), else_=0)
        + case(
            (
                or_(
                    _contains(JobSeekerProfile.summary, text),
                    _contains(JobSeekerProfile.current_location, text),
                    _employment_match(text),
                ),
                1,
            ),
            else_=0,
        )
    )


def build_filter(node: Node, term_builder: Callable[[str], ColumnElement[bool]] = term_clause) -> ColumnElement[bool]:
    """Translate the AST to a SQLAlchemy boolean expression."""
    if isinstance(node, Term):
        return term_builder(node.text)
    if isinstance(node, Not):
        return not_(build_filter(node.node, term_builder))
    if isinstance(node, And):
        return and_(*(build_filter(n, term_builder) for n in node.nodes))
    return or_(*(build_filter(n, term_builder) for n in node.nodes))


# ======================================================================================= visibility


def visibility_conditions(company_id: uuid.UUID) -> list[ColumnElement[bool]]:
    """WHERE conditions for (User, JobSeekerProfile) rows a company's recruiters may see."""
    hidden_by_candidate = (
        select(HiddenCompany.id)
        .where(HiddenCompany.user_id == User.id, HiddenCompany.company_id == company_id)
        .exists()
    )
    applied_to_company = (
        select(Application.id)
        .join(Job, Job.id == Application.job_id)
        .where(Application.user_id == User.id, Job.company_id == company_id)
        .exists()
    )
    return [
        User.role == UserRole.JOB_SEEKER,
        User.deleted_at.is_(None),
        User.is_blocked.is_(False),
        JobSeekerProfile.visibility != Visibility.HIDDEN,
        not_(hidden_by_candidate),
        or_(
            JobSeekerProfile.visibility == Visibility.ALL_RECRUITERS,
            and_(JobSeekerProfile.visibility == Visibility.APPLIED_ONLY, applied_to_company),
        ),
    ]


def visible_candidates_stmt(company_id: uuid.UUID) -> Select[Any]:
    return (
        select(User, JobSeekerProfile)
        .join(JobSeekerProfile, JobSeekerProfile.user_id == User.id)
        .where(*visibility_conditions(company_id))
    )


# ======================================================================================= filters


@dataclass
class CandidateFilters:
    q: str | None = None
    skills: list[str] = field(default_factory=list)
    experience_min: float | None = None
    experience_max: float | None = None
    locations: list[str] = field(default_factory=list)
    ctc_min: float | None = None
    ctc_max: float | None = None
    notice_periods: list[str] = field(default_factory=list)
    education: list[str] = field(default_factory=list)
    industries: list[str] = field(default_factory=list)
    last_active_days: int | None = None
    sort: str = "relevance"


def split_csv(value: str | None) -> list[str]:
    if not value:
        return []
    seen: dict[str, str] = {}
    for part in value.split(","):
        part = part.strip()
        if part:
            seen.setdefault(part.lower(), part)
    return list(seen.values())


def _total_months() -> ColumnElement[int]:
    return JobSeekerProfile.experience_years * 12 + JobSeekerProfile.experience_months


def _location_match(loc: str) -> ColumnElement[bool]:
    return or_(
        _contains(JobSeekerProfile.current_location, loc),
        _contains(func.array_to_string(JobSeekerProfile.preferred_locations, "|"), loc),
        _contains(func.array_to_string(JobSeekerProfile.desired_locations, "|"), loc),
    )


def _industry_match(industry: str) -> ColumnElement[bool]:
    return or_(
        _contains(JobSeekerProfile.desired_industry, industry),
        select(Employment.id)
        .where(
            Employment.user_id == User.id,
            or_(_contains(Employment.designation, industry), _contains(Employment.description, industry)),
        )
        .exists(),
    )


def filter_conditions(filters: CandidateFilters, node: Node | None) -> list[ColumnElement[bool]]:
    conditions: list[ColumnElement[bool]] = []
    if node is not None:
        conditions.append(build_filter(node))
    for skill in filters.skills:  # every requested skill must match
        conditions.append(
            select(ProfileSkill.id)
            .join(Skill, Skill.id == ProfileSkill.skill_id)
            .where(ProfileSkill.user_id == User.id, func.lower(Skill.name) == skill.lower())
            .exists()
        )
    if filters.experience_min is not None:
        conditions.append(_total_months() >= filters.experience_min * 12)
    if filters.experience_max is not None:
        conditions.append(_total_months() <= filters.experience_max * 12)
    if filters.locations:
        conditions.append(or_(*(_location_match(loc) for loc in filters.locations)))
    if filters.ctc_min is not None:
        conditions.append(JobSeekerProfile.expected_ctc >= filters.ctc_min)
    if filters.ctc_max is not None:
        conditions.append(JobSeekerProfile.expected_ctc <= filters.ctc_max)
    if filters.notice_periods:
        conditions.append(
            func.lower(JobSeekerProfile.notice_period).in_([n.lower() for n in filters.notice_periods])
        )
    if filters.education:
        conditions.append(
            select(Education.id)
            .where(Education.user_id == User.id, or_(*(_contains(Education.degree, d) for d in filters.education)))
            .exists()
        )
    if filters.industries:
        conditions.append(or_(*(_industry_match(i) for i in filters.industries)))
    if filters.last_active_days is not None:
        conditions.append(User.last_active_at >= utcnow() - timedelta(days=filters.last_active_days))
    return conditions


def _order_by(filters: CandidateFilters, terms: list[str]) -> list[Any]:
    last_active = User.last_active_at.desc().nulls_last()
    if filters.sort == "experience":
        return [_total_months().desc(), last_active, User.id]
    if filters.sort == "lastActive":
        return [last_active, User.id]
    if terms:
        score = term_score(terms[0])
        for term in terms[1:]:
            score = score + term_score(term)
        return [score.desc(), last_active, User.id]
    return [last_active, User.id]


def search_candidates(
    db: Session, company: Company, filters: CandidateFilters, page: int, page_size: int
) -> tuple[list[dict[str, Any]], int]:
    """Visible, masked candidates matching ``filters`` (DB-level pagination)."""
    try:
        node = parse_boolean(filters.q)
    except BooleanSyntaxError as exc:
        raise AppError(422, "VALIDATION_ERROR", str(exc), [{"field": "q", "message": str(exc)}]) from exc
    stmt = visible_candidates_stmt(company.id).where(*filter_conditions(filters, node))
    stmt = stmt.order_by(*_order_by(filters, positive_terms(node)))
    params = PageParams(page=page, page_size=page_size)
    rows, total = paginate(db, stmt, params)
    return serialize_candidates(db, company, [(r[0], r[1]) for r in rows]), total


# ======================================================================================= masking


def mask_name(name: str) -> str:
    """'Rahul Sharma' -> 'Rahul S****'; a single name is left as is."""
    parts = (name or "").split()
    if not parts:
        return "Candidate"
    if len(parts) == 1:
        return parts[0]
    return f"{parts[0]} {parts[1][0]}****"


def mask_candidate(item: dict[str, Any], unlocked: bool) -> dict[str, Any]:
    """Return ``item`` with contact details/photo removed and the name masked unless unlocked."""
    item["maskedName"] = mask_name(item.get("name") or "")
    item["isUnlocked"] = unlocked
    if not unlocked:
        item["name"] = item["maskedName"]
        for key in ("email", "mobile", "photoUrl"):
            item.pop(key, None)
    return item


def _education_summary(edu: Education) -> str:
    text = edu.degree
    if edu.specialization:
        text += f" ({edu.specialization})"
    if edu.institute:
        text += f", {edu.institute}"
    return text


def _batch_skills(db: Session, ids: list[uuid.UUID]) -> dict[uuid.UUID, list[str]]:
    result: dict[uuid.UUID, list[str]] = {i: [] for i in ids}
    rows = db.execute(
        select(ProfileSkill.user_id, Skill.name)
        .join(Skill, Skill.id == ProfileSkill.skill_id)
        .where(ProfileSkill.user_id.in_(ids))
        .order_by(ProfileSkill.years_of_experience.desc().nulls_last(), func.lower(Skill.name))
    ).all()
    for user_id, name in rows:
        result[user_id].append(name)
    return result


def _batch_education(db: Session, ids: list[uuid.UUID]) -> dict[uuid.UUID, Education]:
    latest: dict[uuid.UUID, Education] = {}
    rows = db.scalars(
        select(Education)
        .where(Education.user_id.in_(ids))
        .order_by(Education.end_year.desc().nulls_last(), Education.start_year.desc().nulls_last())
    ).all()
    for edu in rows:
        latest.setdefault(edu.user_id, edu)
    return latest


def _batch_current_employment(db: Session, ids: list[uuid.UUID]) -> dict[uuid.UUID, Employment]:
    current: dict[uuid.UUID, Employment] = {}
    rows = db.scalars(
        select(Employment)
        .where(Employment.user_id.in_(ids))
        .order_by(Employment.is_current.desc(), Employment.start_date.desc().nulls_last())
    ).all()
    for emp in rows:
        current.setdefault(emp.user_id, emp)
    return current


def serialize_candidates(
    db: Session, company: Company, pairs: Iterable[tuple[User, JobSeekerProfile]]
) -> list[dict[str, Any]]:
    """Masked list items for ``(User, JobSeekerProfile)`` pairs using four batched queries."""
    pairs = list(pairs)
    if not pairs:
        return []
    ids = [user.id for user, _ in pairs]
    skills = _batch_skills(db, ids)
    education = _batch_education(db, ids)
    employment = _batch_current_employment(db, ids)
    unlocked = credits.unlocked_ids(db, company.id, ids)
    items: list[dict[str, Any]] = []
    for user, profile in pairs:
        edu = education.get(user.id)
        emp = employment.get(user.id)
        item = {
            "id": user.id,
            "name": user.name,
            "headline": profile.headline,
            "experienceYears": profile.experience_years,
            "experienceMonths": profile.experience_months,
            "currentLocation": profile.current_location,
            "skills": skills.get(user.id, [])[:MAX_SKILLS_IN_LIST],
            "expectedCtc": profile.expected_ctc,
            "noticePeriod": profile.notice_period,
            "education": _education_summary(edu) if edu else None,
            "currentEmployer": emp.company_name if emp else None,
            "currentDesignation": emp.designation if emp else None,
            "lastActiveAt": user.last_active_at,
            "email": user.email,
            "mobile": user.mobile,
            "photoUrl": profile.photo_url,
        }
        items.append(mask_candidate(item, user.id in unlocked))
    return items


__all__ = [
    "And",
    "BooleanSyntaxError",
    "CandidateFilters",
    "Not",
    "Or",
    "Term",
    "build_filter",
    "mask_candidate",
    "mask_name",
    "parse_boolean",
    "positive_terms",
    "search_candidates",
    "serialize_candidates",
    "split_csv",
    "visibility_conditions",
    "visible_candidates_stmt",
]
