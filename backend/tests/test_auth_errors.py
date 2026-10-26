"""Authentication flows and the shared JSON error envelope / global handlers."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import jwt
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError, OperationalError

from app.config import settings
from app.core.errors import AppError, register_handlers
from app.core.ratelimit import reset_rate_limits
from app.models.accounts import OtpCode, RefreshToken, ResetToken, User
from app.models.enums import UserRole
from tests.helpers import assert_error, assert_ok

API = "/api/v1"
PASSWORD = "Passw0rd1"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def login(client, identifier: str, password: str = PASSWORD, **extra):
    return client.post(f"{API}/auth/login", json={"identifier": identifier, "password": password, **extra})


def register_body(**overrides) -> dict:
    body = {"name": "New Seeker", "email": "new.seeker@example.com", "mobile": "9811122233", "password": PASSWORD,
            "role": "JOB_SEEKER"}
    body.update(overrides)
    return body


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# =========================================================================== envelope / global handlers


def test_malformed_json_is_400_malformed_body(client):
    resp = client.post(f"{API}/auth/login", content=b'{"identifier": "a", ',
                       headers={"Content-Type": "application/json"})
    error = assert_error(resp, 400, "MALFORMED_BODY")
    assert error["details"] == []


def test_non_object_json_body_is_422(client):
    resp = client.post(f"{API}/auth/login", content=b"[1, 2]", headers={"Content-Type": "application/json"})
    assert_error(resp, 422, "VALIDATION_ERROR")


@pytest.mark.parametrize("path", ["/api/v1/does-not-exist", "/nope", "/api/v1/jobs/search/extra/deep"])
def test_unknown_route_is_404_envelope(client, path):
    error = assert_error(client.get(path), 404, "NOT_FOUND")
    assert error["message"]


@pytest.mark.parametrize("method,path", [("POST", "/api/v1/health"), ("DELETE", "/api/v1/health"),
                                         ("PUT", "/health"), ("POST", "/health")])
def test_405_has_allow_header_and_envelope(client, method, path):
    resp = client.request(method, path)
    assert_error(resp, 405, "METHOD_NOT_ALLOWED")
    allow = {m.strip() for m in resp.headers["allow"].split(",")}
    assert "GET" in allow
    assert method not in allow


def test_405_on_other_routes_keeps_allow(client):
    resp = client.post(f"{API}/jobs/search")
    assert_error(resp, 405, "METHOD_NOT_ALLOWED")
    assert "GET" in resp.headers["allow"]


def test_health_endpoints(client):
    for path in ("/api/v1/health", "/health"):
        data = assert_ok(client.get(path))["data"]
        assert data["status"] == "UP" and data["database"] == "UP"


def test_validation_error_envelope_has_field_details(client):
    error = assert_error(client.post(f"{API}/auth/register", json={}), 422, "VALIDATION_ERROR")
    fields = {d["field"] for d in error["details"]}
    assert {"name", "email", "mobile", "password", "role"} <= fields
    assert all(d["message"] for d in error["details"])

    error = assert_error(client.post(f"{API}/auth/register", json=register_body(email="not-an-email",
                                                                                 password="short")),
                         422, "VALIDATION_ERROR")
    assert {d["field"] for d in error["details"]} >= {"email", "password"}


def test_query_validation_error_details_name_the_parameter(client):
    error = assert_error(client.get(f"{API}/jobs/search", params={"page": "abc"}), 422, "VALIDATION_ERROR")
    assert any("page" in d["field"] for d in error["details"])


def test_request_id_header_is_propagated_or_generated(client):
    resp = client.get("/health", headers={"X-Request-ID": "abc-123"})
    assert resp.headers["x-request-id"] == "abc-123"
    assert client.get("/health").headers["x-request-id"]


def test_unhandled_exception_returns_500_without_trace():
    app2 = FastAPI()
    register_handlers(app2)

    @app2.get("/boom")
    def boom():
        raise RuntimeError("secret-internal-detail /srv/app/secret.py")

    @app2.get("/db-down")
    def db_down():
        raise OperationalError("SELECT secret_column", {}, Exception("password authentication failed"))

    @app2.get("/conflict")
    def conflict():
        raise IntegrityError("INSERT INTO t", {}, Exception("duplicate key value violates unique constraint"))

    @app2.get("/teapot")
    def teapot():
        raise HTTPException(status_code=418, detail="short and stout")

    @app2.get("/custom")
    def custom():
        raise AppError(402, "CUSTOM_CODE", "custom message", [{"field": "x", "message": "y"}])

    with TestClient(app2, raise_server_exceptions=False) as c:
        resp = c.get("/boom")
        assert_error(resp, 500, "INTERNAL_ERROR")
        assert resp.json()["error"]["message"] == "Internal server error"
        for leaked in ("secret-internal-detail", "RuntimeError", "Traceback", "secret.py"):
            assert leaked not in resp.text

        resp = c.get("/db-down")
        assert_error(resp, 500, "INTERNAL_ERROR")
        assert "secret_column" not in resp.text and "password authentication" not in resp.text

        resp = c.get("/conflict")
        assert_error(resp, 409, "CONFLICT")
        assert "duplicate key" not in resp.text

        error = assert_error(c.get("/teapot"), 418)
        assert error["message"] == "short and stout"

        error = assert_error(c.get("/custom"), 402, "CUSTOM_CODE")
        assert error["details"] == [{"field": "x", "message": "y"}]

        assert_error(c.get("/missing"), 404, "NOT_FOUND")
        assert_error(c.post("/boom"), 405, "METHOD_NOT_ALLOWED")


def test_rate_limit_returns_429(client, monkeypatch, make_user):
    make_user(email="limited@example.com")
    monkeypatch.setattr(settings, "rate_limit_enabled", True)
    monkeypatch.setattr(settings, "rate_limit_login", 3)
    reset_rate_limits()
    try:
        for _ in range(3):
            assert_error(login(client, "limited@example.com", "wrong-Pass1"), 401, "UNAUTHORIZED")
        resp = login(client, "limited@example.com", "wrong-Pass1")
        assert_error(resp, 429, "RATE_LIMITED")
        assert int(resp.headers["retry-after"]) >= 1
        # even the correct password is throttled while the window is full
        assert_error(login(client, "limited@example.com"), 429, "RATE_LIMITED")
        # the limiter is per endpoint-name: other endpoints are unaffected
        assert client.get("/health").status_code == 200
    finally:
        reset_rate_limits()
    monkeypatch.setattr(settings, "rate_limit_enabled", False)
    assert login(client, "limited@example.com").status_code == 200


def test_otp_endpoints_are_rate_limited(client, monkeypatch):
    monkeypatch.setattr(settings, "rate_limit_enabled", True)
    monkeypatch.setattr(settings, "rate_limit_otp", 2)
    reset_rate_limits()
    try:
        for _ in range(2):
            assert_ok(client.post(f"{API}/auth/forgot-password", json={"email": "nobody@example.com"}))
        assert_error(client.post(f"{API}/auth/forgot-password", json={"email": "nobody@example.com"}), 429,
                     "RATE_LIMITED")
    finally:
        reset_rate_limits()


# =========================================================================== token checks (401 JSON)


def test_missing_token_is_401_json(client):
    resp = client.get(f"{API}/auth/me")
    assert_error(resp, 401, "UNAUTHORIZED")
    assert resp.headers["www-authenticate"] == "Bearer"
    assert_error(client.get(f"{API}/auth/me", headers={"Authorization": ""}), 401, "UNAUTHORIZED")
    assert_error(client.get(f"{API}/auth/me", headers={"Authorization": "Basic dXNlcjpwdw=="}), 401, "UNAUTHORIZED")


def test_invalid_tokens_are_401(client, make_user):
    user = make_user()
    assert_error(client.get(f"{API}/auth/me", headers=bearer("garbage")), 401, "UNAUTHORIZED")
    now = utc_now()

    def forge(secret=settings.jwt_secret, **claims):
        payload = {"sub": str(user.id), "iat": now, "exp": now + timedelta(minutes=5), "type": "access"}
        payload.update(claims)
        payload = {k: v for k, v in payload.items() if v is not None}
        return jwt.encode(payload, secret, algorithm="HS256")

    assert_error(client.get(f"{API}/auth/me", headers=bearer(forge(exp=now - timedelta(minutes=1)))), 401,
                 "UNAUTHORIZED")
    assert_error(client.get(f"{API}/auth/me", headers=bearer(forge(secret="another-secret-" + "z" * 32))), 401,
                 "UNAUTHORIZED")
    assert_error(client.get(f"{API}/auth/me", headers=bearer(forge(type="refresh"))), 401, "UNAUTHORIZED")
    assert_error(client.get(f"{API}/auth/me", headers=bearer(forge(sub=str(uuid.uuid4())))), 401, "UNAUTHORIZED")
    assert_error(client.get(f"{API}/auth/me", headers=bearer(forge(sub="not-a-uuid"))), 401, "UNAUTHORIZED")
    # sanity: the forge helper produces a token the API accepts
    assert_ok(client.get(f"{API}/auth/me", headers=bearer(forge())))


def test_expired_token_message(client, make_user):
    user = make_user()
    now = utc_now()
    token = jwt.encode({"sub": str(user.id), "iat": now - timedelta(hours=2), "exp": now - timedelta(hours=1),
                        "type": "access"}, settings.jwt_secret, algorithm="HS256")
    error = assert_error(client.get(f"{API}/auth/me", headers=bearer(token)), 401, "UNAUTHORIZED")
    assert "expired" in error["message"].lower()


def test_blocked_user_cannot_login_or_use_token(client, db, make_user, auth_headers):
    user = make_user(email="blocked@example.com", is_blocked=True)
    error = assert_error(login(client, "blocked@example.com"), 403, "ACCOUNT_BLOCKED")
    assert "blocked" in error["message"].lower()
    assert_error(client.get(f"{API}/auth/me", headers=auth_headers(user)), 403, "ACCOUNT_BLOCKED")


def test_user_blocked_after_login_loses_access_and_refresh(client, db, make_user):
    user = make_user(email="soon.blocked@example.com")
    tokens = assert_ok(login(client, user.email))["data"]
    assert_ok(client.get(f"{API}/auth/me", headers=bearer(tokens["accessToken"])))
    user.is_blocked = True
    db.commit()
    assert_error(client.get(f"{API}/auth/me", headers=bearer(tokens["accessToken"])), 403, "ACCOUNT_BLOCKED")
    assert_error(client.post(f"{API}/auth/refresh", json={"refreshToken": tokens["refreshToken"]}), 403,
                 "ACCOUNT_BLOCKED")


def test_soft_deleted_user_is_unauthorized(client, db, make_user, auth_headers):
    user = make_user(email="gone@example.com", deleted_at=utc_now())
    assert_error(login(client, "gone@example.com"), 401, "UNAUTHORIZED")
    assert_error(client.get(f"{API}/auth/me", headers=auth_headers(user)), 401, "UNAUTHORIZED")

    live = make_user(email="live@example.com")
    tokens = assert_ok(login(client, live.email))["data"]
    live.deleted_at = utc_now()
    db.commit()
    assert_error(client.get(f"{API}/auth/me", headers=bearer(tokens["accessToken"])), 401, "UNAUTHORIZED")
    assert_error(client.post(f"{API}/auth/refresh", json={"refreshToken": tokens["refreshToken"]}), 401,
                 "UNAUTHORIZED")


# =========================================================================== login


def test_login_by_email_is_case_insensitive_and_returns_tokens(client, make_user):
    user = make_user(email="alice@example.com", name="Alice")
    data = assert_ok(login(client, "ALICE@Example.com"))["data"]
    assert data["tokenType"] == "Bearer" and data["expiresIn"] == settings.access_token_minutes * 60
    assert data["accessToken"] and data["refreshToken"]
    assert data["user"]["id"] == str(user.id) and data["user"]["email"] == "alice@example.com"
    assert data["user"]["role"] == "JOB_SEEKER"
    assert "passwordHash" not in data["user"] and "password_hash" not in data["user"]
    me = assert_ok(client.get(f"{API}/auth/me", headers=bearer(data["accessToken"])))["data"]
    assert me["id"] == str(user.id) and me["name"] == "Alice" and me["company"] is None


def test_login_by_mobile_and_legacy_email_field(client, make_user):
    user = make_user(email="bob@example.com", mobile="9988776655")
    by_mobile = assert_ok(login(client, "9988776655"))["data"]
    assert by_mobile["user"]["id"] == str(user.id)
    legacy = client.post(f"{API}/auth/login", json={"email": "bob@example.com", "password": PASSWORD})
    assert assert_ok(legacy)["data"]["user"]["id"] == str(user.id)
    assert_error(login(client, "9988776650"), 401, "UNAUTHORIZED")


def test_login_failures_do_not_reveal_which_part_was_wrong(client, make_user):
    make_user(email="carol@example.com")
    wrong_pw = assert_error(login(client, "carol@example.com", "Wr0ngPassword"), 401, "UNAUTHORIZED")
    unknown = assert_error(login(client, "nobody@example.com"), 401, "UNAUTHORIZED")
    assert wrong_pw["message"] == unknown["message"]
    assert_error(client.post(f"{API}/auth/login", json={"identifier": "carol@example.com"}), 422, "VALIDATION_ERROR")
    assert_error(client.post(f"{API}/auth/login", json={"password": PASSWORD}), 422, "VALIDATION_ERROR")


def test_recruiter_me_includes_company(client, make_company, make_recruiter, auth_headers):
    company = make_company(name="Umbrella")
    me = assert_ok(client.get(f"{API}/auth/me", headers=auth_headers(make_recruiter(company))))["data"]
    assert me["role"] == "RECRUITER"
    assert me["company"]["name"] == "Umbrella" and me["company"]["status"] == "APPROVED"
    assert me["company"]["isCompanyAdmin"] is True


# =========================================================================== register


def test_register_seeker_and_duplicates(client, db):
    data = assert_ok(client.post(f"{API}/auth/register", json=register_body()), 201)["data"]
    assert data["user"]["email"] == "new.seeker@example.com" and data["user"]["emailVerified"] is False
    assert data["devToken"]
    assert assert_ok(login(client, "new.seeker@example.com"))["data"]["user"]["name"] == "New Seeker"
    dup_email = assert_error(client.post(f"{API}/auth/register", json=register_body(mobile="9000000001")), 409,
                             "CONFLICT")
    assert dup_email["details"][0]["field"] == "email"
    dup_mobile = assert_error(client.post(f"{API}/auth/register", json=register_body(email="other@example.com")),
                              409, "CONFLICT")
    assert dup_mobile["details"][0]["field"] == "mobile"
    # case-insensitive e-mail uniqueness
    assert_error(client.post(f"{API}/auth/register", json=register_body(email="NEW.SEEKER@example.com",
                                                                         mobile="9000000002")), 409, "CONFLICT")
    db.expire_all()
    assert db.query(User).count() == 1


@pytest.mark.parametrize("overrides", [
    {"password": "short1"}, {"password": "onlyletters"}, {"password": "12345678"},
    {"mobile": "12345"}, {"mobile": "abcdefghij"}, {"email": "bad@"}, {"name": "   "},
])
def test_register_validation(client, overrides):
    assert_error(client.post(f"{API}/auth/register", json=register_body(**overrides)), 422, "VALIDATION_ERROR")


# =========================================================================== refresh / logout


def test_refresh_rotation_rejects_old_token(client, make_user):
    make_user(email="dave@example.com")
    first = assert_ok(login(client, "dave@example.com"))["data"]
    second = assert_ok(client.post(f"{API}/auth/refresh", json={"refreshToken": first["refreshToken"]}))["data"]
    assert second["refreshToken"] != first["refreshToken"] and second["accessToken"]
    assert_error(client.post(f"{API}/auth/refresh", json={"refreshToken": first["refreshToken"]}), 401,
                 "UNAUTHORIZED")
    third = assert_ok(client.post(f"{API}/auth/refresh", json={"refreshToken": second["refreshToken"]}))["data"]
    assert assert_ok(client.get(f"{API}/auth/me", headers=bearer(third["accessToken"])))
    assert_error(client.post(f"{API}/auth/refresh", json={"refreshToken": "garbage"}), 401, "UNAUTHORIZED")
    assert_error(client.post(f"{API}/auth/refresh", json={}), 422, "VALIDATION_ERROR")


def test_expired_refresh_token_is_rejected(client, db, make_user):
    user = make_user(email="erin@example.com")
    tokens = assert_ok(login(client, user.email))["data"]
    db.query(RefreshToken).filter_by(user_id=user.id).update({"expires_at": utc_now() - timedelta(minutes=1)})
    db.commit()
    assert_error(client.post(f"{API}/auth/refresh", json={"refreshToken": tokens["refreshToken"]}), 401,
                 "UNAUTHORIZED")


def test_logout_revokes_refresh_token(client, db, make_user):
    user = make_user(email="frank@example.com")
    tokens = assert_ok(login(client, user.email))["data"]
    other = assert_ok(login(client, user.email))["data"]
    assert_ok(client.post(f"{API}/auth/logout", json={"refreshToken": tokens["refreshToken"]},
                          headers=bearer(tokens["accessToken"])))
    assert_error(client.post(f"{API}/auth/refresh", json={"refreshToken": tokens["refreshToken"]}), 401,
                 "UNAUTHORIZED")
    # the other session is untouched
    assert_ok(client.post(f"{API}/auth/refresh", json={"refreshToken": other["refreshToken"]}))
    assert_error(client.post(f"{API}/auth/logout", json={"refreshToken": "x"}), 401, "UNAUTHORIZED")


def test_logout_all_revokes_every_session(client, make_user):
    user = make_user(email="gina@example.com")
    a, b = (assert_ok(login(client, user.email))["data"] for _ in range(2))
    assert_ok(client.post(f"{API}/auth/logout-all", headers=bearer(a["accessToken"])))
    for tokens in (a, b):
        assert_error(client.post(f"{API}/auth/refresh", json={"refreshToken": tokens["refreshToken"]}), 401,
                     "UNAUTHORIZED")


# =========================================================================== password flows


def test_forgot_and_reset_password_flow(client, db, make_user):
    user = make_user(email="hank@example.com")
    tokens = assert_ok(login(client, user.email))["data"]
    forgot = assert_ok(client.post(f"{API}/auth/forgot-password", json={"email": "HANK@example.com"}))["data"]
    token = forgot["devToken"]
    assert token and "reset link" in forgot["message"]

    assert_error(client.post(f"{API}/auth/reset-password", json={"token": token, "newPassword": "weak"}), 422,
                 "VALIDATION_ERROR")
    assert_ok(client.post(f"{API}/auth/reset-password", json={"token": token, "newPassword": "N3wPassword!"}))
    assert_error(login(client, user.email), 401, "UNAUTHORIZED")  # old password gone
    assert_ok(login(client, user.email, "N3wPassword!"))
    # single use
    assert_error(client.post(f"{API}/auth/reset-password", json={"token": token, "newPassword": "An0therPass"}), 400,
                 "BAD_REQUEST")
    # existing sessions are revoked
    assert_error(client.post(f"{API}/auth/refresh", json={"refreshToken": tokens["refreshToken"]}), 401,
                 "UNAUTHORIZED")


def test_forgot_password_unknown_email_does_not_leak(client):
    data = assert_ok(client.post(f"{API}/auth/forgot-password", json={"email": "ghost@example.com"}))["data"]
    assert "devToken" not in data
    assert "reset link" in data["message"]
    assert_error(client.post(f"{API}/auth/forgot-password", json={"email": "bad"}), 422, "VALIDATION_ERROR")


def test_reset_password_rejects_unknown_expired_and_superseded_tokens(client, db, make_user):
    user = make_user(email="iris@example.com")
    assert_error(client.post(f"{API}/auth/reset-password", json={"token": "nope", "newPassword": "N3wPassword!"}),
                 400, "BAD_REQUEST")
    old = assert_ok(client.post(f"{API}/auth/forgot-password", json={"email": user.email}))["data"]["devToken"]
    new = assert_ok(client.post(f"{API}/auth/forgot-password", json={"email": user.email}))["data"]["devToken"]
    assert_error(client.post(f"{API}/auth/reset-password", json={"token": old, "newPassword": "N3wPassword!"}), 400,
                 "BAD_REQUEST")
    db.query(ResetToken).filter_by(user_id=user.id, used_at=None).update({"expires_at": utc_now() - timedelta(minutes=1)})
    db.commit()
    assert_error(client.post(f"{API}/auth/reset-password", json={"token": new, "newPassword": "N3wPassword!"}), 400,
                 "BAD_REQUEST")
    assert_ok(login(client, user.email))  # password unchanged


def test_change_password(client, make_user):
    user = make_user(email="jack@example.com")
    tokens = assert_ok(login(client, user.email))["data"]
    headers = bearer(tokens["accessToken"])
    url = f"{API}/auth/change-password"
    assert_error(client.post(url, json={"currentPassword": "Wr0ngPassword", "newPassword": "N3wPassword!"},
                             headers=headers), 400, "BAD_REQUEST")
    assert_error(client.post(url, json={"currentPassword": PASSWORD, "newPassword": "short"}, headers=headers), 422,
                 "VALIDATION_ERROR")
    assert_error(client.post(url, json={"currentPassword": PASSWORD, "newPassword": "N3wPassword!"}), 401,
                 "UNAUTHORIZED")
    assert_ok(client.post(url, json={"currentPassword": PASSWORD, "newPassword": "N3wPassword!"}, headers=headers))
    assert_error(login(client, user.email), 401, "UNAUTHORIZED")
    assert_ok(login(client, user.email, "N3wPassword!"))
    assert_error(client.post(f"{API}/auth/refresh", json={"refreshToken": tokens["refreshToken"]}), 401,
                 "UNAUTHORIZED")


# =========================================================================== OTP / email / mobile verification


def test_otp_login_flow(client, db, make_user):
    user = make_user(email="kate@example.com", mobile="9700000001", mobile_verified=False)
    sent = assert_ok(client.post(f"{API}/auth/send-otp", json={"identifier": "9700000001"}))["data"]
    otp = sent["devOtp"]
    assert len(otp) == settings.otp_length and otp.isdigit()

    assert_error(client.post(f"{API}/auth/login-otp", json={"identifier": "9700000001", "otp": "000000" if otp != "000000"
                                                            else "111111"}), 401, "UNAUTHORIZED")
    data = assert_ok(client.post(f"{API}/auth/login-otp", json={"identifier": "9700000001", "otp": otp}))["data"]
    assert data["user"]["id"] == str(user.id) and data["accessToken"] and data["user"]["mobileVerified"] is True
    assert_ok(client.get(f"{API}/auth/me", headers=bearer(data["accessToken"])))
    # an OTP is single-use
    assert_error(client.post(f"{API}/auth/login-otp", json={"identifier": "9700000001", "otp": otp}), 401,
                 "UNAUTHORIZED")


def test_otp_by_email_identifier_and_unknown_user(client, make_user):
    make_user(email="leo@example.com", mobile="9700000002")
    otp = assert_ok(client.post(f"{API}/auth/send-otp", json={"identifier": "leo@example.com"}))["data"]["devOtp"]
    assert assert_ok(client.post(f"{API}/auth/login-otp", json={"identifier": "leo@example.com", "otp": otp}))
    ghost = assert_ok(client.post(f"{API}/auth/send-otp", json={"identifier": "9111111111"}))["data"]
    assert "devOtp" not in ghost
    assert_error(client.post(f"{API}/auth/login-otp", json={"identifier": "9111111111", "otp": "123456"}), 401,
                 "UNAUTHORIZED")


def test_otp_expiry_and_attempt_limit(client, db, make_user):
    user = make_user(email="mia@example.com", mobile="9700000003")
    otp = assert_ok(client.post(f"{API}/auth/send-otp", json={"identifier": user.mobile}))["data"]["devOtp"]
    wrong = "999999" if otp != "999999" else "888888"
    for _ in range(settings.otp_max_attempts):
        assert_error(client.post(f"{API}/auth/login-otp", json={"identifier": user.mobile, "otp": wrong}), 401,
                     "UNAUTHORIZED")
    # too many wrong guesses burn the code - even the right one is refused now
    assert_error(client.post(f"{API}/auth/login-otp", json={"identifier": user.mobile, "otp": otp}), 401,
                 "UNAUTHORIZED")

    fresh = assert_ok(client.post(f"{API}/auth/send-otp", json={"identifier": user.mobile}))["data"]["devOtp"]
    db.query(OtpCode).filter(OtpCode.user_id == user.id, OtpCode.consumed_at.is_(None)).update(
        {"expires_at": utc_now() - timedelta(seconds=1)})
    db.commit()
    assert_error(client.post(f"{API}/auth/login-otp", json={"identifier": user.mobile, "otp": fresh}), 401,
                 "UNAUTHORIZED")


def test_new_otp_invalidates_the_previous_one(client, make_user):
    user = make_user(email="ned@example.com", mobile="9700000004")
    first = assert_ok(client.post(f"{API}/auth/send-otp", json={"identifier": user.mobile}))["data"]["devOtp"]
    second = assert_ok(client.post(f"{API}/auth/send-otp", json={"identifier": user.mobile}))["data"]["devOtp"]
    if first != second:
        assert_error(client.post(f"{API}/auth/login-otp", json={"identifier": user.mobile, "otp": first}), 401,
                     "UNAUTHORIZED")
    assert_ok(client.post(f"{API}/auth/login-otp", json={"identifier": user.mobile, "otp": second}))


def test_blocked_user_gets_no_otp(client, make_user):
    make_user(email="olga@example.com", mobile="9700000005", is_blocked=True)
    sent = assert_ok(client.post(f"{API}/auth/send-otp", json={"identifier": "9700000005"}))["data"]
    assert "devOtp" not in sent


def test_email_verification_flow(client, db):
    reg = assert_ok(client.post(f"{API}/auth/register", json=register_body()), 201)["data"]
    token = reg["devToken"]
    tokens = assert_ok(login(client, "new.seeker@example.com"))["data"]
    headers = bearer(tokens["accessToken"])
    assert assert_ok(client.get(f"{API}/auth/me", headers=headers))["data"]["emailVerified"] is False

    assert_error(client.post(f"{API}/auth/verify-email", json={"token": "bogus"}), 400, "BAD_REQUEST")
    verified = assert_ok(client.post(f"{API}/auth/verify-email", json={"token": token}))["data"]
    assert verified["emailVerified"] is True
    assert assert_ok(client.get(f"{API}/auth/me", headers=headers))["data"]["emailVerified"] is True
    assert_error(client.post(f"{API}/auth/verify-email", json={"token": token}), 400, "BAD_REQUEST")  # single use
    assert "already verified" in assert_ok(client.post(f"{API}/auth/resend-verification", headers=headers))["data"][
        "message"]


def test_resend_verification_issues_new_token(client, make_user):
    make_user(email="pat@example.com", email_verified=False)
    headers = bearer(assert_ok(login(client, "pat@example.com"))["data"]["accessToken"])
    token = assert_ok(client.post(f"{API}/auth/resend-verification", headers=headers))["data"]["devToken"]
    assert_ok(client.post(f"{API}/auth/verify-email", json={"token": token}))
    assert_error(client.post(f"{API}/auth/resend-verification"), 401, "UNAUTHORIZED")


def test_mobile_verification_flow(client, make_user):
    make_user(email="quinn@example.com", mobile="9700000006", mobile_verified=False)
    headers = bearer(assert_ok(login(client, "quinn@example.com"))["data"]["accessToken"])
    otp = assert_ok(client.post(f"{API}/auth/send-mobile-otp", headers=headers))["data"]["devOtp"]
    wrong = "999999" if otp != "999999" else "888888"
    assert_error(client.post(f"{API}/auth/verify-mobile", json={"otp": wrong}, headers=headers), 400, "BAD_REQUEST")
    assert assert_ok(client.post(f"{API}/auth/verify-mobile", json={"otp": otp}, headers=headers))["data"][
        "mobileVerified"] is True
    assert assert_ok(client.get(f"{API}/auth/me", headers=headers))["data"]["mobileVerified"] is True
    assert_error(client.post(f"{API}/auth/send-mobile-otp"), 401, "UNAUTHORIZED")


def test_register_then_login_as_recruiter_roles_are_in_token(client, make_user):
    user = make_user(UserRole.ADMIN, email="root@jobportal.test")
    data = assert_ok(login(client, user.email))["data"]
    claims = jwt.decode(data["accessToken"], settings.jwt_secret, algorithms=["HS256"])
    assert claims["role"] == "ADMIN" and claims["sub"] == str(user.id) and claims["type"] == "access"
