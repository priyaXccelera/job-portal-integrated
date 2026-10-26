"""Authentication endpoints (mounted under /api/v1 by main.py)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.config import settings
from app.core.deps import get_current_user, get_db
from app.core.ratelimit import rate_limit
from app.core.responses import ok
from app.models.accounts import User
from app.schemas.auth import (
    ChangePasswordRequest,
    ForgotPasswordRequest,
    LoginOtpRequest,
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    ResetPasswordRequest,
    SendOtpRequest,
    VerifyEmailRequest,
    VerifyMobileRequest,
)
from app.services.auth_service import AuthService, serialize_user

router = APIRouter(tags=["auth"])


def _service(db: Session = Depends(get_db)) -> AuthService:
    return AuthService(db)


@router.post("/auth/register", status_code=201)
def register(body: RegisterRequest, svc: AuthService = Depends(_service)):
    return ok(svc.register(body), status_code=201)


@router.post("/auth/login", dependencies=[Depends(rate_limit("login"))])
def login(body: LoginRequest, svc: AuthService = Depends(_service)):
    return ok(svc.login(body.identifier or "", body.password))


@router.post("/auth/send-otp", dependencies=[Depends(rate_limit("otp"))])
def send_otp(body: SendOtpRequest, svc: AuthService = Depends(_service)):
    code = svc.send_login_otp(body.identifier or "", body.purpose)
    data: dict = {"message": "If the account exists, an OTP has been sent"}
    if settings.expose_dev_codes and code is not None:
        data["devOtp"] = code
    return ok(data)


@router.post("/auth/login-otp", dependencies=[Depends(rate_limit("otp"))])
def login_otp(body: LoginOtpRequest, svc: AuthService = Depends(_service)):
    return ok(svc.login_with_otp(body.identifier or "", body.otp))


@router.post("/auth/refresh")
def refresh(body: RefreshRequest, svc: AuthService = Depends(_service)):
    return ok(svc.refresh(body.refresh_token))


@router.post("/auth/logout")
def logout(
    body: RefreshRequest,
    user: User = Depends(get_current_user),
    svc: AuthService = Depends(_service),
):
    svc.logout(user, body.refresh_token)
    return ok({"message": "Logged out"})


@router.post("/auth/logout-all")
def logout_all(user: User = Depends(get_current_user), svc: AuthService = Depends(_service)):
    svc.logout_all(user)
    return ok({"message": "Logged out from all devices"})


@router.post("/auth/verify-email")
def verify_email(body: VerifyEmailRequest, svc: AuthService = Depends(_service)):
    svc.verify_email(body.token)
    return ok({"message": "Email verified", "emailVerified": True})


@router.post("/auth/resend-verification", dependencies=[Depends(rate_limit("otp"))])
def resend_verification(user: User = Depends(get_current_user), svc: AuthService = Depends(_service)):
    token = svc.resend_verification(user)
    if token is None:
        return ok({"message": "Email is already verified"})
    data: dict = {"message": "Verification email sent"}
    if settings.expose_dev_codes:
        data["devToken"] = token
    return ok(data)


@router.post("/auth/send-mobile-otp", dependencies=[Depends(rate_limit("otp"))])
def send_mobile_otp(user: User = Depends(get_current_user), svc: AuthService = Depends(_service)):
    code = svc.send_mobile_otp(user)
    data: dict = {"message": "OTP sent to your mobile"}
    if settings.expose_dev_codes:
        data["devOtp"] = code
    return ok(data)


@router.post("/auth/verify-mobile")
def verify_mobile(
    body: VerifyMobileRequest,
    user: User = Depends(get_current_user),
    svc: AuthService = Depends(_service),
):
    svc.verify_mobile(user, body.otp)
    return ok({"message": "Mobile verified", "mobileVerified": True})


@router.post("/auth/forgot-password", dependencies=[Depends(rate_limit("otp"))])
def forgot_password(body: ForgotPasswordRequest, svc: AuthService = Depends(_service)):
    token = svc.forgot_password(body.email)
    data: dict = {"message": "If the email is registered, a reset link has been sent"}
    if settings.expose_dev_codes and token is not None:
        data["devToken"] = token
    return ok(data)


@router.post("/auth/reset-password")
def reset_password(body: ResetPasswordRequest, svc: AuthService = Depends(_service)):
    svc.reset_password(body.token, body.new_password)
    return ok({"message": "Password has been reset"})


@router.post("/auth/change-password")
def change_password(
    body: ChangePasswordRequest,
    user: User = Depends(get_current_user),
    svc: AuthService = Depends(_service),
):
    svc.change_password(user, body.current_password, body.new_password)
    return ok({"message": "Password changed"})


@router.get("/auth/me")
def me(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return ok(serialize_user(db, user))
