"""Job search engine: weighted full-text + trigram typo tolerance, synonyms, facets, typeahead,
recommendations and the batched list-object serializer used by every job listing.

All user input reaches SQL only through bound parameters; free-text tokens are additionally
sanitised to ``[a-z0-9+#.]`` before they are used to build tsqueries.
"""

from __future__ import annotations

import html
import logging
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from functools import reduce
from typing import Any

from sqlalchemy import (
    Boolean,
    Float,
    Text,
    and_,
    any_,
    bindparam,
    case,
    cast,
    delete,
    desc,
    false,
    func,
    true,
    literal,
    literal_column,
    or_,
    select,
    text,
    type_coerce,
)
from sqlalchemy.dialects.postgresql import ARRAY as PG_ARRAY
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from sqlalchemy.sql import ColumnElement

from app.models.accounts import User
from app.models.applications import Application
from app.models.company import Company, CompanyReview
from app.models.enums import (
    CompanyStatus,
    CompanyType,
    EmploymentType,
    JobStatus,
    JobType,
    ReviewStatus,
    WorkMode,
)
from app.models.jobs import Job, RecentSearch, SavedJob
from app.models.master import Location, Skill
from app.models.profile import HiddenCompany, JobSeekerProfile, ProfileSkill

logger = logging.getLogger(__name__)

FUZZY_THRESHOLD = 0.35  # word_similarity threshold for typo tolerance (title / skills / company)
MAX_TOKENS = 10
MAX_TERMS_PER_GROUP = 6
FACET_LIMIT = 20
RECENT_SEARCH_KEEP = 20
RECENT_SEARCH_USED = 5
FRESHNESS_DAYS = (1, 3, 7, 15, 30)
SNIPPET_LENGTH = 160

_TOKEN_RE = re.compile(r"[a-z0-9+#.]+")
_TERM_RE = re.compile(r"[^a-z0-9+#. ]+")
_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")
_SEP = "\x1f"
_ENGLISH = literal_column("'english'")


# --------------------------------------------------------------------------- filters

def split_csv(value: Any) -> list[str]:
    """Normalise ``'a,b'`` / ``['a,b', 'c']`` / None into a clean list of non-empty strings."""
    if value is None:
        return []
    items = [value] if isinstance(value, str) else list(value)
    out: list[str] = []
    for item in items:
        for part in str(item).split(","):
            part = part.strip()
            if part:
                out.append(part)
    return out


_FILTER_KEYS: dict[str, str] = {
    "q": "q",
    "location": "location",
    "experience": "experience",
    "salaryMin": "salary_min",
    "salaryMax": "salary_max",
    "department": "department",
    "roleCategory": "role_category",
    "industry": "industry",
    "companyType": "company_type",
    "company": "company",
    "jobType": "job_type",
    "employmentType": "employment_type",
    "workMode": "work_mode",
    "education": "education",
    "freshness": "freshness",
    "postedBy": "posted_by",
    "walkIn": "walk_in",
}
_LIST_FIELDS = {
    "location", "department", "role_category", "industry", "company_type", "company",
    "job_type", "employment_type", "work_mode", "education",
}


@dataclass
class JobSearchFilters:
    """Search filters; multi-valued filters are lists (already split on commas)."""

    q: str | None = None
    location: list[str] = field(default_factory=list)
    experience: float | None = None
    salary_min: float | None = None
    salary_max: float | None = None
    department: list[str] = field(default_factory=list)
    role_category: list[str] = field(default_factory=list)
    industry: list[str] = field(default_factory=list)
    company_type: list[str] = field(default_factory=list)
    company: list[str] = field(default_factory=list)  # company ids or names
    job_type: list[str] = field(default_factory=list)
    employment_type: list[str] = field(default_factory=list)
    work_mode: list[str] = field(default_factory=list)
    education: list[str] = field(default_factory=list)
    freshness: int | None = None
    posted_by: str | None = None  # "company" | "consultancy"
    walk_in: bool = False

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> JobSearchFilters:
        """Build from API-style (camelCase) or snake_case keys, e.g. a stored saved search."""
        flt = cls()
        for key, value in (data or {}).items():
            attr = _FILTER_KEYS.get(key, key if key in _FILTER_KEYS.values() else None)
            if attr is None or value in (None, "", []):
                continue
            if attr in _LIST_FIELDS:
                setattr(flt, attr, split_csv(value))
            elif attr in ("experience", "salary_min", "salary_max"):
                try:
                    setattr(flt, attr, float(value))
                except (TypeError, ValueError):
                    continue
            elif attr == "freshness":
                try:
                    flt.freshness = int(value)
                except (TypeError, ValueError):
                    continue
            elif attr == "walk_in":
                flt.walk_in = value is True or str(value).lower() in ("true", "1", "yes")
            else:
                setattr(flt, attr, str(value))
        return flt

    def to_dict(self, include_q: bool = False) -> dict[str, Any]:
        """camelCase dict of the non-empty filters (what is stored with a recent/saved search)."""
        out: dict[str, Any] = {}
        for api_key, attr in _FILTER_KEYS.items():
            if attr == "q" and not include_q:
                continue
            value = getattr(self, attr)
            if value in (None, "", [], False):
                continue
            out[api_key] = value
        return out


def tokenize(q: str | None) -> list[str]:
    """Lower-case tokens restricted to ``[a-z0-9+#.]`` (deduplicated, capped)."""
    seen: list[str] = []
    for raw in _TOKEN_RE.findall((q or "").lower()):
        token = raw.strip(".")
        if token and token not in seen:
            seen.append(token)
    return seen[:MAX_TOKENS]


def _clean_term(term: str) -> str:
    return _WS_RE.sub(" ", _TERM_RE.sub(" ", term.lower())).strip()


def _synonym_groups(db: Session, tokens: list[str]) -> list[list[str]]:
    """One group per query token: [token, *synonyms]; a trailing group for a multi-word phrase."""
    if not tokens:
        return []
    phrase = " ".join(tokens)
    candidates = list(tokens)
    if len(tokens) > 1:
        candidates.append(phrase)
    stmt = text(
        """
        SELECT name, syn FROM (
            SELECT name,
                   CASE WHEN jsonb_typeof(synonyms) = 'array' THEN synonyms ELSE '[]'::jsonb END AS syn
            FROM skills WHERE is_active
        ) s
        WHERE lower(name) = ANY(:cands)
           OR EXISTS (SELECT 1 FROM jsonb_array_elements_text(syn) AS e(v) WHERE lower(e.v) = ANY(:cands))
        """
    ).bindparams(bindparam("cands", value=candidates, type_=PG_ARRAY(Text)))
    rows = db.execute(stmt).all()

    expansions: dict[str, list[str]] = {c: [] for c in candidates}
    for name, syn in rows:
        names = [_clean_term(str(n)) for n in [name, *(syn or [])] if isinstance(n, str)]
        names = [n for n in dict.fromkeys(names) if n]
        for cand in candidates:
            if cand in names:
                expansions[cand].extend(n for n in names if n != cand and n not in expansions[cand])

    groups = [[t, *expansions[t][: MAX_TERMS_PER_GROUP - 1]] for t in tokens]
    if len(tokens) > 1 and expansions[phrase]:
        groups.append(expansions[phrase][:MAX_TERMS_PER_GROUP])
    return groups


def expand_synonyms(db: Session, q: str | None) -> list[str]:
    """Query tokens plus their master-skill synonyms (both directions), deduplicated, tokens first."""
    groups = _synonym_groups(db, tokenize(q))
    terms: list[str] = []
    for group in groups:
        for term in group:
            if term not in terms:
                terms.append(term)
    return terms


# --------------------------------------------------------------------------- SQL pieces

def _now() -> datetime:
    return datetime.now(timezone.utc)


def visible_job_conditions(now: datetime | None = None) -> list[ColumnElement[bool]]:
    """Public visibility: ACTIVE, not deleted, not expired, owned by an APPROVED live company.
    Callers must join Company."""
    now = now or _now()
    return [
        Job.status == JobStatus.ACTIVE,
        Job.deleted_at.is_(None),
        or_(Job.expires_at.is_(None), Job.expires_at > now),
        Company.status == CompanyStatus.APPROVED,
        Company.deleted_at.is_(None),
    ]


def _like_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


like_escape = _like_escape


def _lower_locations() -> ColumnElement:
    """jobs.locations lower-cased, as a text[] (for case-insensitive overlap checks)."""
    return type_coerce(
        func.string_to_array(func.lower(func.array_to_string(Job.locations, _SEP)), _SEP),
        PG_ARRAY(Text),
    )


def _array_overlap(column: ColumnElement, values: list[str]) -> ColumnElement[bool]:
    return column.op("&&", return_type=Boolean)(literal(values, PG_ARRAY(Text)))


def _skill_overlap(column: ColumnElement, lowered_names: list[str]) -> ColumnElement:
    """Scalar subquery: how many entries of text[] ``column`` equal (case-insens.) one of the names."""
    if not lowered_names:
        return literal(0)
    elem = func.unnest(column).table_valued("sk").render_derived()
    return (
        select(func.count())
        .select_from(elem)
        .where(func.lower(elem.c.sk) == any_(literal(lowered_names, PG_ARRAY(Text))))
        .correlate(Job)
        .scalar_subquery()
    )


def _gate(similarity: ColumnElement) -> ColumnElement:
    return case((similarity >= FUZZY_THRESHOLD, similarity), else_=literal(0.0, Float))


def _max_similarity(terms: list[str], haystack: ColumnElement) -> ColumnElement | None:
    sims = [func.word_similarity(t, haystack) for t in terms if len(t) >= 3]
    if not sims:
        return None
    return sims[0] if len(sims) == 1 else func.greatest(*sims)


class _TextQuery:
    """SQL fragments (WHERE + relevance score) for a free-text query with synonym groups."""

    def __init__(self, groups: list[list[str]]) -> None:
        self.groups = groups
        title = func.lower(Job.title)
        skills = func.lower(
            func.array_to_string(func.array_cat(Job.required_skills, Job.preferred_skills), " ")
        )
        company = func.lower(Company.name)

        group_tsq = [
            reduce(lambda a, b: a.op("||")(b), [func.plainto_tsquery(_ENGLISH, t) for t in g])
            for g in groups
        ]
        self.tsq = reduce(lambda a, b: a.op("||")(b), group_tsq)
        vector = Job.search_vector
        self.fts_match = vector.op("@@", return_type=Boolean)(self.tsq)
        matched = [
            case((vector.op("@@", return_type=Boolean)(tsq), 1), else_=0) for tsq in group_tsq
        ]

        title_sims = [_max_similarity(g, title) for g in groups]
        skill_sims = [_max_similarity(g, skills) for g in groups]
        company_sims = [_max_similarity(g, company) for g in groups]
        fuzzy_any = [s >= FUZZY_THRESHOLD for sims in (title_sims, skill_sims, company_sims) for s in sims if s is not None]
        self.where = or_(self.fts_match, *fuzzy_any)

        def total(sims: list[ColumnElement | None]) -> ColumnElement:
            parts = [_gate(s) for s in sims if s is not None]
            return reduce(lambda a, b: a + b, parts) if parts else literal(0.0, Float)

        # title/skill matches are weighted far above description-only (full-text 'C') matches
        self.score = (
            literal(5.0) * total(title_sims)
            + literal(4.0) * total(skill_sims)
            + literal(1.5) * total(company_sims)
            + literal(3.0) * func.ts_rank_cd(vector, self.tsq, 32)
            + literal(1.0) * reduce(lambda a, b: a + b, matched)
        )


def _text_query(db: Session, q: str | None) -> _TextQuery | None:
    tokens = tokenize(q)
    if not tokens:
        return None
    return _TextQuery(_synonym_groups(db, tokens))


# --------------------------------------------------------------------------- filter conditions

def _lower_values(values: list[str]) -> list[str]:
    return [v.lower() for v in values]


def _enum_condition(column: ColumnElement, enum_cls: type, raw: list[str]) -> ColumnElement[bool]:
    wanted = []
    for item in raw:
        norm = item.strip().upper().replace("-", "_").replace(" ", "_")
        try:
            wanted.append(enum_cls(norm))
        except ValueError:
            continue
    return column.in_(wanted) if wanted else false()


def _split_company_refs(refs: list[str]) -> tuple[list[uuid.UUID], list[str]]:
    ids: list[uuid.UUID] = []
    names: list[str] = []
    for ref in refs:
        try:
            ids.append(uuid.UUID(ref))
        except ValueError:
            names.append(ref.lower())
    return ids, names


def _dimension_conditions(f: JobSearchFilters) -> dict[str, ColumnElement[bool]]:
    """One condition per facet dimension (so each facet can exclude its own filter)."""
    conds: dict[str, ColumnElement[bool]] = {}
    if f.location:
        conds["location"] = _array_overlap(_lower_locations(), _lower_values(f.location))
    for dim, column, values in (
        ("industry", Job.industry, f.industry),
        ("department", Job.department, f.department),
        ("roleCategory", Job.role_category, f.role_category),
        ("education", Job.education, f.education),
    ):
        if values:
            conds[dim] = func.lower(column).in_(_lower_values(values))
    if f.job_type:
        conds["jobType"] = _enum_condition(Job.job_type, JobType, f.job_type)
    if f.employment_type:
        conds["employmentType"] = _enum_condition(Job.employment_type, EmploymentType, f.employment_type)
    if f.work_mode:
        conds["workMode"] = _enum_condition(Job.work_mode, WorkMode, f.work_mode)

    company_type_parts: list[ColumnElement[bool]] = []
    if f.company_type:
        company_type_parts.append(_enum_condition(Company.company_type, CompanyType, f.company_type))
    if f.posted_by == "consultancy":
        company_type_parts.append(Company.company_type == CompanyType.CONSULTANCY)
    elif f.posted_by == "company":
        company_type_parts.append(
            or_(Company.company_type.is_(None), Company.company_type != CompanyType.CONSULTANCY)
        )
    if company_type_parts:
        conds["companyType"] = and_(*company_type_parts)

    if f.company:
        ids, names = _split_company_refs(f.company)
        parts = []
        if ids:
            parts.append(Company.id.in_(ids))
        if names:
            parts.append(func.lower(Company.name).in_(names))
        conds["company"] = or_(*parts)
    return conds


def _fixed_conditions(f: JobSearchFilters, now: datetime) -> list[ColumnElement[bool]]:
    """Filters that are not a facet dimension (always applied)."""
    conds: list[ColumnElement[bool]] = []
    if f.experience is not None:
        x = Decimal(str(f.experience))
        conds.append(or_(Job.experience_min.is_(None), Job.experience_min <= x))
        conds.append(or_(Job.experience_max.is_(None), Job.experience_max >= x))
    if f.salary_min is not None or f.salary_max is not None:
        # only jobs that disclose a salary range take part in salary filtering
        conds.append(Job.hide_salary.is_(False))
        conds.append(or_(Job.salary_min.is_not(None), Job.salary_max.is_not(None)))
    if f.salary_min is not None:
        conds.append(or_(Job.salary_max.is_(None), Job.salary_max >= Decimal(str(f.salary_min))))
    if f.salary_max is not None:
        conds.append(or_(Job.salary_min.is_(None), Job.salary_min <= Decimal(str(f.salary_max))))
    if f.freshness is not None:
        conds.append(Job.posted_at >= now - timedelta(days=f.freshness))
    if f.walk_in:
        conds.append(Job.is_walk_in.is_(True))
    return conds


def _where_for(
    f: JobSearchFilters,
    tq: _TextQuery | None,
    now: datetime,
    exclude_dim: str | None = None,
    extra: tuple[ColumnElement[bool], ...] = (),
) -> list[ColumnElement[bool]]:
    conds = visible_job_conditions(now) + _fixed_conditions(f, now) + list(extra)
    dims = _dimension_conditions(f)
    for name, cond in dims.items():
        if name != exclude_dim:
            conds.append(cond)
    if tq is not None:
        conds.append(tq.where)
    return conds


def _joined_jobs(*columns: Any):
    return select(*columns).select_from(Job).join(Company, Company.id == Job.company_id)


# --------------------------------------------------------------------------- facets

_STRING_FACETS = (
    ("industry", Job.industry),
    ("department", Job.department),
    ("roleCategory", Job.role_category),
    ("education", Job.education),
)
_ENUM_FACETS = (
    ("jobType", Job.job_type),
    ("employmentType", Job.employment_type),
    ("workMode", Job.work_mode),
    ("companyType", Company.company_type),
)


def _facet_value(value: Any) -> Any:
    return value.value if hasattr(value, "value") else value


def _compute_facets(
    db: Session,
    f: JobSearchFilters,
    tq: _TextQuery | None,
    now: datetime,
    extra: tuple[ColumnElement[bool], ...] = (),
) -> dict[str, list[dict[str, Any]]]:
    """Counts per dimension over the filtered set, ignoring that dimension's own filter."""
    facets: dict[str, list[dict[str, Any]]] = {}

    for name, column in (*_STRING_FACETS, *_ENUM_FACETS):
        count = func.count().label("n")
        stmt = (
            _joined_jobs(column.label("v"), count)
            .where(*_where_for(f, tq, now, exclude_dim=name, extra=extra), column.is_not(None))
            .group_by(column)
            .order_by(desc(count), column)
            .limit(FACET_LIMIT)
        )
        facets[name] = [{"value": _facet_value(v), "count": n} for v, n in db.execute(stmt).all() if v != ""]

    # company facet (value = company name, accepted by the `company` filter)
    count = func.count().label("n")
    stmt = (
        _joined_jobs(Company.name, count)
        .where(*_where_for(f, tq, now, exclude_dim="company", extra=extra))
        .group_by(Company.id, Company.name)
        .order_by(desc(count), Company.name)
        .limit(FACET_LIMIT)
    )
    facets["company"] = [{"value": v, "count": n} for v, n in db.execute(stmt).all()]

    # location facet: unnest the array, count distinct jobs per lower-cased city
    loc_table = func.unnest(Job.locations).table_valued("loc").render_derived()
    loc = loc_table.c.loc
    count = func.count(func.distinct(Job.id)).label("n")
    stmt = (
        select(func.min(loc).label("v"), count)
        .select_from(Job)
        .join(Company, Company.id == Job.company_id)
        .join(loc_table, true())
        .where(*_where_for(f, tq, now, exclude_dim="location", extra=extra), func.btrim(loc) != "")
        .group_by(func.lower(loc))
        .order_by(desc(count), func.min(loc))
        .limit(FACET_LIMIT)
    )
    facets["location"] = [{"value": v, "count": n} for v, n in db.execute(stmt).all()]
    return facets


# --------------------------------------------------------------------------- serializers

def strip_html(value: str | None) -> str:
    if not value:
        return ""
    return _WS_RE.sub(" ", html.unescape(_TAG_RE.sub(" ", value))).strip()


def make_snippet(job: Job, tokens: list[str]) -> str:
    """Short plain-text excerpt around the first query term (or the start of the description)."""
    body = strip_html(job.description) or strip_html(job.responsibilities)
    if not body:
        return ""
    lowered = body.lower()
    positions = [p for p in (lowered.find(t) for t in tokens) if p >= 0]
    if not positions:
        return body[:SNIPPET_LENGTH] + ("…" if len(body) > SNIPPET_LENGTH else "")
    pos = min(positions)
    start = max(0, pos - SNIPPET_LENGTH // 4)
    if start > 0:  # begin at a word boundary
        space = body.find(" ", start)
        start = space + 1 if 0 <= space < pos else start
    chunk = body[start : start + SNIPPET_LENGTH]
    return ("…" if start > 0 else "") + chunk + ("…" if start + SNIPPET_LENGTH < len(body) else "")


def company_ratings(db: Session, company_ids: list[uuid.UUID]) -> dict[uuid.UUID, tuple[float, int]]:
    """{company_id: (avg rating rounded to 1 dp, review count)} from APPROVED reviews only."""
    if not company_ids:
        return {}
    rows = db.execute(
        select(CompanyReview.company_id, func.avg(CompanyReview.rating), func.count())
        .where(CompanyReview.company_id.in_(company_ids), CompanyReview.status == ReviewStatus.APPROVED)
        .group_by(CompanyReview.company_id)
    ).all()
    return {cid: (round(float(avg), 1), int(n)) for cid, avg, n in rows}


def saved_and_applied(
    db: Session, user: User | None, job_ids: list[uuid.UUID]
) -> tuple[set[uuid.UUID], set[uuid.UUID]]:
    if user is None or not job_ids:
        return set(), set()
    saved = set(db.scalars(select(SavedJob.job_id).where(SavedJob.user_id == user.id, SavedJob.job_id.in_(job_ids))))
    applied = set(
        db.scalars(select(Application.job_id).where(Application.user_id == user.id, Application.job_id.in_(job_ids)))
    )
    return saved, applied


def serialize_jobs(
    db: Session, jobs: list[Job], user: User | None, query: str | None = None
) -> list[dict[str, Any]]:
    """List-object serializer; related rows are batch-loaded (4 queries regardless of page size)."""
    if not jobs:
        return []
    company_ids = list({j.company_id for j in jobs})
    companies = {
        c.id: c for c in db.scalars(select(Company).where(Company.id.in_(company_ids))).all()
    }
    ratings = company_ratings(db, company_ids)
    saved, applied = saved_and_applied(db, user, [j.id for j in jobs])
    tokens = tokenize(query)

    items: list[dict[str, Any]] = []
    for job in jobs:
        company = companies.get(job.company_id)
        disclosed = not job.hide_salary
        items.append(
            {
                "id": job.id,
                "title": job.title,
                "company": {
                    "id": job.company_id,
                    "name": company.name if company else None,
                    "logoUrl": company.logo_url if company else None,
                    "rating": ratings[job.company_id][0] if job.company_id in ratings else None,
                },
                "experienceMin": job.experience_min,
                "experienceMax": job.experience_max,
                "salaryMin": job.salary_min if disclosed else None,
                "salaryMax": job.salary_max if disclosed else None,
                "salaryDisclosed": disclosed,
                "locations": list(job.locations or []),
                "skills": list(job.required_skills or []),
                "jobType": job.job_type,
                "employmentType": job.employment_type,
                "workMode": job.work_mode,
                "postedAt": job.posted_at,
                "isSaved": job.id in saved,
                "isApplied": job.id in applied,
                "snippet": make_snippet(job, tokens),
            }
        )
    return items


# --------------------------------------------------------------------------- recent searches

def _record_recent_search(db: Session, user: User, f: JobSearchFilters) -> None:
    query = (f.q or "").strip()[:500]
    if not query:
        return
    try:
        db.execute(
            delete(RecentSearch).where(
                RecentSearch.user_id == user.id, func.lower(RecentSearch.query) == query.lower()
            )
        )
        db.add(RecentSearch(user_id=user.id, query=query, filters=f.to_dict() or None))
        db.flush()
        stale = (
            select(RecentSearch.id)
            .where(RecentSearch.user_id == user.id)
            .order_by(desc(RecentSearch.created_at), desc(RecentSearch.id))
            .offset(RECENT_SEARCH_KEEP)
        )
        db.execute(delete(RecentSearch).where(RecentSearch.id.in_(stale)))
        db.commit()
    except SQLAlchemyError:
        logger.warning("Could not record recent search for user %s", user.id, exc_info=True)
        db.rollback()


# --------------------------------------------------------------------------- search

def _fetch_jobs_page(
    db: Session,
    conds: list[ColumnElement[bool]],
    order_by: list[Any],
    page: int,
    page_size: int,
) -> tuple[list[Job], int]:
    total = int(db.execute(_joined_jobs(func.count()).where(*conds)).scalar_one())
    if total == 0 or (page - 1) * page_size >= total:
        return [], total
    stmt = (
        select(Job)
        .join(Company, Company.id == Job.company_id)
        .where(*conds)
        .order_by(*order_by)
        .limit(page_size)
        .offset((page - 1) * page_size)
    )
    return list(db.scalars(stmt).all()), total


def _date_order() -> list[Any]:
    return [Job.posted_at.desc().nulls_last(), Job.id]


def _search(
    db: Session,
    f: JobSearchFilters,
    page: int,
    page_size: int,
    sort: str | None,
    user: User | None,
    extra: tuple[ColumnElement[bool], ...] = (),
    with_facets: bool = True,
) -> tuple[list[dict[str, Any]], int, dict[str, Any]]:
    now = _now()
    tq = _text_query(db, f.q)
    use_relevance = tq is not None and (sort or "relevance") == "relevance"
    order_by = [desc(tq.score), *_date_order()] if use_relevance and tq is not None else _date_order()
    jobs, total = _fetch_jobs_page(db, _where_for(f, tq, now, extra=extra), order_by, page, page_size)
    items = serialize_jobs(db, jobs, user, query=f.q)
    facets = _compute_facets(db, f, tq, now, extra) if with_facets else {}
    return items, total, facets


def search_jobs(
    db: Session,
    filters: JobSearchFilters,
    page: int,
    page_size: int,
    sort: str | None,
    user: User | None,
    record: bool = True,
) -> tuple[list[dict[str, Any]], int, dict[str, Any]]:
    """Run a job search. Returns (list objects, total, facets). Authenticated first-page searches
    with a keyword are stored as the user's recent searches."""
    items, total, facets = _search(db, filters, page, page_size, sort, user)
    if record and user is not None and page == 1 and tokenize(filters.q):
        _record_recent_search(db, user, filters)
    return items, total, facets


# --------------------------------------------------------------------------- typeahead

def _rank(column_lower: ColumnElement, q_lower: str) -> tuple[ColumnElement, ColumnElement[bool]]:
    esc = _like_escape(q_lower)
    prefix = column_lower.like(f"{esc}%", escape="\\")
    word = column_lower.like(f"% {esc}%", escape="\\")
    conds: list[ColumnElement[bool]] = [prefix, word]
    fuzzy = func.word_similarity(q_lower, column_lower)
    if len(q_lower) >= 3:
        conds.append(fuzzy >= 0.4)
    rank = case((prefix, 3.0), (word, 2.0), else_=fuzzy)
    return rank, or_(*conds)


def _suggest_jobs(db: Session, q: str, limit: int) -> list[str]:
    title = func.lower(Job.title)
    rank, cond = _rank(title, q)
    best = func.max(rank).label("r")
    stmt = (
        _joined_jobs(func.min(Job.title).label("t"), best)
        .where(*visible_job_conditions(), cond)
        .group_by(title)
        .order_by(desc(best), desc(func.count()), func.min(Job.title))
        .limit(limit)
    )
    return [t for t, _ in db.execute(stmt).all()]


def _suggest_skills(db: Session, q: str, limit: int) -> list[str]:
    name = func.lower(Skill.name)
    rank, cond = _rank(name, q)
    synonym_prefix = func.lower(cast(Skill.synonyms, Text)).like(f'%"{_like_escape(q)}%', escape="\\")
    stmt = (
        select(Skill.name)
        .where(Skill.is_active.is_(True), or_(cond, synonym_prefix))
        .order_by(desc(case((synonym_prefix, func.greatest(rank, 2.5)), else_=rank)), Skill.name)
        .limit(limit)
    )
    return list(db.scalars(stmt).all())


def _suggest_companies(db: Session, q: str, limit: int) -> list[dict[str, Any]]:
    name = func.lower(Company.name)
    rank, cond = _rank(name, q)
    stmt = (
        select(Company.id, Company.name, Company.logo_url)
        .where(Company.status == CompanyStatus.APPROVED, Company.deleted_at.is_(None), cond)
        .order_by(desc(rank), Company.name)
        .limit(limit)
    )
    return [{"id": cid, "name": n, "logoUrl": logo} for cid, n, logo in db.execute(stmt).all()]


def _suggest_locations(db: Session, q: str, limit: int) -> list[str]:
    name = func.lower(Location.name)
    rank, cond = _rank(name, q)
    best = func.max(rank).label("r")
    stmt = (
        select(func.min(Location.name).label("n"), best)
        .where(cond)
        .group_by(name)
        .order_by(desc(best), func.min(Location.name))
        .limit(limit)
    )
    return [n for n, _ in db.execute(stmt).all()]


def suggest(db: Session, type: str | None, q: str, limit: int = 10) -> list[Any] | dict[str, list[Any]]:  # noqa: A002
    """Typeahead: prefix + trigram matching. With a type returns a list; otherwise a grouped dict."""
    needle = (q or "").strip().lower()[:100]
    handlers = {
        "job": ("jobs", _suggest_jobs),
        "skill": ("skills", _suggest_skills),
        "company": ("companies", _suggest_companies),
        "location": ("locations", _suggest_locations),
    }
    if type in handlers:
        return handlers[type][1](db, needle, limit) if needle else []
    return {key: (fn(db, needle, limit) if needle else []) for key, fn in handlers.values()}


# --------------------------------------------------------------------------- recommendations

def _profile_signals(db: Session, user: User) -> dict[str, Any]:
    profile = db.get(JobSeekerProfile, user.id)
    skills = [
        n.lower()
        for n in db.scalars(
            select(Skill.name).join(ProfileSkill, ProfileSkill.skill_id == Skill.id).where(ProfileSkill.user_id == user.id)
        ).all()
    ]
    locations: list[str] = []
    experience = 0.0
    desired: dict[str, str | None] = {"industry": None, "role": None, "department": None}
    if profile is not None:
        for loc in [*(profile.preferred_locations or []), *(profile.desired_locations or []), profile.current_location]:
            if loc and loc.strip().lower() not in locations:
                locations.append(loc.strip().lower())
        experience = float(profile.experience_years or 0) + float(profile.experience_months or 0) / 12
        desired = {
            "industry": (profile.desired_industry or "").strip().lower() or None,
            "role": (profile.desired_role_category or "").strip().lower() or None,
            "department": (profile.desired_department or "").strip().lower() or None,
        }
    return {"skills": skills, "locations": locations, "experience": experience, "desired": desired}


def recommended(db: Session, user: User, page: int, page_size: int) -> tuple[list[dict[str, Any]], int]:
    """Active jobs scored in SQL by skill overlap, experience fit, locations and desired role/industry."""
    sig = _profile_signals(db, user)
    skills: list[str] = sig["skills"]
    desired = sig["desired"]

    overlap = _skill_overlap(func.array_cat(Job.required_skills, Job.preferred_skills), skills)
    parts: list[ColumnElement] = [literal(3.0) * overlap]
    relevance: list[ColumnElement[bool]] = [overlap > 0] if skills else []
    if sig["locations"]:
        loc_match = _array_overlap(_lower_locations(), sig["locations"])
        parts.append(case((loc_match, 2.0), else_=0.0))
        relevance.append(loc_match)
    for key, column, weight in (
        ("industry", Job.industry, 1.0),
        ("role", Job.role_category, 1.0),
        ("department", Job.department, 1.0),
    ):
        if desired[key]:
            match = func.lower(column) == desired[key]
            parts.append(case((match, weight), else_=0.0))
            relevance.append(match)
    x = Decimal(str(round(sig["experience"], 1)))
    fit = and_(
        or_(Job.experience_min.is_(None), Job.experience_min <= x),
        or_(Job.experience_max.is_(None), Job.experience_max >= x),
    )
    parts.append(case((fit, 1.5), else_=0.0))
    score = reduce(lambda a, b: a + b, parts)

    extra: list[ColumnElement[bool]] = [
        Job.id.not_in(select(Application.job_id).where(Application.user_id == user.id)),
        Job.company_id.not_in(select(HiddenCompany.company_id).where(HiddenCompany.user_id == user.id)),
    ]
    if relevance:
        extra.append(or_(*relevance))
    conds = visible_job_conditions() + extra
    jobs, total = _fetch_jobs_page(db, conds, [desc(score), *_date_order()], page, page_size)
    return serialize_jobs(db, jobs, user), total


def based_on_recent_searches(
    db: Session, user: User, page: int, page_size: int
) -> tuple[list[dict[str, Any]], int]:
    """Jobs matching the user's latest search keywords (same engine), excluding applied jobs."""
    queries = [
        q
        for q in db.scalars(
            select(RecentSearch.query)
            .where(RecentSearch.user_id == user.id, RecentSearch.query.is_not(None), RecentSearch.query != "")
            .order_by(desc(RecentSearch.created_at))
            .limit(RECENT_SEARCH_USED)
        ).all()
        if q
    ]
    if not queries:
        return [], 0
    flt = JobSearchFilters(q=" ".join(queries))
    applied = Job.id.not_in(select(Application.job_id).where(Application.user_id == user.id))
    items, total, _ = _search(db, flt, page, page_size, "relevance", user, extra=(applied,), with_facets=False)
    return items, total


# --------------------------------------------------------------------------- similar / company jobs

def similar(db: Session, job: Job, user: User | None = None, limit: int = 10) -> list[dict[str, Any]]:
    """Active jobs sharing skills / industry / a similar title, excluding the job itself."""
    skills = [s.lower() for s in [*(job.required_skills or []), *(job.preferred_skills or [])]]
    title_sim = func.similarity(func.lower(Job.title), (job.title or "").lower())
    overlap = _skill_overlap(func.array_cat(Job.required_skills, Job.preferred_skills), skills)
    industry = (job.industry or "").strip().lower()
    same_industry = case((func.lower(Job.industry) == industry, 1.0), else_=0.0) if industry else literal(0.0)
    signals = [title_sim >= 0.3]
    if skills:
        signals.append(overlap > 0)
    if industry:
        signals.append(func.lower(Job.industry) == industry)
    score = literal(3.0) * title_sim + literal(1.0) * overlap + same_industry
    conds = visible_job_conditions() + [Job.id != job.id, or_(*signals)]
    stmt = (
        select(Job)
        .join(Company, Company.id == Job.company_id)
        .where(*conds)
        .order_by(desc(score), *_date_order())
        .limit(limit)
    )
    return serialize_jobs(db, list(db.scalars(stmt).all()), user)


def company_jobs(
    db: Session,
    company_id: uuid.UUID,
    user: User | None,
    page: int,
    page_size: int,
    exclude_job_id: uuid.UUID | None = None,
) -> tuple[list[dict[str, Any]], int]:
    """A company's active, publicly visible jobs (newest first), optionally excluding one job."""
    conds = visible_job_conditions() + [Job.company_id == company_id]
    if exclude_job_id is not None:
        conds.append(Job.id != exclude_job_id)
    jobs, total = _fetch_jobs_page(db, conds, _date_order(), page, page_size)
    return serialize_jobs(db, jobs, user), total


__all__ = [
    "JobSearchFilters",
    "based_on_recent_searches",
    "company_jobs",
    "company_ratings",
    "expand_synonyms",
    "make_snippet",
    "recommended",
    "saved_and_applied",
    "search_jobs",
    "serialize_jobs",
    "similar",
    "split_csv",
    "suggest",
    "tokenize",
    "visible_job_conditions",
]
