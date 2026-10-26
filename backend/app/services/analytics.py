"""Admin analytics: every figure is computed with grouped SQL (no per-row queries)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import Any

from sqlalchemy import Date, Select, and_, cast, exists, func, literal_column, or_, select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models.accounts import User
from app.models.applications import Application, StatusHistory
from app.models.company import Company
from app.models.enums import ApplicationStatus, JobStatus
from app.models.jobs import Job, JobView, RecentSearch

logger = logging.getLogger(__name__)

DEFAULT_RANGE_DAYS = 30
MAX_RANGE_DAYS = 366
TOP_N = 10

_SHORTLISTED_OR_BEYOND = (
    ApplicationStatus.SHORTLISTED,
    ApplicationStatus.INTERVIEW_SCHEDULED,
    ApplicationStatus.OFFERED,
    ApplicationStatus.HIRED,
)
_INTERVIEW = (ApplicationStatus.INTERVIEW_SCHEDULED,)
_HIRED = (ApplicationStatus.HIRED,)


@dataclass(frozen=True)
class DateRange:
    start_date: date
    end_date: date  # inclusive

    @property
    def start(self) -> datetime:
        return datetime.combine(self.start_date, time.min, tzinfo=timezone.utc)

    @property
    def end(self) -> datetime:
        """Exclusive upper bound."""
        return datetime.combine(self.end_date + timedelta(days=1), time.min, tzinfo=timezone.utc)

    def days(self) -> list[date]:
        return [self.start_date + timedelta(days=i) for i in range((self.end_date - self.start_date).days + 1)]


def resolve_range(date_from: date | None, date_to: date | None, today: date | None = None) -> DateRange:
    today = today or datetime.now(timezone.utc).date()
    end = date_to or today
    start = date_from or (end - timedelta(days=DEFAULT_RANGE_DAYS - 1))
    if start > end:
        raise AppError(
            422, "VALIDATION_ERROR", "Invalid date range",
            [{"field": "from", "message": "'from' must not be after 'to'"}],
        )
    if (end - start).days + 1 > MAX_RANGE_DAYS:
        raise AppError(
            422, "VALIDATION_ERROR", "Invalid date range",
            [{"field": "from", "message": f"range must not exceed {MAX_RANGE_DAYS} days"}],
        )
    return DateRange(start, end)


def _day(column: Any) -> Any:
    # literal (not bound) zone so SELECT and GROUP BY expressions are textually identical
    return cast(func.timezone(literal_column("'UTC'"), column), Date)


def _series(db: Session, stmt_builder: Select[Any], day_col: Any, rng: DateRange) -> list[dict[str, Any]]:
    """Run a grouped-by-day count and zero-fill the range."""
    rows = db.execute(stmt_builder.add_columns(day_col.label("d"), func.count().label("c")).group_by(day_col)).all()
    counts = {r.d: int(r.c) for r in rows}
    return [{"date": d.isoformat(), "count": counts.get(d, 0)} for d in rng.days()]


def _registrations(db: Session, rng: DateRange) -> dict[str, Any]:
    where = and_(User.created_at >= rng.start, User.created_at < rng.end)
    by_role = {
        str(role.value if hasattr(role, "value") else role): int(count)
        for role, count in db.execute(select(User.role, func.count()).where(where).group_by(User.role)).all()
    }
    series = _series(db, select().where(where), _day(User.created_at), rng)
    return {"total": sum(by_role.values()), "byRole": by_role, "series": series}


def _posted_at() -> Any:
    return func.coalesce(Job.posted_at, Job.created_at)


def _jobs_posted(db: Session, rng: DateRange) -> dict[str, Any]:
    where = and_(
        Job.deleted_at.is_(None),
        Job.status != JobStatus.DRAFT,
        _posted_at() >= rng.start,
        _posted_at() < rng.end,
    )
    series = _series(db, select().where(where), _day(_posted_at()), rng)
    return {"total": sum(p["count"] for p in series), "series": series}


def _applications(db: Session, rng: DateRange) -> dict[str, Any]:
    where = and_(Application.applied_at >= rng.start, Application.applied_at < rng.end)
    series = _series(db, select().where(where), _day(Application.applied_at), rng)
    return {"total": sum(p["count"] for p in series), "series": series}


def _active_users(db: Session, rng: DateRange) -> int:
    return int(
        db.scalar(
            select(func.count()).select_from(User).where(
                User.last_active_at >= rng.start, User.last_active_at < rng.end
            )
        )
        or 0
    )


def _top_keywords(db: Session, rng: DateRange) -> list[dict[str, Any]]:
    keyword = func.lower(func.trim(RecentSearch.query))
    rows = db.execute(
        select(keyword.label("k"), func.count().label("c"))
        .where(
            RecentSearch.created_at >= rng.start,
            RecentSearch.created_at < rng.end,
            RecentSearch.query.is_not(None),
            func.trim(RecentSearch.query) != "",
        )
        .group_by(keyword)
        .order_by(func.count().desc(), keyword)
        .limit(TOP_N)
    ).all()
    return [{"keyword": r.k, "count": int(r.c)} for r in rows]


def _top_companies(db: Session, rng: DateRange) -> list[dict[str, Any]]:
    jobs_sq = (
        select(Job.company_id.label("company_id"), func.count().label("jobs"))
        .where(
            Job.deleted_at.is_(None),
            Job.status != JobStatus.DRAFT,
            _posted_at() >= rng.start,
            _posted_at() < rng.end,
        )
        .group_by(Job.company_id)
        .subquery()
    )
    apps_sq = (
        select(Job.company_id.label("company_id"), func.count(Application.id).label("applications"))
        .join(Application, Application.job_id == Job.id)
        .where(Application.applied_at >= rng.start, Application.applied_at < rng.end)
        .group_by(Job.company_id)
        .subquery()
    )
    apps_col = func.coalesce(apps_sq.c.applications, 0)
    rows = db.execute(
        select(Company.id, Company.name, jobs_sq.c.jobs, apps_col.label("applications"))
        .join(jobs_sq, jobs_sq.c.company_id == Company.id)
        .outerjoin(apps_sq, apps_sq.c.company_id == Company.id)
        .where(Company.deleted_at.is_(None))
        .order_by(jobs_sq.c.jobs.desc(), apps_col.desc(), Company.name)
        .limit(TOP_N)
    ).all()
    return [
        {"companyId": r.id, "name": r.name, "jobs": int(r.jobs), "applications": int(r.applications)}
        for r in rows
    ]


def _reached(statuses: tuple[ApplicationStatus, ...]) -> Any:
    """Application is currently in, or was ever in, one of ``statuses``."""
    history = exists().where(StatusHistory.application_id == Application.id, StatusHistory.status.in_(statuses))
    return or_(Application.status.in_(statuses), history)


def _ratio(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 4) if denominator else 0.0


def _funnel(db: Session, rng: DateRange) -> dict[str, Any]:
    row = db.execute(
        select(
            func.count().label("applications"),
            func.count().filter(_reached(_SHORTLISTED_OR_BEYOND)).label("shortlisted"),
            func.count().filter(_reached(_INTERVIEW)).label("interviews"),
            func.count().filter(_reached(_HIRED)).label("hired"),
        ).where(Application.applied_at >= rng.start, Application.applied_at < rng.end)
    ).one()
    views = int(
        db.scalar(
            select(func.count()).select_from(JobView).where(
                JobView.view_date >= rng.start_date, JobView.view_date <= rng.end_date
            )
        )
        or 0
    )
    applications, shortlisted, interviews, hired = (int(row.applications), int(row.shortlisted),
                                                     int(row.interviews), int(row.hired))
    return {
        "counts": {
            "views": views,
            "applications": applications,
            "shortlisted": shortlisted,
            "interviews": interviews,
            "hired": hired,
        },
        "conversionRates": {
            "viewToApplication": min(_ratio(applications, views), 1.0),
            "applicationToShortlist": _ratio(shortlisted, applications),
            "shortlistToHire": _ratio(hired, shortlisted),
            "applicationToInterview": _ratio(interviews, applications),
        },
    }


def build_analytics(db: Session, rng: DateRange) -> dict[str, Any]:
    funnel = _funnel(db, rng)
    return {
        "from": rng.start_date,
        "to": rng.end_date,
        "registrations": _registrations(db, rng),
        "jobsPosted": _jobs_posted(db, rng),
        "applications": _applications(db, rng),
        "activeUsers": _active_users(db, rng),
        "topKeywords": _top_keywords(db, rng),
        "topHiringCompanies": _top_companies(db, rng),
        "conversionRates": funnel["conversionRates"],
        "funnel": funnel["counts"],
    }


CSV_HEADER = ["section", "metric", "value"]


def analytics_csv_rows(data: dict[str, Any]) -> list[list[Any]]:
    rows: list[list[Any]] = [
        ["range", "from", data["from"]],
        ["range", "to", data["to"]],
        ["registrations", "total", data["registrations"]["total"]],
    ]
    rows += [["registrations", f"role:{role}", n] for role, n in data["registrations"]["byRole"].items()]
    rows += [["registrationsSeries", p["date"], p["count"]] for p in data["registrations"]["series"]]
    rows.append(["jobsPosted", "total", data["jobsPosted"]["total"]])
    rows += [["jobsPostedSeries", p["date"], p["count"]] for p in data["jobsPosted"]["series"]]
    rows.append(["applications", "total", data["applications"]["total"]])
    rows += [["applicationsSeries", p["date"], p["count"]] for p in data["applications"]["series"]]
    rows.append(["activeUsers", "total", data["activeUsers"]])
    rows += [["topKeywords", k["keyword"], k["count"]] for k in data["topKeywords"]]
    for c in data["topHiringCompanies"]:
        rows.append(["topHiringCompanies", f"{c['name']} (jobs)", c["jobs"]])
        rows.append(["topHiringCompanies", f"{c['name']} (applications)", c["applications"]])
    rows += [["conversionRates", name, value] for name, value in data["conversionRates"].items()]
    rows += [["funnel", name, value] for name, value in data["funnel"].items()]
    return rows
