"""Business logic for the job-seeker profile: basics, skills, child records, privacy, files."""

from __future__ import annotations

import logging
import os
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any, BinaryIO

from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.config import settings
from app.core.errors import AppError, BadRequestError, ConflictError, NotFoundError
from app.models.accounts import User
from app.models.company import Company
from app.models.master import Skill
from app.models.profile import (
    Certification,
    Education,
    Employment,
    HiddenCompany,
    JobSeekerProfile,
    ProfileSkill,
    ProfileView,
    Project,
    Resume,
)
from app.schemas.profile import (
    CareerPreferencesUpdate,
    LanguageItem,
    OnlineProfilesUpdate,
    PrivacyUpdate,
    ProfileUpdate,
    SkillItem,
)
from app.services import matching
from app.services.resume_parser import get_parser

logger = logging.getLogger(__name__)

PHOTO_TYPES: dict[str, set[str]] = {
    "png": {"image/png"},
    "jpg": {"image/jpeg", "image/jpg", "image/pjpeg"},
    "jpeg": {"image/jpeg", "image/jpg", "image/pjpeg"},
    "webp": {"image/webp"},
}
RESUME_TYPES: dict[str, set[str]] = {
    "pdf": {"application/pdf", "application/x-pdf"},
    "doc": {"application/msword"},
    "docx": {"application/vnd.openxmlformats-officedocument.wordprocessingml.document"},
}
GENERIC_TYPES = {"application/octet-stream", "binary/octet-stream"}
PHOTO_URL_PREFIX = "/api/v1/files/photos/"


def invalid(field: str, message: str) -> AppError:
    return AppError(422, "VALIDATION_ERROR", message, [{"field": field, "message": message}])


# =========================================================================== profile row
def get_or_create_profile(db: Session, user_id: uuid.UUID) -> JobSeekerProfile:
    """Return the seeker's profile row, creating (flushing, not committing) it when missing."""
    profile = db.get(JobSeekerProfile, user_id)
    if profile is not None:
        return profile
    try:
        with db.begin_nested():
            profile = JobSeekerProfile(user_id=user_id)
            db.add(profile)
    except IntegrityError:
        # concurrent creation by another request
        profile = db.get(JobSeekerProfile, user_id)
        if profile is None:
            raise
    return profile


# =========================================================================== serializers
def serialize_skill(ps: ProfileSkill, name: str) -> dict[str, Any]:
    return {
        "id": ps.id,
        "skillId": ps.skill_id,
        "name": name,
        "yearsOfExperience": ps.years_of_experience,
    }


def serialize_employment(e: Employment) -> dict[str, Any]:
    return {
        "id": e.id,
        "companyName": e.company_name,
        "designation": e.designation,
        "startDate": e.start_date,
        "endDate": e.end_date,
        "isCurrent": bool(e.is_current),
        "description": e.description,
        "location": e.location,
    }


def serialize_education(e: Education) -> dict[str, Any]:
    return {
        "id": e.id,
        "degree": e.degree,
        "specialization": e.specialization,
        "institute": e.institute,
        "startYear": e.start_year,
        "endYear": e.end_year,
        "grade": e.grade,
    }


def serialize_project(p: Project) -> dict[str, Any]:
    return {
        "id": p.id,
        "title": p.title,
        "description": p.description,
        "url": p.url,
        "startDate": p.start_date,
        "endDate": p.end_date,
        "skills": list(p.skills or []),
    }


def serialize_certification(c: Certification) -> dict[str, Any]:
    return {
        "id": c.id,
        "name": c.name,
        "issuer": c.issuer,
        "issuedDate": c.issued_date,
        "expiryDate": c.expiry_date,
        "credentialUrl": c.credential_url,
    }


def serialize_resume(r: Resume) -> dict[str, Any]:
    return {
        "id": r.id,
        "fileName": r.file_name,
        "contentType": r.content_type,
        "sizeBytes": r.size_bytes,
        "isDefault": bool(r.is_default),
        "parsedSkills": list(r.parsed_skills or []),
        "uploadedAt": r.created_at,
        "createdAt": r.created_at,
    }


def online_profiles_dict(profile: JobSeekerProfile) -> dict[str, Any]:
    stored = profile.online_profiles or {}
    return {k: stored.get(k) for k in ("linkedin", "github", "portfolio")}


def career_preferences_dict(profile: JobSeekerProfile) -> dict[str, Any]:
    return {
        "desiredIndustry": profile.desired_industry,
        "desiredDepartment": profile.desired_department,
        "functionalArea": profile.desired_department,
        "desiredRoleCategory": profile.desired_role_category,
        "desiredJobType": profile.desired_job_type,
        "desiredEmploymentType": profile.desired_employment_type,
        "desiredShift": profile.desired_shift,
        "desiredLocations": list(profile.desired_locations or []),
    }


def privacy_dict(profile: JobSeekerProfile) -> dict[str, Any]:
    return {"visibility": profile.visibility, "activelyLooking": bool(profile.actively_looking)}


# =========================================================================== loaders
def list_skills(db: Session, user_id: uuid.UUID) -> list[dict[str, Any]]:
    rows = db.execute(
        select(ProfileSkill, Skill.name)
        .join(Skill, Skill.id == ProfileSkill.skill_id)
        .where(ProfileSkill.user_id == user_id)
        .order_by(func.lower(Skill.name))
    ).all()
    return [serialize_skill(ps, name) for ps, name in rows]


def list_hidden_companies(db: Session, user_id: uuid.UUID) -> list[dict[str, Any]]:
    rows = db.execute(
        select(HiddenCompany.company_id, Company.name)
        .join(Company, Company.id == HiddenCompany.company_id)
        .where(HiddenCompany.user_id == user_id)
        .order_by(func.lower(Company.name))
    ).all()
    return [{"companyId": cid, "name": name} for cid, name in rows]


def list_resumes(db: Session, user_id: uuid.UUID) -> list[Resume]:
    return list(
        db.scalars(
            select(Resume).where(Resume.user_id == user_id).order_by(Resume.is_default.desc(), Resume.created_at.desc())
        ).all()
    )


def build_profile(db: Session, user: User) -> dict[str, Any]:
    """Full profile payload (a fixed number of queries regardless of data size)."""
    profile = get_or_create_profile(db, user.id)
    skills = list_skills(db, user.id)
    employments = list_children(db, EMPLOYMENT, user.id)
    educations = list_children(db, EDUCATION, user.id)
    projects = list_children(db, PROJECT, user.id)
    certifications = list_children(db, CERTIFICATION, user.id)
    resumes = list_resumes(db, user.id)
    completeness = matching.completeness_from_counts(
        user,
        profile,
        resumes=len(resumes),
        skills=len(skills),
        employments=len(employments),
        educations=len(educations),
        projects=len(projects),
        certifications=len(certifications),
    )
    return {
        "id": user.id,
        "userId": user.id,
        "name": user.name,
        "email": user.email,
        "mobile": user.mobile,
        "mobileVerified": bool(user.mobile_verified),
        "emailVerified": bool(user.email_verified),
        "headline": profile.headline,
        "summary": profile.summary,
        "currentLocation": profile.current_location,
        "preferredLocations": list(profile.preferred_locations or []),
        "dob": profile.dob,
        "gender": profile.gender,
        "photoUrl": profile.photo_url,
        "experienceYears": profile.experience_years,
        "experienceMonths": profile.experience_months,
        "noticePeriod": profile.notice_period,
        "currentCtc": profile.current_ctc,
        "expectedCtc": profile.expected_ctc,
        "workStatus": profile.work_status,
        "skills": skills,
        "employments": [serialize_employment(e) for e in employments],
        "educations": [serialize_education(e) for e in educations],
        "projects": [serialize_project(p) for p in projects],
        "certifications": [serialize_certification(c) for c in certifications],
        "languages": list(profile.languages or []),
        "onlineProfiles": online_profiles_dict(profile),
        "careerPreferences": career_preferences_dict(profile),
        "visibility": profile.visibility,
        "activelyLooking": bool(profile.actively_looking),
        "hiddenCompanies": list_hidden_companies(db, user.id),
        "resumes": [serialize_resume(r) for r in resumes],
        "completeness": completeness,
        "createdAt": profile.created_at,
        "updatedAt": profile.updated_at,
    }


# =========================================================================== basics update
_PROFILE_SIMPLE_FIELDS = (
    "headline",
    "summary",
    "current_location",
    "dob",
    "gender",
    "notice_period",
    "current_ctc",
    "expected_ctc",
    "work_status",
)


def update_profile(db: Session, user: User, data: ProfileUpdate) -> None:
    """Apply a partial update; commits. Raises AppError on rule violations."""
    fields = data.model_fields_set
    profile = get_or_create_profile(db, user.id)

    if "email" in fields and data.email is not None and data.email.lower() != user.email.lower():
        raise BadRequestError("Email address cannot be changed")
    if "name" in fields:
        if not data.name:
            raise invalid("name", "name cannot be empty")
        user.name = data.name
    if "mobile" in fields:
        if not data.mobile:
            raise invalid("mobile", "mobile cannot be empty")
        if data.mobile != user.mobile:
            taken = db.scalar(select(User.id).where(User.mobile == data.mobile, User.id != user.id))
            if taken is not None:
                raise ConflictError("Mobile number is already registered")
            user.mobile = data.mobile
            user.mobile_verified = False
    for attr in ("experience_years", "experience_months"):
        if attr in fields:
            value = getattr(data, attr)
            if value is None:
                raise invalid(attr, f"{attr} cannot be null")
            setattr(profile, attr, value)
    if "preferred_locations" in fields:
        profile.preferred_locations = list(data.preferred_locations or [])
    for attr in _PROFILE_SIMPLE_FIELDS:
        if attr in fields:
            setattr(profile, attr, getattr(data, attr))
    if "skills" in fields and data.skills is not None:
        _replace_skills(db, user.id, data.skills)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        logger.info("Profile update integrity error: %s", exc.orig)
        raise ConflictError("Mobile number is already registered") from exc


# =========================================================================== skills
def _skill_lookup(db: Session) -> tuple[dict[uuid.UUID, Skill], dict[str, Skill]]:
    skills = list(db.scalars(select(Skill).where(Skill.is_active.is_(True))).all())
    by_id = {s.id: s for s in skills}
    by_name: dict[str, Skill] = {s.name.strip().casefold(): s for s in skills}
    for s in skills:
        for syn in s.synonyms or []:
            if isinstance(syn, str) and syn.strip():
                by_name.setdefault(syn.strip().casefold(), s)
    return by_id, by_name


def resolve_skills(db: Session, items: Sequence[SkillItem]) -> dict[uuid.UUID, Decimal | None]:
    """Map request items to master skill ids (ordered, last duplicate wins). Unknown -> 422."""
    if not items:
        return {}
    by_id, by_name = _skill_lookup(db)
    resolved: dict[uuid.UUID, Decimal | None] = {}
    errors: list[dict[str, str]] = []
    for idx, item in enumerate(items):
        skill: Skill | None
        if item.skill_id is not None:
            skill = by_id.get(item.skill_id)
            label = str(item.skill_id)
        else:
            skill = by_name.get((item.name or "").casefold())
            label = item.name or ""
        if skill is None:
            errors.append({"field": f"skills.{idx}", "message": f"Unknown skill: {label}"})
            continue
        resolved[skill.id] = item.years_of_experience
    if errors:
        raise AppError(422, "VALIDATION_ERROR", "One or more skills are not in the master skill list", errors)
    return resolved


def _replace_skills(db: Session, user_id: uuid.UUID, items: Sequence[SkillItem]) -> None:
    resolved = resolve_skills(db, items)
    existing = {ps.skill_id: ps for ps in db.scalars(select(ProfileSkill).where(ProfileSkill.user_id == user_id)).all()}
    stale = [sid for sid in existing if sid not in resolved]
    if stale:
        db.execute(delete(ProfileSkill).where(ProfileSkill.user_id == user_id, ProfileSkill.skill_id.in_(stale)))
    for sid, years in resolved.items():
        current = existing.get(sid)
        if current is not None:
            current.years_of_experience = years
        else:
            db.add(ProfileSkill(user_id=user_id, skill_id=sid, years_of_experience=years))
    db.flush()


def replace_skills(db: Session, user_id: uuid.UUID, items: Sequence[SkillItem]) -> list[dict[str, Any]]:
    get_or_create_profile(db, user_id)
    _replace_skills(db, user_id, items)
    db.commit()
    return list_skills(db, user_id)


def add_skill(db: Session, user_id: uuid.UUID, item: SkillItem) -> tuple[dict[str, Any], bool]:
    """Add (or update the years of) one skill. Returns (serialized, created)."""
    get_or_create_profile(db, user_id)
    skill_id = next(iter(resolve_skills(db, [item])))
    existing = db.scalar(select(ProfileSkill).where(ProfileSkill.user_id == user_id, ProfileSkill.skill_id == skill_id))
    created = existing is None
    if existing is None:
        existing = ProfileSkill(user_id=user_id, skill_id=skill_id, years_of_experience=item.years_of_experience)
        db.add(existing)
    elif "years_of_experience" in item.model_fields_set:
        existing.years_of_experience = item.years_of_experience
    db.commit()
    name = db.scalar(select(Skill.name).where(Skill.id == skill_id)) or ""
    return serialize_skill(existing, name), created


def remove_skill(db: Session, user_id: uuid.UUID, skill_id: uuid.UUID) -> None:
    """Delete by master skill id (a ProfileSkill row id is accepted as well)."""
    result = db.execute(
        delete(ProfileSkill).where(
            ProfileSkill.user_id == user_id,
            (ProfileSkill.skill_id == skill_id) | (ProfileSkill.id == skill_id),
        )
    )
    if result.rowcount == 0:
        db.rollback()
        raise NotFoundError("Skill not found on your profile")
    db.commit()


# =========================================================================== child record CRUD
@dataclass(frozen=True)
class ChildSpec:
    model: Any
    fields: tuple[str, ...]
    required: tuple[str, ...]
    order_by: Callable[[], list[Any]]
    validate: Callable[[Any], None]
    label: str


def _validate_employment(e: Employment) -> None:
    if e.is_current and e.end_date is not None:
        raise invalid("endDate", "endDate must be empty for a current employment")
    if e.start_date and e.end_date and e.end_date < e.start_date:
        raise invalid("endDate", "endDate cannot be before startDate")


def _validate_education(e: Education) -> None:
    if e.start_year and e.end_year and e.end_year < e.start_year:
        raise invalid("endYear", "endYear cannot be before startYear")


def _validate_project(p: Project) -> None:
    if p.start_date and p.end_date and p.end_date < p.start_date:
        raise invalid("endDate", "endDate cannot be before startDate")


def _validate_certification(c: Certification) -> None:
    if c.issued_date and c.expiry_date and c.expiry_date < c.issued_date:
        raise invalid("expiryDate", "expiryDate cannot be before issuedDate")


EMPLOYMENT = ChildSpec(
    Employment,
    ("company_name", "designation", "start_date", "end_date", "is_current", "description", "location"),
    ("company_name", "designation", "is_current"),
    lambda: [Employment.is_current.desc(), Employment.start_date.desc().nulls_last(), Employment.id],
    _validate_employment,
    "Employment",
)
EDUCATION = ChildSpec(
    Education,
    ("degree", "specialization", "institute", "start_year", "end_year", "grade"),
    ("degree",),
    lambda: [Education.end_year.desc().nulls_last(), Education.id],
    _validate_education,
    "Education",
)
PROJECT = ChildSpec(
    Project,
    ("title", "description", "url", "start_date", "end_date", "skills"),
    ("title", "skills"),
    lambda: [Project.start_date.desc().nulls_last(), Project.id],
    _validate_project,
    "Project",
)
CERTIFICATION = ChildSpec(
    Certification,
    ("name", "issuer", "issued_date", "expiry_date", "credential_url"),
    ("name",),
    lambda: [Certification.issued_date.desc().nulls_last(), Certification.id],
    _validate_certification,
    "Certification",
)

CHILD_SERIALIZERS: dict[str, Callable[[Any], dict[str, Any]]] = {
    "Employment": serialize_employment,
    "Education": serialize_education,
    "Project": serialize_project,
    "Certification": serialize_certification,
}


def serialize_child(spec: ChildSpec, obj: Any) -> dict[str, Any]:
    return CHILD_SERIALIZERS[spec.label](obj)


def list_children(db: Session, spec: ChildSpec, user_id: uuid.UUID) -> list[Any]:
    return list(db.scalars(select(spec.model).where(spec.model.user_id == user_id).order_by(*spec.order_by())).all())


def create_child(db: Session, spec: ChildSpec, user_id: uuid.UUID, data: Any) -> Any:
    get_or_create_profile(db, user_id)
    obj = spec.model(user_id=user_id, **{f: getattr(data, f) for f in spec.fields})
    spec.validate(obj)
    db.add(obj)
    db.commit()
    return obj


def _get_owned(db: Session, spec: ChildSpec, user_id: uuid.UUID, item_id: uuid.UUID) -> Any:
    obj = db.scalar(select(spec.model).where(spec.model.id == item_id, spec.model.user_id == user_id))
    if obj is None:
        raise NotFoundError(f"{spec.label} not found")
    return obj


def update_child(db: Session, spec: ChildSpec, user_id: uuid.UUID, item_id: uuid.UUID, data: Any) -> Any:
    obj = _get_owned(db, spec, user_id, item_id)
    for field in data.model_fields_set:
        if field not in spec.fields:
            continue
        value = getattr(data, field)
        if value is None and field in spec.required:
            raise invalid(field, f"{field} cannot be null")
        setattr(obj, field, value)
    spec.validate(obj)
    db.commit()
    return obj


def delete_child(db: Session, spec: ChildSpec, user_id: uuid.UUID, item_id: uuid.UUID) -> None:
    obj = _get_owned(db, spec, user_id, item_id)
    db.delete(obj)
    db.commit()


# =========================================================================== languages / links / prefs / privacy
def set_languages(db: Session, user_id: uuid.UUID, items: Sequence[LanguageItem]) -> list[dict[str, Any]]:
    profile = get_or_create_profile(db, user_id)
    seen: set[str] = set()
    languages: list[dict[str, Any]] = []
    for item in items:
        key = item.name.casefold()
        if key in seen:
            continue
        seen.add(key)
        languages.append({"name": item.name, "proficiency": item.proficiency})
    profile.languages = languages
    db.commit()
    return languages


def set_online_profiles(db: Session, user_id: uuid.UUID, data: OnlineProfilesUpdate) -> dict[str, Any]:
    profile = get_or_create_profile(db, user_id)
    merged = online_profiles_dict(profile)
    for key in data.model_fields_set:
        merged[key] = getattr(data, key)
    profile.online_profiles = {k: v for k, v in merged.items() if v}
    db.commit()
    return online_profiles_dict(profile)


def get_career_preferences(db: Session, user_id: uuid.UUID) -> dict[str, Any]:
    profile = get_or_create_profile(db, user_id)
    db.commit()
    return career_preferences_dict(profile)


def set_career_preferences(db: Session, user_id: uuid.UUID, data: CareerPreferencesUpdate) -> dict[str, Any]:
    profile = get_or_create_profile(db, user_id)
    for field in data.model_fields_set:
        value = getattr(data, field)
        if field == "desired_locations":
            value = list(value or [])
        elif field in ("desired_job_type", "desired_employment_type") and value is not None:
            value = value.value
        setattr(profile, field, value)
    db.commit()
    return career_preferences_dict(profile)


def get_privacy(db: Session, user_id: uuid.UUID) -> dict[str, Any]:
    profile = get_or_create_profile(db, user_id)
    db.commit()
    return privacy_dict(profile)


def set_privacy(db: Session, user_id: uuid.UUID, data: PrivacyUpdate) -> dict[str, Any]:
    profile = get_or_create_profile(db, user_id)
    if "visibility" in data.model_fields_set and data.visibility is not None:
        profile.visibility = data.visibility
    if "actively_looking" in data.model_fields_set and data.actively_looking is not None:
        profile.actively_looking = data.actively_looking
    db.commit()
    return privacy_dict(profile)


def hide_company(db: Session, user_id: uuid.UUID, company_id: uuid.UUID) -> tuple[dict[str, Any], bool]:
    company = db.scalar(select(Company).where(Company.id == company_id, Company.deleted_at.is_(None)))
    if company is None:
        raise NotFoundError("Company not found")
    existing = db.scalar(
        select(HiddenCompany.id).where(HiddenCompany.user_id == user_id, HiddenCompany.company_id == company_id)
    )
    created = existing is None
    if created:
        try:
            with db.begin_nested():
                db.add(HiddenCompany(user_id=user_id, company_id=company_id))
        except IntegrityError:
            created = False  # concurrent duplicate: idempotent
        db.commit()
    return {"companyId": company.id, "name": company.name}, created


def unhide_company(db: Session, user_id: uuid.UUID, company_id: uuid.UUID) -> None:
    result = db.execute(
        delete(HiddenCompany).where(HiddenCompany.user_id == user_id, HiddenCompany.company_id == company_id)
    )
    if result.rowcount == 0:
        db.rollback()
        raise NotFoundError("Company is not in your hidden list")
    db.commit()


def views_statement(user_id: uuid.UUID) -> Any:
    """Select of (id, company_id, company_name, viewed_at); recruiter identity is never selected."""
    return (
        select(ProfileView.id, ProfileView.company_id, Company.name.label("company_name"), ProfileView.viewed_at)
        .outerjoin(Company, Company.id == ProfileView.company_id)
        .where(ProfileView.candidate_id == user_id)
        .order_by(ProfileView.viewed_at.desc(), ProfileView.id)
    )


def serialize_view(row: Any) -> dict[str, Any]:
    return {
        "id": row.id,
        "companyId": row.company_id,
        "companyName": row.company_name or "A company",
        "viewedAt": row.viewed_at,
    }


# =========================================================================== uploads
def _extension(filename: str) -> str:
    return os.path.splitext(filename or "")[1].lstrip(".").lower()


def _check_upload_type(
    filename: str, content_type: str | None, allowed: dict[str, set[str]], what: str
) -> str:
    ext = _extension(filename)
    if ext not in allowed:
        raise BadRequestError(
            f"Unsupported {what} type. Allowed: {', '.join(sorted(allowed))}", code="UNSUPPORTED_FILE_TYPE"
        )
    ctype = (content_type or "").split(";")[0].strip().lower()
    if ctype and ctype not in allowed[ext] and ctype not in GENERIC_TYPES:
        raise BadRequestError(
            f"Content type '{ctype}' does not match the {what} file extension", code="UNSUPPORTED_FILE_TYPE"
        )
    return ext


def _read_limited(stream: BinaryIO, limit: int, what: str) -> bytes:
    data = stream.read(limit + 1)
    if not data:
        raise BadRequestError(f"Uploaded {what} is empty")
    if len(data) > limit:
        raise AppError(413, "PAYLOAD_TOO_LARGE", f"{what.capitalize()} exceeds the maximum size of {limit} bytes")
    return data


def _write_file(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def _remove_file(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError as exc:
        logger.warning("Could not delete file %s: %s", path, exc)


def upload_root() -> Path:
    return Path(settings.upload_dir)


def save_photo(
    db: Session, user_id: uuid.UUID, filename: str, content_type: str | None, stream: BinaryIO
) -> dict[str, Any]:
    ext = _check_upload_type(filename, content_type, PHOTO_TYPES, "image")
    data = _read_limited(stream, settings.max_image_bytes, "image")
    profile = get_or_create_profile(db, user_id)
    name = f"{uuid.uuid4().hex}.{ext}"
    path = upload_root() / "photos" / name
    _write_file(path, data)
    old_url = profile.photo_url
    profile.photo_url = PHOTO_URL_PREFIX + name
    try:
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        _remove_file(path)
        raise
    if old_url and old_url.startswith(PHOTO_URL_PREFIX):
        _remove_file(upload_root() / "photos" / Path(old_url).name)
    return {"photoUrl": profile.photo_url}


def _master_skill_names(db: Session) -> list[str]:
    return list(db.scalars(select(Skill.name).where(Skill.is_active.is_(True)).order_by(Skill.name)).all())


def _run_parser(db: Session, resume: Resume) -> list[str]:
    try:
        result = get_parser().parse(resume.file_path, _master_skill_names(db))
    except OSError as exc:
        logger.warning("Resume %s could not be read for parsing: %s", resume.id, exc)
        return []
    return list(result.get("skills") or [])


def save_resume(
    db: Session,
    user_id: uuid.UUID,
    filename: str,
    content_type: str | None,
    stream: BinaryIO,
    make_default: bool,
) -> Resume:
    safe_name = os.path.basename((filename or "").replace("\\", "/"))[:255]
    ext = _check_upload_type(safe_name, content_type, RESUME_TYPES, "resume")
    data = _read_limited(stream, settings.max_resume_bytes, "resume")
    get_or_create_profile(db, user_id)
    has_any = db.scalar(select(func.count()).select_from(Resume).where(Resume.user_id == user_id)) or 0
    path = upload_root() / "resumes" / str(user_id) / f"{uuid.uuid4().hex}.{ext}"
    _write_file(path, data)
    try:
        default = make_default or has_any == 0
        if default:
            db.execute(update(Resume).where(Resume.user_id == user_id).values(is_default=False))
        resume = Resume(
            user_id=user_id,
            file_name=safe_name or f"resume.{ext}",
            file_path=str(path),
            content_type=(content_type or "").split(";")[0].strip().lower() or None,
            size_bytes=len(data),
            is_default=default,
            parsed_skills=[],
        )
        db.add(resume)
        db.flush()
        resume.parsed_skills = _run_parser(db, resume)
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        _remove_file(path)
        raise
    return resume


def get_owned_resume(db: Session, user_id: uuid.UUID, resume_id: uuid.UUID) -> Resume:
    resume = db.scalar(select(Resume).where(Resume.id == resume_id, Resume.user_id == user_id))
    if resume is None:
        raise NotFoundError("Resume not found")
    return resume


def resume_file_path(resume: Resume) -> Path:
    """Stored file path, verified to live under the uploads root and to exist."""
    path = Path(resume.file_path)
    root = (upload_root() / "resumes").resolve()
    resolved = path.resolve()
    if not resolved.is_relative_to(root) or not resolved.is_file():
        raise NotFoundError("Resume file is no longer available")
    return resolved


def set_default_resume(db: Session, user_id: uuid.UUID, resume_id: uuid.UUID) -> Resume:
    resume = get_owned_resume(db, user_id, resume_id)
    db.execute(update(Resume).where(Resume.user_id == user_id, Resume.id != resume.id).values(is_default=False))
    resume.is_default = True
    db.commit()
    return resume


def delete_resume(db: Session, user_id: uuid.UUID, resume_id: uuid.UUID) -> None:
    """Delete the row and file. Applications keep working (their resume_id is set NULL by the FK)."""
    resume = get_owned_resume(db, user_id, resume_id)
    was_default = bool(resume.is_default)
    path = Path(resume.file_path)
    db.delete(resume)
    db.flush()
    if was_default:
        newest = db.scalar(select(Resume).where(Resume.user_id == user_id).order_by(Resume.created_at.desc()).limit(1))
        if newest is not None:
            newest.is_default = True
    db.commit()
    root = (upload_root() / "resumes").resolve()
    if path.resolve().is_relative_to(root):
        _remove_file(path)


def parse_resume(db: Session, user_id: uuid.UUID, resume_id: uuid.UUID) -> dict[str, Any]:
    """Re-parse a resume and add the recognised master skills not yet on the profile."""
    resume = get_owned_resume(db, user_id, resume_id)
    resume_file_path(resume)  # 404 when the file is gone
    parsed = _run_parser(db, resume)
    resume.parsed_skills = parsed
    added: list[str] = []
    if parsed:
        by_name = {s.name.casefold(): s for s in db.scalars(select(Skill).where(Skill.name.in_(parsed))).all()}
        have = set(db.scalars(select(ProfileSkill.skill_id).where(ProfileSkill.user_id == user_id)).all())
        get_or_create_profile(db, user_id)
        for name in parsed:
            skill = by_name.get(name.casefold())
            if skill is not None and skill.id not in have:
                have.add(skill.id)
                db.add(ProfileSkill(user_id=user_id, skill_id=skill.id))
                added.append(skill.name)
    db.commit()
    return {"parsedSkills": parsed, "addedSkills": added}
