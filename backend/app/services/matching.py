"""Skill matching and profile completeness scoring."""

from __future__ import annotations

import logging
import uuid
from collections.abc import Iterable
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.accounts import User
from app.models.master import Skill
from app.models.profile import (
    Certification,
    Education,
    Employment,
    JobSeekerProfile,
    ProfileSkill,
    Project,
    Resume,
)

logger = logging.getLogger(__name__)

# (key, weight, suggestion). Weights sum to 100.
COMPLETENESS_SECTIONS: tuple[tuple[str, int, str], ...] = (
    ("basics", 10, "Add your mobile number, current location and work status"),
    ("headline", 10, "Add a profile headline that summarises your expertise"),
    ("summary", 5, "Write a short profile summary"),
    ("resume", 15, "Upload your resume"),
    ("skills", 15, "Add your key skills"),
    ("employment", 15, "Add your employment history"),
    ("education", 10, "Add your education details"),
    ("projects", 5, "Add projects or certifications to showcase your work"),
    ("preferences", 5, "Set your career preferences"),
    ("photo", 5, "Upload a profile photo"),
    ("onlineProfiles", 5, "Link your LinkedIn, GitHub or portfolio"),
)


def _norm(value: str) -> str:
    return value.strip().casefold()


def match_score(job_skills: Iterable[str] | None, candidate_skills: Iterable[str] | None) -> dict[str, Any]:
    """Compare required skills to candidate skills (case-insensitive).

    Empty requirement -> 100 %. percentage = round(100 * matching / required).
    """
    required: list[str] = []
    seen: set[str] = set()
    for skill in job_skills or []:
        key = _norm(skill) if isinstance(skill, str) else ""
        if key and key not in seen:
            seen.add(key)
            required.append(skill.strip())
    if not required:
        return {"percentage": 100, "matchingSkills": [], "missingSkills": []}
    have = {_norm(s) for s in (candidate_skills or []) if isinstance(s, str)}
    matching = [s for s in required if _norm(s) in have]
    missing = [s for s in required if _norm(s) not in have]
    return {
        "percentage": round(100 * len(matching) / len(required)),
        "matchingSkills": matching,
        "missingSkills": missing,
    }


def candidate_skill_names(db: Session, user_id: uuid.UUID) -> list[str]:
    """Master-skill names on the candidate's profile (single query)."""
    stmt = (
        select(Skill.name)
        .join(ProfileSkill, ProfileSkill.skill_id == Skill.id)
        .where(ProfileSkill.user_id == user_id)
        .order_by(Skill.name)
    )
    return list(db.scalars(stmt).all())


def completeness_from_counts(
    user: User,
    profile: JobSeekerProfile | None,
    *,
    resumes: int,
    skills: int,
    employments: int,
    educations: int,
    projects: int,
    certifications: int,
) -> dict[str, Any]:
    """Pure scoring function so callers that already loaded the rows avoid extra queries."""
    p = profile
    online = (p.online_profiles or {}) if p else {}
    checks: dict[str, bool] = {
        "basics": bool(
            user.name and user.email and user.mobile and p and p.current_location and p.work_status is not None
        ),
        "headline": bool(p and p.headline),
        "summary": bool(p and p.summary),
        "resume": resumes > 0,
        "skills": skills > 0,
        "employment": employments > 0,
        "education": educations > 0,
        "projects": (projects + certifications) > 0,
        "preferences": bool(
            p
            and (
                p.desired_industry
                or p.desired_department
                or p.desired_role_category
                or p.desired_job_type
                or p.desired_employment_type
                or p.desired_shift
                or p.desired_locations
            )
        ),
        "photo": bool(p and p.photo_url),
        "onlineProfiles": any(online.get(k) for k in ("linkedin", "github", "portfolio")),
    }
    score = 0
    missing: list[str] = []
    suggestions: list[str] = []
    for key, weight, suggestion in COMPLETENESS_SECTIONS:
        if checks[key]:
            score += weight
        else:
            missing.append(key)
            suggestions.append(suggestion)
    return {"percentage": score, "missingSections": missing, "suggestions": suggestions}


def profile_completeness(db: Session, user_id: uuid.UUID) -> dict[str, Any]:
    """Completeness percentage, missing sections and suggestions for a seeker."""
    user = db.get(User, user_id)
    if user is None:
        return {
            "percentage": 0,
            "missingSections": [k for k, _, _ in COMPLETENESS_SECTIONS],
            "suggestions": [s for _, _, s in COMPLETENESS_SECTIONS],
        }
    profile = db.get(JobSeekerProfile, user_id)

    def count(model: Any) -> Any:
        return select(func.count()).select_from(model).where(model.user_id == user_id).scalar_subquery()

    row = db.execute(
        select(
            count(Resume),
            count(ProfileSkill),
            count(Employment),
            count(Education),
            count(Project),
            count(Certification),
        )
    ).one()
    return completeness_from_counts(
        user,
        profile,
        resumes=row[0],
        skills=row[1],
        employments=row[2],
        educations=row[3],
        projects=row[4],
        certifications=row[5],
    )
