"""Test configuration: real PostgreSQL, isolated `<dbname>_test` database, factories.

The environment is prepared BEFORE the application is imported (settings are read at import time).
A test that cannot reach the database fails (this module raises at import) - nothing is skipped.
"""

from __future__ import annotations

import atexit
import itertools
import os
import shutil
import sys
import tempfile
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import psycopg
import pytest
from psycopg import sql
from sqlalchemy.engine import make_url

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


# --------------------------------------------------------------------------- environment / database


def _connect(url, dbname: str, retries: int = 15) -> psycopg.Connection:
    """Autocommit connection to ``dbname`` on the server of ``url`` (waits for the server to come up)."""
    last: Exception | None = None
    for _ in range(retries):
        try:
            return psycopg.connect(
                host=url.host,
                port=url.port or 5432,
                user=url.username,
                password=url.password,
                dbname=dbname,
                autocommit=True,
                connect_timeout=5,
                **{k: v for k, v in url.query.items() if isinstance(v, str)},
            )
        except psycopg.OperationalError as exc:  # pragma: no cover - only while the server boots
            last = exc
            time.sleep(1)
    raise RuntimeError(f"Cannot connect to PostgreSQL database '{dbname}' at {url.host}:{url.port}: {last}")


def _prepare_environment() -> str:
    raw = os.environ.get("DATABASE_URL")
    if not raw:
        raise RuntimeError("DATABASE_URL must point to a PostgreSQL server for the test-suite")
    url = make_url(raw)
    base = url.database or "postgres"
    test_db = base if base.endswith("_test") else f"{base}_test"

    conn = None
    for maintenance in ("postgres", base):
        try:
            conn = _connect(url, maintenance, retries=15 if maintenance == "postgres" else 2)
            break
        except RuntimeError:
            continue
    if conn is None:
        raise RuntimeError("Could not connect to PostgreSQL (tried the 'postgres' and application databases)")
    with conn:
        exists = conn.execute("SELECT 1 FROM pg_database WHERE datname = %s", (test_db,)).fetchone()
        if exists is None:
            conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(test_db)))

    # start every session from a clean schema (the app's init_db recreates everything)
    with _connect(url, test_db) as tconn:
        tconn.execute("DROP SCHEMA IF EXISTS public CASCADE")
        tconn.execute("CREATE SCHEMA public")

    upload_dir = tempfile.mkdtemp(prefix="jobportal-test-uploads-")
    atexit.register(shutil.rmtree, upload_dir, ignore_errors=True)

    os.environ["DATABASE_URL"] = url.set(database=test_db).render_as_string(hide_password=False)
    os.environ["RATE_LIMIT_ENABLED"] = "false"
    os.environ["SCHEDULER_ENABLED"] = "false"
    os.environ["EXPOSE_DEV_CODES"] = "true"
    os.environ["UPLOAD_DIR"] = upload_dir
    os.environ.setdefault("JWT_SECRET", "test-secret-" + "x" * 32)
    return test_db


TEST_DB_NAME = _prepare_environment()

# --- application imports (only after the environment is ready) ---
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.core.ratelimit import reset_rate_limits  # noqa: E402
from app.core.security import create_access_token, hash_password  # noqa: E402
from app.db import Base, SessionLocal, engine, init_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models.accounts import NotificationPreference, User  # noqa: E402
from app.models.applications import Application, StatusHistory  # noqa: E402
from app.models.company import Company  # noqa: E402
from app.models.enums import (  # noqa: E402
    ApplicationStatus,
    CompanyStatus,
    CompanyType,
    JobStatus,
    QuestionType,
    UserRole,
)
from app.models.jobs import Job, ScreeningQuestion  # noqa: E402
from app.models.master import Skill  # noqa: E402
from app.models.profile import JobSeekerProfile, ProfileSkill  # noqa: E402
from app.services.job_index import reindex_job  # noqa: E402

_counter = itertools.count(1)
_hash_cache: dict[str, str] = {}


def _hashed(password: str) -> str:
    if password not in _hash_cache:
        _hash_cache[password] = hash_password(password)
    return _hash_cache[password]


# --------------------------------------------------------------------------- fixtures


@pytest.fixture(scope="session", autouse=True)
def _schema() -> None:
    init_db()


@pytest.fixture(autouse=True)
def _clean_state(_schema):
    """Empty every table (identity restarted) and the in-memory rate limiter before each test."""
    names = ", ".join(f'"{t.name}"' for t in Base.metadata.sorted_tables)
    with engine.begin() as conn:
        conn.execute(text(f"TRUNCATE TABLE {names} RESTART IDENTITY CASCADE"))
    reset_rate_limits()
    yield
    reset_rate_limits()


@pytest.fixture(scope="session")
def client(_schema):
    with TestClient(app) as c:  # runs the lifespan (init_db, upload dirs) once
        yield c


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture
def reload(db):
    """reload(obj) -> fresh copy of ``obj`` from the database (sees changes made through the API)."""

    def _reload(obj):
        db.expire_all()
        return db.get(type(obj), obj.id)

    return _reload


@pytest.fixture
def make_company(db):
    def _make(
        status: CompanyStatus = CompanyStatus.APPROVED,
        credits: int = 50,
        job_quota: int = 10,
        name: str | None = None,
        company_type: CompanyType | None = CompanyType.CORPORATE,
        **kw,
    ) -> Company:
        n = next(_counter)
        company = Company(
            name=name or f"Acme Corp {n}",
            status=status,
            credits=credits,
            job_quota=job_quota,
            company_type=company_type,
            **kw,
        )
        db.add(company)
        db.commit()
        return company

    return _make


@pytest.fixture
def make_user(db):
    def _make(
        role: UserRole = UserRole.JOB_SEEKER,
        email: str | None = None,
        password: str = "Passw0rd1",
        company: Company | None = None,
        is_company_admin: bool = False,
        name: str | None = None,
        mobile: str | None = None,
        **kw,
    ) -> User:
        n = next(_counter)
        role = UserRole(role)
        if email is None:
            domain = {
                UserRole.JOB_SEEKER: "example.com",
                UserRole.RECRUITER: "acme-corp.com",
                UserRole.ADMIN: "jobportal.test",
            }[role]
            email = f"{role.value.lower()}{n}@{domain}"
        kw.setdefault("email_verified", True)
        kw.setdefault("mobile_verified", True)
        user = User(
            name=name or f"{role.value.title().replace('_', ' ')} {n}",
            email=email.lower(),
            mobile=mobile if mobile is not None else f"9{n:09d}",
            password_hash=_hashed(password),
            role=role,
            company_id=company.id if company is not None else None,
            is_company_admin=is_company_admin,
            **kw,
        )
        db.add(user)
        db.flush()
        db.add(NotificationPreference(user_id=user.id))
        if role == UserRole.JOB_SEEKER:
            db.add(JobSeekerProfile(user_id=user.id))
        db.commit()
        return user

    return _make


@pytest.fixture
def auth_headers():
    def _headers(user: User) -> dict[str, str]:
        token, _ = create_access_token(user)
        return {"Authorization": f"Bearer {token}"}

    return _headers


@pytest.fixture
def make_recruiter(make_user):
    def _make(company: Company, admin: bool = True, **kw) -> User:
        return make_user(UserRole.RECRUITER, company=company, is_company_admin=admin, **kw)

    return _make


@pytest.fixture
def make_admin(make_user):
    def _make(**kw) -> User:
        return make_user(UserRole.ADMIN, **kw)

    return _make


@pytest.fixture
def make_job(db):
    def _make(
        company: Company,
        posted_by: User | None = None,
        title: str = "Python Developer",
        required_skills: list[str] | None = None,
        status: JobStatus = JobStatus.ACTIVE,
        locations: list[str] | None = None,
        description: str = "Build and maintain backend services.",
        experience_min=None,
        experience_max=None,
        salary_min=None,
        salary_max=None,
        **kw,
    ) -> Job:
        now = datetime.now(timezone.utc)
        kw.setdefault("posted_at", now)
        if "expires_at" not in kw:
            kw["expires_at"] = now + timedelta(days=30)
        job = Job(
            company_id=company.id,
            posted_by=posted_by.id if posted_by is not None else None,
            title=title,
            description=description,
            required_skills=list(required_skills if required_skills is not None else ["Python"]),
            status=status,
            locations=list(locations if locations is not None else ["Bengaluru"]),
            experience_min=experience_min,
            experience_max=experience_max,
            salary_min=salary_min,
            salary_max=salary_max,
            **kw,
        )
        db.add(job)
        db.flush()
        reindex_job(db, job.id)
        db.commit()
        return job

    return _make


@pytest.fixture
def make_question(db):
    def _make(
        job: Job,
        text: str = "Are you authorised to work in India?",
        question_type: QuestionType = QuestionType.YES_NO,
        is_knockout: bool = False,
        expected_answer: str | None = None,
        options: list[str] | None = None,
        is_required: bool = True,
        position: int = 0,
    ) -> ScreeningQuestion:
        q = ScreeningQuestion(
            job_id=job.id,
            text=text,
            question_type=question_type,
            options=options or [],
            is_knockout=is_knockout,
            expected_answer=expected_answer,
            is_required=is_required,
            position=position,
        )
        db.add(q)
        db.commit()
        return q

    return _make


@pytest.fixture
def master_skills(db):
    """Minimal master skills (with synonyms) used by search and matching."""
    rows = {
        "Python": ["py", "python3"],
        "JavaScript": ["js", "ecmascript"],
        "Java": ["jdk"],
        "React": ["reactjs"],
        "SQL": ["structured query language"],
    }
    skills: dict[str, Skill] = {}
    for name, synonyms in rows.items():
        skill = Skill(name=name, synonyms=synonyms, is_active=True)
        db.add(skill)
        skills[name] = skill
    db.commit()
    return skills


@pytest.fixture
def make_seeker_with_skills(db, make_user):
    def _make(skill_names: list[str], **kw) -> User:
        user = make_user(UserRole.JOB_SEEKER, **kw)
        for skill_name in skill_names:
            skill = db.query(Skill).filter(Skill.name == skill_name).one_or_none()
            if skill is None:
                skill = Skill(name=skill_name, synonyms=[], is_active=True)
                db.add(skill)
                db.flush()
            db.add(ProfileSkill(user_id=user.id, skill_id=skill.id))
        db.commit()
        return user

    return _make


@pytest.fixture
def make_application(db):
    def _make(
        job: Job,
        user: User,
        status: ApplicationStatus = ApplicationStatus.APPLIED,
        **kw,
    ) -> Application:
        application = Application(job_id=job.id, user_id=user.id, status=status, **kw)
        db.add(application)
        db.flush()
        db.add(StatusHistory(application_id=application.id, status=ApplicationStatus.APPLIED, message="seed"))
        db.commit()
        return application

    return _make


@pytest.fixture
def approved_setup(make_company, make_recruiter, make_job):
    """(company, recruiter, job) for an APPROVED company with one ACTIVE job."""
    company = make_company()
    recruiter = make_recruiter(company)
    job = make_job(company, recruiter)
    return company, recruiter, job


def new_uuid() -> str:
    return str(uuid.uuid4())
