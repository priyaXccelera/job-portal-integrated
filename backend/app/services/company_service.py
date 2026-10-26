"""Recruiter company management: profile, logo/banner upload, team and invitations."""

from __future__ import annotations

import logging
import os
import uuid
from datetime import timedelta
from pathlib import Path
from typing import Any, BinaryIO, Literal

from sqlalchemy import Select, func, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.config import settings
from app.core.deps import RecruiterContext
from app.core.errors import AppError, BadRequestError, ConflictError, ForbiddenError, NotFoundError
from app.core.security import hash_token, new_refresh_token
from app.db import utcnow
from app.models.accounts import User
from app.models.company import Company, CompanyFollow, Invitation
from app.models.enums import InvitationStatus, UserRole
from app.models.jobs import Job
from app.schemas.recruiter import CompanyUpdate
from app.services import search as job_search
from app.services.job_index import reindex_job
from app.services.senders import SenderError, get_email_sender

logger = logging.getLogger(__name__)

ImageKind = Literal["logo", "banner"]
KIND_DIRS: dict[str, str] = {"logo": "logos", "banner": "banners"}
IMAGE_EXTENSIONS = {"png", "jpg", "jpeg", "webp"}
IMAGE_CONTENT_TYPES = {"image/png", "image/jpeg", "image/jpg", "image/webp"}
FILE_URL_PREFIX = "/api/v1/files/"


# ======================================================================================= helpers


def require_company_admin(ctx: RecruiterContext) -> None:
    if not ctx.is_company_admin:
        raise ForbiddenError("Only a company admin can perform this action")


def serialize_company(db: Session, company: Company, is_company_admin: bool | None = None) -> dict[str, Any]:
    rating, review_count = job_search.company_ratings(db, [company.id]).get(company.id, (None, 0))
    followers = db.scalar(
        select(func.count()).select_from(CompanyFollow).where(CompanyFollow.company_id == company.id)
    )
    recruiters = db.scalar(
        select(func.count())
        .select_from(User)
        .where(User.company_id == company.id, User.role == UserRole.RECRUITER, User.deleted_at.is_(None))
    )
    data: dict[str, Any] = {
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
        "verified": bool(company.verified),
        "status": company.status,
        "statusReason": company.status_reason,
        "credits": company.credits,
        "jobQuota": company.job_quota,
        "jobsPosted": company.jobs_posted,
        "quotaRemaining": max(company.job_quota - company.jobs_posted, 0),
        "rating": rating,
        "reviewCount": review_count,
        "followersCount": followers or 0,
        "recruitersCount": recruiters or 0,
        "createdAt": company.created_at,
        "updatedAt": company.updated_at,
    }
    if is_company_admin is not None:
        data["isCompanyAdmin"] = is_company_admin
    return data


# ======================================================================================= company profile


def update_company(db: Session, ctx: RecruiterContext, data: CompanyUpdate) -> dict[str, Any]:
    """Apply the supplied fields to the company (admin only); caller commits."""
    require_company_admin(ctx)
    company = ctx.company
    changes = data.model_dump(exclude_unset=True)
    name_changed = "name" in changes and changes["name"] != company.name
    for attr, value in changes.items():
        setattr(company, attr, value)  # JSONB columns are reassigned whole, never mutated in place
    db.flush()
    if name_changed:  # company name is part of the jobs' search vector
        for job_id in db.scalars(select(Job.id).where(Job.company_id == company.id, Job.deleted_at.is_(None))).all():
            reindex_job(db, job_id)
    return serialize_company(db, company, ctx.is_company_admin)


# ======================================================================================= images


def _sniff_image(data: bytes) -> str | None:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if data.startswith(b"\xff\xd8\xff"):
        return "jpg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    return None


def _remove_file(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError as exc:
        logger.warning("Could not delete file %s: %s", path, exc)


def save_company_image(
    db: Session,
    ctx: RecruiterContext,
    kind: ImageKind,
    filename: str | None,
    content_type: str | None,
    stream: BinaryIO,
) -> dict[str, Any]:
    """Validate and store a logo/banner for the company (admin only) and commit."""
    require_company_admin(ctx)
    ext = os.path.splitext(filename or "")[1].lstrip(".").lower()
    ctype = (content_type or "").split(";")[0].strip().lower()
    if ext not in IMAGE_EXTENSIONS or (ctype and ctype != "application/octet-stream" and ctype not in IMAGE_CONTENT_TYPES):
        raise BadRequestError(
            f"Unsupported image type. Allowed: {', '.join(sorted(IMAGE_EXTENSIONS))}", code="UNSUPPORTED_FILE_TYPE"
        )
    limit = settings.max_image_bytes
    data = stream.read(limit + 1)
    if not data:
        raise BadRequestError("Uploaded image is empty")
    if len(data) > limit:
        raise AppError(413, "PAYLOAD_TOO_LARGE", f"Image exceeds the maximum size of {limit} bytes")
    sniffed = _sniff_image(data)
    if sniffed is None:
        raise BadRequestError("File content is not a valid PNG, JPEG or WebP image", code="UNSUPPORTED_FILE_TYPE")
    if sniffed != ("jpg" if ext == "jpeg" else ext):
        raise BadRequestError("File content does not match its extension", code="UNSUPPORTED_FILE_TYPE")

    directory = KIND_DIRS[kind]
    name = f"{uuid.uuid4().hex}.{ext}"
    path = Path(settings.upload_dir) / directory / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)

    company = ctx.company
    attr = "logo_url" if kind == "logo" else "banner_url"
    old_url = getattr(company, attr)
    new_url = f"{FILE_URL_PREFIX}{directory}/{name}"
    setattr(company, attr, new_url)
    try:
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        _remove_file(path)
        raise
    prefix = f"{FILE_URL_PREFIX}{directory}/"
    if old_url and old_url.startswith(prefix):
        _remove_file(Path(settings.upload_dir) / directory / Path(old_url).name)
    return {"url": new_url, "logoUrl": company.logo_url, "bannerUrl": company.banner_url}


# ======================================================================================= team


def team_stmt(company_id: uuid.UUID) -> Select[Any]:
    return (
        select(User)
        .where(User.company_id == company_id, User.role == UserRole.RECRUITER, User.deleted_at.is_(None))
        .order_by(User.is_company_admin.desc(), User.created_at, User.id)
    )


def serialize_member(user: User) -> dict[str, Any]:
    return {
        "id": user.id,
        "name": user.name,
        "email": user.email,
        "mobile": user.mobile,
        "isCompanyAdmin": bool(user.is_company_admin),
        "isBlocked": bool(user.is_blocked),
        "emailVerified": bool(user.email_verified),
        "lastActiveAt": user.last_active_at,
        "joinedAt": user.created_at,
    }


# ======================================================================================= invitations


def _effective_status(invitation: Invitation) -> str:
    expires = invitation.expires_at
    if invitation.status == InvitationStatus.PENDING and expires <= utcnow():
        return "EXPIRED"
    return str(invitation.status.value if isinstance(invitation.status, InvitationStatus) else invitation.status)


def serialize_invitation(invitation: Invitation) -> dict[str, Any]:
    return {
        "id": invitation.id,
        "email": invitation.email,
        "status": _effective_status(invitation),
        "invitedBy": invitation.invited_by,
        "expiresAt": invitation.expires_at,
        "createdAt": invitation.created_at,
    }


def invitations_stmt(company_id: uuid.UUID, status: str | None = None) -> Select[Any]:
    stmt = select(Invitation).where(Invitation.company_id == company_id)
    if status:
        now = utcnow()
        wanted = status.upper()
        if wanted == "EXPIRED":
            stmt = stmt.where(Invitation.status == InvitationStatus.PENDING, Invitation.expires_at <= now)
        elif wanted == InvitationStatus.PENDING.value:
            stmt = stmt.where(Invitation.status == InvitationStatus.PENDING, Invitation.expires_at > now)
        elif wanted in {s.value for s in InvitationStatus}:
            stmt = stmt.where(Invitation.status == InvitationStatus(wanted))
        else:
            raise BadRequestError("Unknown invitation status filter")
    return stmt.order_by(Invitation.created_at.desc(), Invitation.id)


def create_invitation(db: Session, ctx: RecruiterContext, email: str) -> tuple[dict[str, Any], str, str]:
    """Create an invitation (admin only); caller commits then calls :func:`send_invitation_email`.

    Returns ``(serialized, raw_token, invite_link)``.
    """
    require_company_admin(ctx)
    if db.scalar(select(User.id).where(User.email == email)) is not None:
        raise ConflictError("A user with this email already exists")
    now = utcnow()
    pending = db.scalar(
        select(Invitation.id).where(
            Invitation.company_id == ctx.company.id,
            func.lower(Invitation.email) == email,
            Invitation.status == InvitationStatus.PENDING,
            Invitation.expires_at > now,
        )
    )
    if pending is not None:
        raise ConflictError("A pending invitation already exists for this email")
    raw_token = new_refresh_token()
    invitation = Invitation(
        id=uuid.uuid4(),
        company_id=ctx.company.id,
        email=email,
        invited_by=ctx.user.id,
        token_hash=hash_token(raw_token),
        status=InvitationStatus.PENDING,
        expires_at=now + timedelta(days=settings.invitation_expiry_days),
        created_at=now,
    )
    db.add(invitation)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise ConflictError("Invitation could not be created, retry the request") from exc
    link = f"{settings.site_url.rstrip('/')}/register?invitationToken={raw_token}"
    return serialize_invitation(invitation), raw_token, link


def send_invitation_email(email: str, company_name: str, inviter_name: str, link: str) -> None:
    """Email the invitee; delivery problems are logged, not raised (the invitation exists)."""
    body = (
        f"{inviter_name} invited you to join {company_name} as a recruiter.\n\n"
        f"Create your account here: {link}\n\n"
        f"This invitation expires in {settings.invitation_expiry_days} days."
    )
    try:
        get_email_sender().send(email, f"You're invited to join {company_name}", body)
    except (SenderError, OSError):
        logger.warning("Invitation email to %s could not be delivered", email, exc_info=True)


def revoke_invitation(db: Session, ctx: RecruiterContext, invitation_id: uuid.UUID) -> dict[str, Any]:
    require_company_admin(ctx)
    invitation = db.get(Invitation, invitation_id)
    if invitation is None or invitation.company_id != ctx.company.id:
        raise NotFoundError("Invitation not found")
    if invitation.status != InvitationStatus.PENDING:
        raise ConflictError(f"Invitation is already {invitation.status.value}")
    invitation.status = InvitationStatus.REVOKED
    db.flush()
    return serialize_invitation(invitation)
