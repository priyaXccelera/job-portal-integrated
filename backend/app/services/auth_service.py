"""Authentication business logic: registration, sessions, OTPs, email verification, passwords."""

from __future__ import annotations

import hmac
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import settings
from app.core.errors import AppError, BadRequestError, ConflictError, ForbiddenError, UnauthorizedError
from app.core.security import (
    create_access_token,
    generate_otp,
    hash_password,
    hash_token,
    new_refresh_token,
    verify_password,
)
from app.models.accounts import (
    EmailToken,
    NotificationPreference,
    OtpCode,
    RefreshToken,
    ResetToken,
    User,
)
from app.models.company import Company, Invitation
from app.models.enums import CompanyStatus, InvitationStatus, UserRole
from app.models.profile import JobSeekerProfile
from app.schemas.auth import RegisterRequest, normalise_mobile
from app.services.senders import SenderError, get_email_sender, get_otp_sender

logger = logging.getLogger(__name__)

OTP_LOGIN = "LOGIN"
OTP_MOBILE_VERIFY = "MOBILE_VERIFY"

_dummy_hash: str | None = None


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return _aware(value).astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _dummy_password_hash() -> str:
    """Hash used to keep login timing similar for unknown identifiers."""
    global _dummy_hash
    if _dummy_hash is None:
        _dummy_hash = hash_password("dummy-password-1")
    return _dummy_hash


@dataclass
class PendingEmail:
    to: str
    subject: str
    body: str


def deliver_email(mail: PendingEmail) -> None:
    """Send an email; delivery failures are logged, never surfaced to the client."""
    try:
        get_email_sender().send(mail.to, mail.subject, mail.body)
    except SenderError:
        logger.warning("Email delivery failed for %s (%s)", mail.to, mail.subject, exc_info=True)


def deliver_otp(mobile: str, code: str) -> None:
    try:
        get_otp_sender().send(mobile, code)
    except SenderError:
        logger.warning("OTP delivery failed for %s", mobile, exc_info=True)


def serialize_user(db: Session, user: User) -> dict[str, Any]:
    company = None
    if user.company_id is not None:
        c = db.get(Company, user.company_id)
        if c is not None and c.deleted_at is None:
            company = {
                "id": str(c.id),
                "name": c.name,
                "status": c.status.value if hasattr(c.status, "value") else str(c.status),
                "isCompanyAdmin": bool(user.is_company_admin),
            }
    return {
        "id": str(user.id),
        "name": user.name,
        "email": user.email,
        "mobile": user.mobile,
        "role": user.role.value if hasattr(user.role, "value") else str(user.role),
        "emailVerified": bool(user.email_verified),
        "mobileVerified": bool(user.mobile_verified),
        "isBlocked": bool(user.is_blocked),
        "createdAt": _iso(user.created_at),
        "company": company,
    }


class AuthService:
    def __init__(self, db: Session) -> None:
        self.db = db

    # ------------------------------------------------------------------ lookups
    def _find_user(self, identifier: str) -> User | None:
        ident = identifier.strip()
        mobile = normalise_mobile(ident)
        conditions = [User.email == ident.lower()]
        if mobile:
            conditions.append(User.mobile == mobile)
        return self.db.scalar(select(User).where(User.deleted_at.is_(None), or_(*conditions)))

    @staticmethod
    def _is_mobile_identifier(identifier: str) -> bool:
        return "@" not in identifier

    # ------------------------------------------------------------------ tokens
    def issue_tokens(self, user: User) -> dict[str, Any]:
        access, expires_in = create_access_token(user)
        raw_refresh = new_refresh_token()
        self.db.add(
            RefreshToken(
                user_id=user.id,
                token_hash=hash_token(raw_refresh),
                expires_at=_now() + timedelta(days=settings.refresh_token_days),
            )
        )
        return {
            "accessToken": access,
            "refreshToken": raw_refresh,
            "tokenType": "Bearer",
            "expiresIn": expires_in,
            "user": serialize_user(self.db, user),
        }

    def _revoke_all_refresh_tokens(self, user_id: uuid.UUID) -> None:
        self.db.execute(
            update(RefreshToken)
            .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=_now())
        )

    def _new_email_token(self, user: User) -> tuple[str, PendingEmail]:
        raw = new_refresh_token()
        self.db.add(
            EmailToken(
                user_id=user.id,
                token_hash=hash_token(raw),
                expires_at=_now() + timedelta(hours=settings.email_token_hours),
            )
        )
        link = f"{settings.site_url.rstrip('/')}/verify-email?token={raw}"
        mail = PendingEmail(
            to=user.email,
            subject="Verify your email address",
            body=(
                f"Hi {user.name},\n\nPlease verify your email by opening this link:\n{link}\n\n"
                f"Verification token: {raw}\nThe link expires in {settings.email_token_hours} hours."
            ),
        )
        return raw, mail

    def _new_otp(self, user: User, purpose: str) -> str:
        """Invalidate older codes for the purpose and create a fresh one; returns the raw code."""
        now = _now()
        self.db.execute(
            update(OtpCode)
            .where(OtpCode.user_id == user.id, OtpCode.purpose == purpose, OtpCode.consumed_at.is_(None))
            .values(consumed_at=now)
        )
        code = generate_otp()
        self.db.add(
            OtpCode(
                user_id=user.id,
                target=user.mobile or user.email,
                purpose=purpose,
                code_hash=hash_token(code),
                expires_at=now + timedelta(minutes=settings.otp_ttl_minutes),
            )
        )
        return code

    def _check_otp(self, user: User, purpose: str, code: str) -> bool:
        """Validate ``code`` against the latest live OTP; consumes it on success.

        Wrong guesses increment the attempt counter (persisted) and a code with too many
        attempts is dead.
        """
        now = _now()
        otp = self.db.scalar(
            select(OtpCode)
            .where(
                OtpCode.user_id == user.id,
                OtpCode.purpose == purpose,
                OtpCode.consumed_at.is_(None),
                OtpCode.expires_at > now,
            )
            .order_by(OtpCode.created_at.desc())
            .limit(1)
            .with_for_update()
        )
        if otp is None or otp.attempts >= settings.otp_max_attempts:
            self.db.rollback()
            return False
        if not hmac.compare_digest(otp.code_hash, hash_token(code.strip())):
            otp.attempts += 1
            self.db.commit()
            return False
        otp.consumed_at = now
        return True

    # ------------------------------------------------------------------ register
    def register(self, data: RegisterRequest) -> dict[str, Any]:
        email = data.email
        existing = self.db.scalar(
            select(User).where(or_(User.email == email, User.mobile == data.mobile))
        )
        if existing is not None:
            field = "email" if existing.email == email else "mobile"
            raise AppError(
                409,
                "CONFLICT",
                f"An account with this {field} already exists",
                [{"field": field, "message": f"{field} already registered"}],
            )

        # Server-side bootstrap: the very first account becomes the admin.
        is_first = (self.db.scalar(select(func.count()).select_from(User)) or 0) == 0
        role = UserRole.ADMIN if is_first else data.role

        user_id = uuid.uuid4()
        company_id: uuid.UUID | None = None
        is_company_admin = False
        email_verified = False
        invitation: Invitation | None = None

        if role == UserRole.RECRUITER:
            if data.invitation_token:
                invitation = self._load_invitation(data.invitation_token, email)
                company_id = invitation.company_id
                email_verified = True
            else:
                self._assert_work_email(email)
                company = Company(
                    name=data.company_name,
                    status=CompanyStatus.PENDING,
                    credits=settings.demo_credits,
                    job_quota=settings.default_job_quota,
                    jobs_posted=0,
                    created_by=user_id,
                )
                self.db.add(company)
                self.db.flush()
                company_id = company.id
                is_company_admin = True
        elif data.invitation_token:
            raise AppError(
                422,
                "VALIDATION_ERROR",
                "Invitations are only valid for recruiter accounts",
                [{"field": "invitationToken", "message": "Invitations are only valid for recruiters"}],
            )

        user = User(
            id=user_id,
            name=data.name,
            email=email,
            mobile=data.mobile,
            password_hash=hash_password(data.password),
            role=role,
            email_verified=email_verified,
            mobile_verified=False,
            company_id=company_id,
            is_company_admin=is_company_admin,
        )
        self.db.add(user)
        try:
            self.db.flush()
        except IntegrityError as exc:
            self.db.rollback()
            raise ConflictError("An account with this email or mobile already exists") from exc

        self.db.add(NotificationPreference(user_id=user_id))
        if role == UserRole.JOB_SEEKER:
            self.db.add(JobSeekerProfile(user_id=user_id))
        if invitation is not None:
            invitation.status = InvitationStatus.ACCEPTED

        raw_token, mail = self._new_email_token(user)
        try:
            self.db.commit()
        except IntegrityError as exc:
            self.db.rollback()
            raise ConflictError("An account with this email or mobile already exists") from exc
        self.db.refresh(user)
        if not email_verified:
            deliver_email(mail)

        result: dict[str, Any] = {"user": serialize_user(self.db, user)}
        if settings.expose_dev_codes:
            result["devToken"] = raw_token
        return result

    @staticmethod
    def _assert_work_email(email: str) -> None:
        domain = email.rsplit("@", 1)[-1].lower()
        if domain in {d.lower() for d in settings.free_email_domains}:
            raise AppError(
                422,
                "VALIDATION_ERROR",
                "Recruiters must register with a work email address",
                [{"field": "email", "message": "Free email domains are not allowed for recruiters"}],
            )

    def _load_invitation(self, raw_token: str, email: str) -> Invitation:
        invitation = self.db.scalar(
            select(Invitation).where(Invitation.token_hash == hash_token(raw_token)).with_for_update()
        )
        company = self.db.get(Company, invitation.company_id) if invitation is not None else None
        valid = (
            invitation is not None
            and invitation.status == InvitationStatus.PENDING
            and _aware(invitation.expires_at) > _now()
            and invitation.email.strip().lower() == email
            and company is not None
            and company.deleted_at is None
        )
        if not valid:
            self.db.rollback()
            raise AppError(
                422,
                "VALIDATION_ERROR",
                "Invitation is invalid, expired or issued for a different email",
                [{"field": "invitationToken", "message": "Invalid or expired invitation"}],
            )
        return invitation

    # ------------------------------------------------------------------ login
    def login(self, identifier: str, password: str) -> dict[str, Any]:
        user = self._find_user(identifier)
        if user is None:
            verify_password(password, _dummy_password_hash())
            raise UnauthorizedError("Invalid credentials")
        if not verify_password(password, user.password_hash):
            raise UnauthorizedError("Invalid credentials")
        self._assert_can_login(user)
        result = self.issue_tokens(user)
        self.db.commit()
        return result

    @staticmethod
    def _assert_can_login(user: User) -> None:
        if user.deleted_at is not None:
            raise UnauthorizedError("Invalid credentials")
        if user.is_blocked:
            raise ForbiddenError("Your account has been blocked", code="ACCOUNT_BLOCKED")

    def send_login_otp(self, identifier: str, purpose: str = OTP_LOGIN) -> str | None:
        """Create + send an OTP if the user exists. Returns the raw code (for dev exposure) or None."""
        user = self._find_user(identifier)
        if user is None or user.is_blocked or not user.mobile:
            return None
        code = self._new_otp(user, purpose)
        self.db.commit()
        deliver_otp(user.mobile, code)
        return code

    def login_with_otp(self, identifier: str, otp: str) -> dict[str, Any]:
        user = self._find_user(identifier)
        if user is None or not self._check_otp(user, OTP_LOGIN, otp):
            raise UnauthorizedError("Invalid or expired OTP")
        self._assert_can_login(user)
        if self._is_mobile_identifier(identifier) and not user.mobile_verified:
            user.mobile_verified = True
        result = self.issue_tokens(user)
        self.db.commit()
        return result

    # ------------------------------------------------------------------ refresh / logout
    def refresh(self, raw_token: str) -> dict[str, Any]:
        token = self.db.scalar(
            select(RefreshToken).where(RefreshToken.token_hash == hash_token(raw_token)).with_for_update()
        )
        if token is None or token.revoked_at is not None or _aware(token.expires_at) <= _now():
            self.db.rollback()
            raise UnauthorizedError("Invalid or expired refresh token")
        user = self.db.get(User, token.user_id)
        if user is None or user.deleted_at is not None:
            self.db.rollback()
            raise UnauthorizedError("Invalid or expired refresh token")
        if user.is_blocked:
            self.db.rollback()
            raise ForbiddenError("Your account has been blocked", code="ACCOUNT_BLOCKED")
        token.revoked_at = _now()
        result = self.issue_tokens(user)
        self.db.commit()
        return result

    def logout(self, user: User, raw_token: str) -> None:
        token = self.db.scalar(
            select(RefreshToken).where(
                RefreshToken.token_hash == hash_token(raw_token), RefreshToken.user_id == user.id
            )
        )
        if token is not None and token.revoked_at is None:
            token.revoked_at = _now()
            self.db.commit()

    def logout_all(self, user: User) -> None:
        self._revoke_all_refresh_tokens(user.id)
        self.db.commit()

    # ------------------------------------------------------------------ email verification
    def verify_email(self, raw_token: str) -> None:
        token = self.db.scalar(
            select(EmailToken).where(EmailToken.token_hash == hash_token(raw_token)).with_for_update()
        )
        if token is None or token.used_at is not None or _aware(token.expires_at) <= _now():
            self.db.rollback()
            raise BadRequestError("Invalid or expired verification token")
        user = self.db.get(User, token.user_id)
        if user is None or user.deleted_at is not None:
            self.db.rollback()
            raise BadRequestError("Invalid or expired verification token")
        token.used_at = _now()
        user.email_verified = True
        self.db.commit()

    def resend_verification(self, user: User) -> str | None:
        if user.email_verified:
            return None
        raw, mail = self._new_email_token(user)
        self.db.commit()
        deliver_email(mail)
        return raw

    # ------------------------------------------------------------------ mobile verification
    def send_mobile_otp(self, user: User) -> str:
        if not user.mobile:
            raise BadRequestError("No mobile number on this account")
        code = self._new_otp(user, OTP_MOBILE_VERIFY)
        self.db.commit()
        deliver_otp(user.mobile, code)
        return code

    def verify_mobile(self, user: User, otp: str) -> None:
        if not self._check_otp(user, OTP_MOBILE_VERIFY, otp):
            raise BadRequestError("Invalid or expired OTP")
        user.mobile_verified = True
        self.db.commit()

    # ------------------------------------------------------------------ passwords
    def forgot_password(self, email: str) -> str | None:
        user = self.db.scalar(select(User).where(User.email == email.lower(), User.deleted_at.is_(None)))
        if user is None:
            return None
        now = _now()
        self.db.execute(
            update(ResetToken)
            .where(ResetToken.user_id == user.id, ResetToken.used_at.is_(None))
            .values(used_at=now)
        )
        raw = new_refresh_token()
        self.db.add(
            ResetToken(
                user_id=user.id,
                token_hash=hash_token(raw),
                expires_at=now + timedelta(minutes=settings.reset_token_minutes),
            )
        )
        self.db.commit()
        link = f"{settings.site_url.rstrip('/')}/reset-password?token={raw}"
        deliver_email(
            PendingEmail(
                to=user.email,
                subject="Reset your password",
                body=(
                    f"Hi {user.name},\n\nUse this link to reset your password:\n{link}\n\n"
                    f"Reset token: {raw}\nThe link expires in {settings.reset_token_minutes} minutes. "
                    "If you did not request this, ignore this email."
                ),
            )
        )
        return raw

    def reset_password(self, raw_token: str, new_password: str) -> None:
        token = self.db.scalar(
            select(ResetToken).where(ResetToken.token_hash == hash_token(raw_token)).with_for_update()
        )
        if token is None or token.used_at is not None or _aware(token.expires_at) <= _now():
            self.db.rollback()
            raise BadRequestError("Invalid or expired reset token")
        user = self.db.get(User, token.user_id)
        if user is None or user.deleted_at is not None:
            self.db.rollback()
            raise BadRequestError("Invalid or expired reset token")
        token.used_at = _now()
        user.password_hash = hash_password(new_password)
        self._revoke_all_refresh_tokens(user.id)
        self.db.commit()

    def change_password(self, user: User, current_password: str, new_password: str) -> None:
        if not verify_password(current_password, user.password_hash):
            raise BadRequestError("Current password is incorrect")
        user.password_hash = hash_password(new_password)
        self._revoke_all_refresh_tokens(user.id)
        self.db.commit()
