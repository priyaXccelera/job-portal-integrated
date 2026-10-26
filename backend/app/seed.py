"""Idempotent demo-data seeder.  Run with ``python -m app.seed``.

Phases (each in its own transaction): master data, accounts, seekers, jobs, applications,
engagement (saved jobs, alerts, follows, reviews, notifications, folders, unlocks, messages).
Natural keys (email / name / company+title / job+user ...) are checked before every insert, so
re-running the seeder creates nothing new.
"""

from __future__ import annotations

import logging
import random
import sys
import time
import uuid
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import seed_data as D
from app.config import settings
from app.core.security import hash_password
from app.db import SessionLocal, init_db
from app.models.accounts import Notification, NotificationPreference, User
from app.models.applications import (
    Application,
    ApplicationAnswer,
    ApplicationNote,
    Interview,
    Message,
    MessageThread,
    StatusHistory,
)
from app.models.company import (
    CandidateFolder,
    Company,
    CompanyFollow,
    CompanyReview,
    ContactUnlock,
    CreditLog,
    FolderCandidate,
)
from app.models.enums import (
    AlertFrequency,
    ApplicationStatus,
    CompanyStatus,
    CompanyType,
    EmploymentType,
    InterviewMode,
    InterviewResponse,
    JobStatus,
    JobType,
    QuestionType,
    ReportReason,
    ReviewStatus,
    UserRole,
    Visibility,
    WorkMode,
    WorkStatus,
)
from app.models.jobs import (
    Job,
    JobAlert,
    JobReport,
    RecentSearch,
    SavedJob,
    SavedSearch,
    ScreeningQuestion,
)
from app.models.master import (
    Degree,
    Department,
    Industry,
    Location,
    NoticePeriodOption,
    RoleCategory,
    Skill,
)
from app.models.profile import (
    Certification,
    Education,
    Employment,
    JobSeekerProfile,
    ProfileSkill,
    ProfileView,
    Project,
    Resume,
)
from app.services.job_index import reindex_all

logger = logging.getLogger("app.seed")

N_SEEKERS = 20
N_ACTIVE_JOBS = 60
AS = ApplicationStatus

# state-machine paths used to build consistent StatusHistory rows
_PATHS: dict[str, list[list[ApplicationStatus]]] = {
    "APPLIED": [[AS.APPLIED]],
    "VIEWED": [[AS.APPLIED, AS.VIEWED]],
    "SHORTLISTED": [[AS.APPLIED, AS.VIEWED, AS.SHORTLISTED]],
    "INTERVIEW_SCHEDULED": [[AS.APPLIED, AS.VIEWED, AS.SHORTLISTED, AS.INTERVIEW_SCHEDULED]],
    "OFFERED": [
        [AS.APPLIED, AS.VIEWED, AS.SHORTLISTED, AS.OFFERED],
        [AS.APPLIED, AS.VIEWED, AS.SHORTLISTED, AS.INTERVIEW_SCHEDULED, AS.OFFERED],
    ],
    "HIRED": [[AS.APPLIED, AS.VIEWED, AS.SHORTLISTED, AS.INTERVIEW_SCHEDULED, AS.OFFERED, AS.HIRED]],
    "REJECTED": [
        [AS.APPLIED, AS.REJECTED],
        [AS.APPLIED, AS.VIEWED, AS.REJECTED],
        [AS.APPLIED, AS.VIEWED, AS.SHORTLISTED, AS.REJECTED],
    ],
    "WITHDRAWN": [[AS.APPLIED, AS.WITHDRAWN], [AS.APPLIED, AS.VIEWED, AS.WITHDRAWN]],
}

_STATUS_COUNTS = [
    ("APPLIED", 20), ("VIEWED", 15), ("SHORTLISTED", 13), ("INTERVIEW_SCHEDULED", 11),
    ("OFFERED", 5), ("HIRED", 4), ("REJECTED", 8), ("WITHDRAWN", 4),
]
_STEP_MESSAGES = {
    AS.APPLIED: "Application submitted",
    AS.VIEWED: "Application viewed by recruiter",
    AS.SHORTLISTED: "Profile shortlisted for the next round",
    AS.INTERVIEW_SCHEDULED: "Interview scheduled",
    AS.OFFERED: "Offer extended to the candidate",
    AS.HIRED: "Candidate accepted the offer and was hired",
    AS.REJECTED: "Thank you for your interest; we will not be moving forward at this time",
    AS.WITHDRAWN: "Application withdrawn by the candidate",
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _rng(*parts: Any) -> random.Random:
    """Deterministic RNG per purpose (str seeds hash deterministically, unlike ``hash()``)."""
    return random.Random("|".join(str(p) for p in parts))


def _transitions() -> dict:
    try:
        from app.services.applications import ALLOWED_TRANSITIONS

        return ALLOWED_TRANSITIONS
    except ImportError:  # pragma: no cover - fallback copy of the documented state machine
        return {
            AS.APPLIED: {AS.VIEWED, AS.SHORTLISTED, AS.REJECTED, AS.WITHDRAWN},
            AS.VIEWED: {AS.SHORTLISTED, AS.REJECTED, AS.WITHDRAWN},
            AS.SHORTLISTED: {AS.INTERVIEW_SCHEDULED, AS.OFFERED, AS.REJECTED, AS.WITHDRAWN},
            AS.INTERVIEW_SCHEDULED: {AS.SHORTLISTED, AS.OFFERED, AS.REJECTED, AS.WITHDRAWN},
            AS.OFFERED: {AS.HIRED, AS.REJECTED, AS.WITHDRAWN},
            AS.HIRED: set(), AS.REJECTED: set(), AS.WITHDRAWN: set(),
        }


def _match_fn():
    try:
        from app.services.matching import match_score

        return match_score
    except ImportError:  # pragma: no cover

        def fallback(job_skills, candidate_skills):
            required = [s for s in job_skills or [] if s]
            have = {s.casefold() for s in candidate_skills or []}
            matching = [s for s in required if s.casefold() in have]
            missing = [s for s in required if s.casefold() not in have]
            pct = round(100 * len(matching) / len(required)) if required else 100
            return {"percentage": pct, "matchingSkills": matching, "missingSkills": missing}

        return fallback


class Seeder:
    def __init__(self) -> None:
        self.created: Counter[str] = Counter()

    def add(self, db: Session, obj: Any) -> Any:
        db.add(obj)
        self.created[type(obj).__name__] += 1
        return obj

    # ------------------------------------------------------------------ phase 1: master data
    def phase_master(self, db: Session) -> None:
        def sync_names(model: type, names: list[str]) -> None:
            existing = set(db.scalars(select(model.name)).all())
            for name in names:
                if name not in existing:
                    self.add(db, model(name=name))

        existing_skills = set(db.scalars(select(Skill.name)).all())
        for name in D.SKILLS:
            if name not in existing_skills:
                self.add(db, Skill(name=name, synonyms=D.SKILL_SYNONYMS.get(name, []), is_active=True))
        sync_names(Industry, D.INDUSTRIES)
        sync_names(Department, D.DEPARTMENTS)
        sync_names(RoleCategory, D.ROLE_CATEGORIES)

        existing_loc = set(db.execute(select(Location.name, Location.state)).all())
        for city, state in D.CITIES:
            if (city, state) not in existing_loc:
                self.add(db, Location(name=city, state=state, country="India"))

        existing_deg = set(db.scalars(select(Degree.name)).all())
        for name, specs in D.DEGREES.items():
            if name not in existing_deg:
                self.add(db, Degree(name=name, specializations=specs))

        existing_np = set(db.scalars(select(NoticePeriodOption.name)).all())
        for name, days in D.NOTICE_PERIODS:
            if name not in existing_np:
                self.add(db, NoticePeriodOption(name=name, days=days))

    # ------------------------------------------------------------------ phase 2: accounts
    def _new_user(self, db: Session, *, name: str, email: str, mobile: str, password: str,
                  role: UserRole, company_id: uuid.UUID | None = None, admin: bool = False) -> User:
        user = User(
            id=uuid.uuid4(), name=name, email=email.lower(), mobile=mobile,
            password_hash=hash_password(password), role=role, email_verified=True,
            mobile_verified=True, is_blocked=False, company_id=company_id, is_company_admin=admin,
            last_active_at=_now(),
        )
        return self.add(db, user)

    def phase_accounts(self, db: Session) -> None:
        if db.scalar(select(User).where(User.email == settings.seed_admin_email.lower())) is None:
            self._new_user(db, name=D.ADMIN["name"], email=settings.seed_admin_email,
                           mobile=D.ADMIN["mobile"], password=settings.seed_admin_password,
                           role=UserRole.ADMIN)
        for spec in D.COMPANIES:
            company = db.scalar(select(Company).where(Company.name == spec["name"], Company.deleted_at.is_(None)))
            recruiter_spec = spec["recruiter"]
            recruiter = db.scalar(select(User).where(User.email == recruiter_spec["email"]))
            if company is None:
                company_id = uuid.uuid4()
                slug = spec["name"].lower().replace(" ", "-")
                company = Company(
                    id=company_id, name=spec["name"], website=f"https://www.{spec['domain']}",
                    industry=spec["industry"], company_type=CompanyType(spec["type"]),
                    size_range=spec["size_range"], founded_year=spec["founded_year"],
                    headquarters=spec["headquarters"], description=spec["description"],
                    benefits=spec["benefits"], gallery=[],
                    social_links={"linkedin": f"https://www.linkedin.com/company/{slug}",
                                  "twitter": f"https://twitter.com/{slug.replace('-', '')}"},
                    verified=True, status=CompanyStatus.APPROVED, credits=settings.demo_credits,
                    job_quota=100, jobs_posted=0,
                )
                self.add(db, company)
                db.flush()
                self.add(db, CreditLog(company_id=company.id, delta=settings.demo_credits,
                                       balance_after=settings.demo_credits, reason="Demo credits",
                                       ref_type="seed"))
            if recruiter is None:
                recruiter = self._new_user(
                    db, name=recruiter_spec["name"], email=recruiter_spec["email"],
                    mobile=recruiter_spec["mobile"], password=settings.seed_recruiter_password,
                    role=UserRole.RECRUITER, company_id=company.id, admin=True)
                if company.created_by is None:
                    company.created_by = recruiter.id
            db.flush()

    # ------------------------------------------------------------------ phase 3: seekers
    @staticmethod
    def seeker_email(i: int) -> str:
        return f"seeker{i + 1}@example.com"

    @staticmethod
    def _resume_pdf(lines: list[str]) -> bytes:
        def esc(s: str) -> str:
            return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")

        ops = ["BT", "/F1 11 Tf", "14 TL", "50 790 Td"]
        for line in lines:
            ops.append(f"({esc(line)}) Tj")
            ops.append("T*")
        ops.append("ET")
        stream = "\n".join(ops).encode("latin-1", errors="replace")
        objs = [
            b"<< /Type /Catalog /Pages 2 0 R >>",
            b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents 4 0 R "
            b"/Resources << /Font << /F1 5 0 R >> >> >>",
            b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        ]
        out = bytearray(b"%PDF-1.4\n")
        offsets = []
        for n, body in enumerate(objs, start=1):
            offsets.append(len(out))
            out += f"{n} 0 obj\n".encode() + body + b"\nendobj\n"
        xref = len(out)
        out += f"xref\n0 {len(objs) + 1}\n".encode() + b"0000000000 65535 f \n"
        for off in offsets:
            out += f"{off:010d} 00000 n \n".encode()
        out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
        return bytes(out)

    def _seeker_blueprint(self, i: int) -> dict[str, Any]:
        arch = D.SEEKER_ARCHETYPES[i % 10]
        variant = i // 10
        name = D.SEEKER_NAMES[i]
        years = 2 + (i * 3) % 9
        months = (i * 5) % 12
        city = D.CITIES[(i * 3) % 20][0]
        prefs = [city] + [D.CITIES[(i + k * 5) % 12][0] for k in (1, 2)]
        skills = [(n, max(1, min(y - variant, years))) for n, y in arch["skills"]]
        return {"arch": arch, "variant": variant, "name": name, "years": years, "months": months,
                "city": city, "prefs": list(dict.fromkeys(prefs)), "skills": skills,
                "mobile": f"+91982000{i + 1:04d}"}

    def _resume_lines(self, i: int, bp: dict[str, Any]) -> list[str]:
        arch = bp["arch"]
        lines = [bp["name"], arch["headline"], f"{self.seeker_email(i)} | {bp['mobile']} | {bp['city']}",
                 "", "SUMMARY",
                 f"{arch['role']} with {bp['years']}+ years of experience delivering production systems.",
                 "", "SKILLS", ", ".join(n for n, _ in bp["skills"]), "", "EXPERIENCE",
                 f"{arch['role']} - {D.EMPLOYERS[i % len(D.EMPLOYERS)]}",
                 "", "EDUCATION", f"{arch['degree'][0]} {arch['degree'][1]}"]
        return lines

    def _write_resume_file(self, path: Path, i: int, bp: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(self._resume_pdf(self._resume_lines(i, bp)))

    def phase_seekers(self, db: Session) -> None:
        skill_ids = {n: sid for sid, n in db.execute(select(Skill.id, Skill.name)).all()}
        notice_names = [n for n, _ in D.NOTICE_PERIODS]
        today = date.today()
        try:
            from app.services.resume_parser import get_parser

            parser = get_parser()
        except ImportError:  # pragma: no cover
            parser = None

        for i in range(N_SEEKERS):
            email = self.seeker_email(i)
            bp = self._seeker_blueprint(i)
            user = db.scalar(select(User).where(User.email == email))
            if user is not None:
                # repair a resume file that went missing (e.g. a fresh uploads volume)
                for resume in db.scalars(select(Resume).where(Resume.user_id == user.id)).all():
                    path = Path(resume.file_path)
                    if not path.exists() and resume.file_name.endswith("_Resume.pdf"):
                        self._write_resume_file(path, i, bp)
                continue
            arch, years, name = bp["arch"], bp["years"], bp["name"]
            user = self._new_user(db, name=name, email=email, mobile=bp["mobile"],
                                  password=settings.seed_seeker_password, role=UserRole.JOB_SEEKER)
            db.flush()
            uid = user.id
            current_ctc = Decimal(int((4 + years * 1.6) * 10) * 10000)
            visibility = (Visibility.HIDDEN if i == 18 else
                          Visibility.APPLIED_ONLY if i in (9, 14) else Visibility.ALL_RECRUITERS)
            slug = name.lower().replace(" ", "-")
            profiles = {"linkedin": f"https://www.linkedin.com/in/{slug}"}
            if arch["role_category"] in ("Software Development", "Data Science and Machine Learning",
                                         "DevOps and Cloud", "Mobile Development",
                                         "Quality Assurance and Testing"):
                profiles["github"] = f"https://github.com/{slug.replace('-', '')}"
            if i % 3 == 0:
                profiles["portfolio"] = f"https://{slug}.dev"
            rng = _rng("seeker", i)
            languages = [{"name": "English", "proficiency": "Fluent"}, {"name": "Hindi", "proficiency": "Fluent"}]
            extra = D.LANGUAGES[2 + i % 5]
            languages.append({"name": extra[0], "proficiency": extra[1]})
            self.add(db, JobSeekerProfile(
                user_id=uid, headline=arch["headline"],
                summary=(f"{arch['role']} with {years} years {bp['months']} months of experience in "
                         f"{arch['industry']}. Strong in {', '.join(n for n, _ in bp['skills'][:3])} and "
                         f"passionate about building reliable, user-focused solutions. "
                         f"Open to opportunities in {', '.join(bp['prefs'])}."),
                current_location=bp["city"], preferred_locations=bp["prefs"],
                dob=date(today.year - 23 - years - i % 4, 1 + (i * 5) % 12, 1 + (i * 7) % 28),
                gender="Male" if i % 2 == 0 else "Female", experience_years=years,
                experience_months=bp["months"], notice_period=notice_names[i % 5],
                current_ctc=current_ctc, expected_ctc=(current_ctc * Decimal("1.3")).quantize(Decimal("1")),
                work_status=WorkStatus.EXPERIENCED, languages=languages, online_profiles=profiles,
                visibility=visibility, actively_looking=(i % 4 != 3),
                desired_industry=arch["industry"], desired_department=arch["department"],
                desired_role_category=arch["role_category"],
                desired_job_type="CONTRACT" if i == 13 else "PERMANENT",
                desired_employment_type="FULL_TIME", desired_shift=["Day", "Flexible", "Night"][i % 3],
                desired_locations=bp["prefs"]))
            for skill_name, yrs in bp["skills"]:
                self.add(db, ProfileSkill(user_id=uid, skill_id=skill_ids[skill_name],
                                          years_of_experience=Decimal(str(yrs))))
            # employments (1-3), newest first
            n_emp = 1 + i % 3
            dur = max(1, round(years / n_emp))
            end = today
            for k in range(n_emp):
                start = end - timedelta(days=365 * dur - rng.randint(0, 60))
                title = arch["role"] if k == 0 else ("Associate " + arch["role"] if k == 1 else "Trainee Engineer")
                self.add(db, Employment(
                    user_id=uid, company_name=D.EMPLOYERS[(i + k * 7) % len(D.EMPLOYERS)],
                    designation=title, start_date=start, end_date=None if k == 0 else end,
                    is_current=(k == 0),
                    description=f"Worked on {', '.join(n for n, _ in bp['skills'][k:k + 3])}; owned delivery "
                                f"of key modules and collaborated with product and QA teams.",
                    location=bp["city"]))
                end = start - timedelta(days=rng.randint(10, 40))
            # educations (1-2)
            deg, spec = arch["degree"]
            grad = today.year - years - 1
            self.add(db, Education(user_id=uid, degree=deg, specialization=spec,
                                   institute=D.INSTITUTES[i % len(D.INSTITUTES)], start_year=grad - 2,
                                   end_year=grad, grade=f"{7 + (i % 3)}.{(i * 3) % 10} CGPA"))
            lower = {"M.Tech": ("B.Tech/B.E.", "Computer Science"), "MBA": ("B.Com", "Accounting & Finance"),
                     "MCA": ("BCA", "Computer Applications")}.get(deg)
            if lower:
                self.add(db, Education(user_id=uid, degree=lower[0], specialization=lower[1],
                                       institute=D.INSTITUTES[(i + 3) % len(D.INSTITUTES)],
                                       start_year=grad - 5, end_year=grad - 2, grade="First Class"))
            # projects (1-2)
            for k, title in enumerate(arch["projects"][: 1 + i % 2]):
                self.add(db, Project(
                    user_id=uid, title=title, url=f"https://{slug}.dev/projects/{k + 1}" if k == 0 else None,
                    description=f"{title}: designed and delivered end to end using "
                                f"{', '.join(n for n, _ in bp['skills'][:3])}.",
                    start_date=today - timedelta(days=700 - k * 200), end_date=today - timedelta(days=400 - k * 150),
                    skills=[n for n, _ in bp["skills"][:3]]))
            if i % 3 != 2:
                self.add(db, Certification(user_id=uid, name=arch["cert"][0], issuer=arch["cert"][1],
                                           issued_date=today - timedelta(days=200 + i * 20),
                                           expiry_date=today + timedelta(days=900 - i * 10),
                                           credential_url=f"https://credentials.example.com/{slug}/{i + 1}"))
            # resume: a small, real PDF so download / parsing work
            fname = f"{name.replace(' ', '_')}_Resume.pdf"
            path = Path(settings.upload_dir) / "resumes" / str(uid) / f"{uuid.uuid4().hex}.pdf"
            self._write_resume_file(path, i, bp)
            parsed = [n for n, _ in bp["skills"]]
            if parser is not None:
                parsed = list(parser.parse(path, D.SKILLS).get("skills") or parsed)
            self.add(db, Resume(user_id=uid, file_name=fname, file_path=str(path),
                                content_type="application/pdf", size_bytes=path.stat().st_size,
                                is_default=True, parsed_skills=parsed))
            db.flush()

        # notification preferences for every user lacking one
        missing = db.scalars(select(User).outerjoin(NotificationPreference, NotificationPreference.user_id == User.id)
                             .where(NotificationPreference.user_id.is_(None))).all()
        for u in missing:
            self.add(db, NotificationPreference(user_id=u.id, categories={}, email_frequency="INSTANT",
                                                new_applicant_digest=(u.role == UserRole.RECRUITER)))

    # ------------------------------------------------------------------ phase 4: jobs
    @staticmethod
    def active_job_spec(i: int) -> dict[str, Any]:
        tpl = D.JOB_TEMPLATES[i % len(D.JOB_TEMPLATES)]
        level = i // len(D.JOB_TEMPLATES)
        title = tpl[0] if level == 0 else f"Senior {tpl[0]}"
        return {"tpl": tpl, "level": level, "title": title, "company_idx": tpl[9]}

    def _job_fields(self, i: int, tpl: tuple, level: int, title: str, company: Company,
                    recruiter: User, status: JobStatus, now: datetime) -> dict[str, Any]:
        (_, industry, dept, role_cat, req, pref, (e_min, e_max), (s_min, s_max), edu, _c, blurb) = tpl
        factor = 1.0
        if level:
            e_min, e_max, factor = e_min + 3, e_max + 4, 1.6
        n = 60 + i  # variation key, independent from the list position of extras
        city = D.CITIES[(i * 7) % len(D.CITIES)][0]
        locations = [city]
        if i % 4 == 1:
            locations.append(D.CITIES[(i * 7 + 13) % len(D.CITIES)][0])
        if i % 10 == 2:
            locations.append(D.CITIES[(i * 7 + 29) % len(D.CITIES)][0])
        if i % 3 == 0:
            locations.append("Bengaluru")  # the busiest hiring hub: keep several jobs searchable there
        locations = list(dict.fromkeys(locations))
        work_mode = [WorkMode.ONSITE, WorkMode.HYBRID, WorkMode.REMOTE, WorkMode.HYBRID, WorkMode.ONSITE][i % 5]
        job_type = JobType.CONTRACT if i % 9 == 4 else JobType.PERMANENT
        emp_type = EmploymentType.PART_TIME if i % 13 == 6 else EmploymentType.FULL_TIME
        walk_in = i % 12 == 5
        details: dict | None = None
        deadline: date | None = None
        if walk_in:
            when = date.today() + timedelta(days=7 + i % 10)
            details = {"date": when.isoformat(), "time": "10:00 AM - 4:00 PM",
                       "venue": f"{company.name}, {city} office",
                       "contactPerson": recruiter.name, "contactNumber": recruiter.mobile,
                       "documents": "Updated resume and photo ID"}
            deadline = when
        elif i % 3 == 0:
            deadline = date.today() + timedelta(days=20 + i % 15)
        years_txt = f"{e_min}-{e_max} years"
        description = (
            f"<p><strong>{company.name}</strong> is looking for a <strong>{title}</strong> to {blurb}.</p>"
            f"<p>You will work with {', '.join(req[:-1])} and {req[-1]} in a collaborative team, "
            f"with typically {years_txt} of relevant experience. This role is based in "
            f"{' / '.join(locations)} ({work_mode.value.title()} work mode).</p>"
            f"<p>Nice to have: {', '.join(pref)}. We offer competitive compensation, learning support "
            f"and a transparent growth path.</p>")
        responsibilities = (
            f"<ul><li>Own delivery of core work using {req[0]} and {req[1]}.</li>"
            f"<li>Apply {req[2]} best practices and keep quality high.</li>"
            f"<li>Collaborate with cross-functional stakeholders and clients.</li>"
            f"<li>Document decisions, share knowledge and mentor peers.</li>"
            f"<li>Continuously improve processes, tooling and outcomes.</li></ul>")
        d = (i * 5) % 25
        posted = now - timedelta(days=d, hours=1 + (i * 37) % 23)
        fields: dict[str, Any] = dict(
            company_id=company.id, posted_by=recruiter.id, title=title, description=description,
            responsibilities=responsibilities, required_skills=list(req), preferred_skills=list(pref),
            experience_min=Decimal(e_min), experience_max=Decimal(e_max),
            salary_min=Decimal(int(s_min * factor * 10) * 10000), salary_max=Decimal(int(s_max * factor * 10) * 10000),
            hide_salary=(i % 11 == 3), job_type=job_type, employment_type=emp_type, work_mode=work_mode,
            locations=locations, openings=1 + i % 5, industry=industry, department=dept,
            role_category=role_cat, education=edu,
            notice_preference=([x for x, _ in D.NOTICE_PERIODS][i % 5] if i % 3 else None),
            is_walk_in=walk_in, walk_in_details=details, deadline=deadline, status=status,
            view_count=20 + (n * 37) % 400, application_count=0)
        if status == JobStatus.DRAFT:
            fields.update(posted_at=None, expires_at=None, view_count=0)
        else:
            expiry_days = max(settings.job_expiry_days, 30)
            fields.update(posted_at=posted, expires_at=posted + timedelta(days=expiry_days))
        return fields

    def _add_questions(self, db: Session, job: Job, i: int, e_min: Decimal) -> None:
        notice_knock = i % 8 == 0
        qs = [
            ScreeningQuestion(job_id=job.id, text=f"Do you have at least {int(e_min)} years of relevant experience?",
                              question_type=QuestionType.YES_NO, options=[], is_knockout=True,
                              expected_answer="YES", is_required=True, position=0),
            ScreeningQuestion(job_id=job.id, text="What is your current notice period?",
                              question_type=QuestionType.MULTIPLE_CHOICE,
                              options=[x for x, _ in D.NOTICE_PERIODS], is_knockout=notice_knock,
                              expected_answer='["Immediate","15 Days","30 Days"]' if notice_knock else None,
                              is_required=True, position=1),
            ScreeningQuestion(job_id=job.id, text="Briefly describe your most relevant project.",
                              question_type=QuestionType.TEXT, options=[], is_knockout=False,
                              expected_answer=None, is_required=False, position=2),
        ]
        for q in qs:
            self.add(db, q)

    def phase_jobs(self, db: Session) -> None:
        now = _now()
        companies = [db.scalar(select(Company).where(Company.name == c["name"], Company.deleted_at.is_(None)))
                     for c in D.COMPANIES]
        recruiters = [db.scalar(select(User).where(User.email == c["recruiter"]["email"])) for c in D.COMPANIES]
        for i in range(N_ACTIVE_JOBS):
            spec = self.active_job_spec(i)
            company, recruiter = companies[spec["company_idx"]], recruiters[spec["company_idx"]]
            if db.scalar(select(Job.id).where(Job.company_id == company.id, Job.title == spec["title"],
                                              Job.deleted_at.is_(None))):
                continue
            fields = self._job_fields(i, spec["tpl"], spec["level"], spec["title"], company, recruiter,
                                      JobStatus.ACTIVE, now)
            job = self.add(db, Job(id=uuid.uuid4(), **fields))
            db.flush()
            if i % 4 == 0:
                self._add_questions(db, job, i, fields["experience_min"])
        for k, (tpl_idx, prefix, status) in enumerate(D.EXTRA_JOBS):
            tpl = D.JOB_TEMPLATES[tpl_idx]
            company, recruiter = companies[tpl[9]], recruiters[tpl[9]]
            title = f"{prefix} {tpl[0]}"
            if db.scalar(select(Job.id).where(Job.company_id == company.id, Job.title == title,
                                              Job.deleted_at.is_(None))):
                continue
            fields = self._job_fields(100 + k * 3, tpl, 1, title, company, recruiter, JobStatus(status), now)
            if status != "DRAFT":
                posted = now - timedelta(days=12 + k * 2)
                fields.update(posted_at=posted, expires_at=posted + timedelta(days=30))
            self.add(db, Job(id=uuid.uuid4(), **fields))
        db.flush()
        # counters: jobs that ever left DRAFT
        for company in companies:
            posted = db.scalar(select(func.count()).select_from(Job).where(
                Job.company_id == company.id, Job.deleted_at.is_(None), Job.status != JobStatus.DRAFT)) or 0
            company.jobs_posted = posted
        reindex_all(db)

    # ------------------------------------------------------------------ phase 5: applications
    def _active_jobs(self, db: Session) -> list[Job]:
        companies = {c.name: c for c in db.scalars(select(Company).where(
            Company.name.in_([c["name"] for c in D.COMPANIES]), Company.deleted_at.is_(None))).all()}
        by_key = {(j.company_id, j.title): j for j in db.scalars(select(Job).where(
            Job.company_id.in_([c.id for c in companies.values()]), Job.deleted_at.is_(None))).all()}
        out = []
        for i in range(N_ACTIVE_JOBS):
            spec = self.active_job_spec(i)
            cid = companies[D.COMPANIES[spec["company_idx"]]["name"]].id
            out.append(by_key[(cid, spec["title"])])
        return out

    def _plan(self, skill_sets: list[list[str]], jobs: list[Job]) -> list[dict[str, Any]]:
        match = _match_fn()
        statuses = [s for s, c in _STATUS_COUNTS for _ in range(c)]
        random.Random("status-plan").shuffle(statuses)
        plan: list[dict[str, Any]] = []
        applied: list[set[int]] = []
        k = 0
        for s in range(N_SEEKERS):
            variant = s // 10
            ranked = sorted(range(len(jobs)), key=lambda j: (-match(jobs[j].required_skills, skill_sets[s])["percentage"],
                                                              -j if variant else j))
            picks = ranked[:4]
            applied.append(set(picks))
            for j in picks:
                plan.append({"seeker": s, "job": j, "status": statuses[k], "screened": False, "k": k})
                k += 1
        question_jobs = list(range(0, N_ACTIVE_JOBS, 4))
        for n, s in enumerate((1, 8, 14)):
            options = [j for j in question_jobs if j not in applied[s]]
            plan.append({"seeker": s, "job": options[n % len(options)], "status": "APPLIED",
                         "screened": True, "k": k})
            k += 1
        return plan

    def phase_applications(self, db: Session) -> None:
        match = _match_fn()
        transitions = _transitions()
        now = _now()
        jobs = self._active_jobs(db)
        users = {u.email: u for u in db.scalars(select(User)).all()}
        seekers = [users[self.seeker_email(i)] for i in range(N_SEEKERS)]
        recruiters = [users[c["recruiter"]["email"]] for c in D.COMPANIES]
        companies = {c.id: c for c in db.scalars(select(Company)).all()}
        skill_sets = []
        for s in seekers:
            skill_sets.append(list(db.scalars(select(Skill.name).join(ProfileSkill, ProfileSkill.skill_id == Skill.id)
                                              .where(ProfileSkill.user_id == s.id)).all()))
        profiles = {p.user_id: p for p in db.scalars(select(JobSeekerProfile)).all()}
        resumes = {r.user_id: r for r in db.scalars(select(Resume).where(Resume.is_default.is_(True))).all()}
        questions: dict[uuid.UUID, list[ScreeningQuestion]] = {}
        for q in db.scalars(select(ScreeningQuestion).order_by(ScreeningQuestion.position)).all():
            questions.setdefault(q.job_id, []).append(q)

        notes_added = 0
        for entry in self._plan(skill_sets, jobs):
            seeker, job = seekers[entry["seeker"]], jobs[entry["job"]]
            if db.scalar(select(Application.id).where(Application.job_id == job.id, Application.user_id == seeker.id)):
                continue
            k = entry["k"]
            recruiter = recruiters[self.active_job_spec(entry["job"])["company_idx"]]
            path = _rng("path", k).choice(_PATHS[entry["status"]])
            for a, b in zip(path, path[1:]):
                assert b in transitions[a], f"seed path violates state machine: {a} -> {b}"
            screened = entry["screened"]
            score = match(job.required_skills, skill_sets[entry["seeker"]])["percentage"]
            # timeline
            t = job.posted_at + timedelta(hours=2 + (k * 7) % 48)
            times: list[datetime] = []
            for idx in range(len(path)):
                cap = now - timedelta(minutes=(len(path) - idx) * 5)
                times.append(min(t, cap))
                t += timedelta(hours=_rng("step", k, idx).randint(3, 30))
            profile = profiles[seeker.id]
            final = path[-1]
            viewed_at = times[path.index(AS.VIEWED)] if AS.VIEWED in path else None
            app = self.add(db, Application(
                id=uuid.uuid4(), job_id=job.id, user_id=seeker.id,
                resume_id=resumes[seeker.id].id if seeker.id in resumes else None,
                cover_note=f"Hello team, I am excited about the {job.title} role and believe my experience "
                           f"with {', '.join(skill_sets[entry['seeker']][:2])} is a strong fit.",
                expected_ctc=profile.expected_ctc, notice_period=profile.notice_period, status=final,
                screened_out=screened,
                screen_reason=f"Failed knockout question: {questions[job.id][0].text}" if screened else None,
                rating=(3 + k % 3) if final in (AS.SHORTLISTED, AS.INTERVIEW_SCHEDULED, AS.OFFERED, AS.HIRED) else None,
                match_score=score, applied_at=times[0], updated_at=times[-1], viewed_at=viewed_at))
            db.flush()
            for step, at in zip(path, times):
                by_candidate = step in (AS.APPLIED, AS.WITHDRAWN)
                self.add(db, StatusHistory(application_id=app.id, status=step, message=_STEP_MESSAGES[step],
                                           changed_by=seeker.id if by_candidate else recruiter.id, created_at=at))
            # answers to screening questions
            for q in questions.get(job.id, []):
                if q.question_type == QuestionType.YES_NO:
                    answer = "NO" if screened else "YES"
                elif q.question_type == QuestionType.MULTIPLE_CHOICE:
                    answer = ["Immediate", "15 Days", "30 Days"][k % 3]
                else:
                    answer = (f"I built a production system using {', '.join(skill_sets[entry['seeker']][:3])} "
                              f"serving thousands of users.")
                self.add(db, ApplicationAnswer(application_id=app.id, question_id=q.id, answer=answer))
            # interviews
            if AS.INTERVIEW_SCHEDULED in path:
                mode = [InterviewMode.VIDEO, InterviewMode.PHONE, InterviewMode.IN_PERSON][k % 3]
                if final == AS.INTERVIEW_SCHEDULED:
                    when = (now + timedelta(days=2 + k % 8)).replace(hour=10 + k % 6, minute=0, second=0, microsecond=0)
                    response = (InterviewResponse.CONFIRM if k % 3 == 0 else
                                InterviewResponse.RESCHEDULE if k % 7 == 0 else None)
                else:
                    when = times[path.index(AS.INTERVIEW_SCHEDULED)] + timedelta(days=2)
                    response = InterviewResponse.CONFIRM
                where = {InterviewMode.VIDEO: f"https://meet.example.com/{uuid.uuid4().hex[:3]}-{uuid.uuid4().hex[:4]}",
                         InterviewMode.PHONE: f"Recruiter will call {seeker.mobile}",
                         InterviewMode.IN_PERSON: f"{companies[job.company_id].name}, {job.locations[0]} office"}[mode]
                self.add(db, Interview(
                    application_id=app.id, scheduled_at=when, mode=mode, location_or_link=where,
                    notes="Technical discussion followed by a culture-fit round. Carry a photo ID.",
                    candidate_response=response,
                    response_note="Could we move this to the afternoon, please?" if response == InterviewResponse.RESCHEDULE else None,
                    created_by=recruiter.id, created_at=times[path.index(AS.INTERVIEW_SCHEDULED)]))
            if final in (AS.SHORTLISTED, AS.INTERVIEW_SCHEDULED, AS.OFFERED, AS.HIRED) and notes_added < 10:
                self.add(db, ApplicationNote(application_id=app.id, author_id=recruiter.id,
                                             note=f"Strong match on {', '.join(skill_sets[entry['seeker']][:2])}; "
                                                  f"discuss compensation expectations."))
                notes_added += 1
        db.flush()
        # application_count = non-withdrawn applications (matches the withdraw logic of the API)
        counts = dict(db.execute(select(Application.job_id, func.count()).where(
            Application.status != AS.WITHDRAWN).group_by(Application.job_id)).all())
        for job in db.scalars(select(Job).where(Job.deleted_at.is_(None))).all():
            if job.application_count != counts.get(job.id, 0):
                job.application_count = counts.get(job.id, 0)

    # ------------------------------------------------------------------ phase 6: engagement
    def _notify(self, db: Session, user_id: uuid.UUID, category: str, title: str, body: str,
                data: dict | None = None, read: bool = False, age_hours: int = 6) -> None:
        if db.scalar(select(Notification.id).where(Notification.user_id == user_id, Notification.category == category,
                                                   Notification.title == title)):
            return
        self.add(db, Notification(user_id=user_id, category=category, title=title[:255], body=body, data=data,
                                  is_read=read, created_at=_now() - timedelta(hours=age_hours)))

    def phase_engagement(self, db: Session) -> None:
        now = _now()
        jobs = self._active_jobs(db)
        users = {u.email: u for u in db.scalars(select(User)).all()}
        seekers = [users[self.seeker_email(i)] for i in range(N_SEEKERS)]
        recruiters = [users[c["recruiter"]["email"]] for c in D.COMPANIES]
        companies = [db.scalar(select(Company).where(Company.name == c["name"])) for c in D.COMPANIES]
        apps = db.scalars(select(Application).order_by(Application.applied_at)).all()
        applied_pairs = {(a.user_id, a.job_id) for a in apps}
        job_index = {j.id: n for n, j in enumerate(jobs)}

        # saved jobs: 2 per seeker, jobs they have not applied to
        for s, seeker in enumerate(seekers):
            rng = _rng("saved", s)
            pool = [j for j in jobs if (seeker.id, j.id) not in applied_pairs]
            for job in rng.sample(pool, 2):
                if not db.scalar(select(SavedJob.id).where(SavedJob.user_id == seeker.id, SavedJob.job_id == job.id)):
                    self.add(db, SavedJob(user_id=seeker.id, job_id=job.id,
                                          created_at=now - timedelta(hours=rng.randint(2, 200))))

        # job alerts: 15 seekers, all frequencies
        freqs = [AlertFrequency.instant, AlertFrequency.daily, AlertFrequency.weekly]
        alert_seekers = [s for s in range(N_SEEKERS) if s % 4 != 3]
        for n, s in enumerate(alert_seekers):
            arch = D.SEEKER_ARCHETYPES[s % 10]
            keyword = arch["skills"][0][0]
            city = D.CITIES[(s * 3) % 20][0]
            name = f"{keyword} jobs in {city}"
            if not db.scalar(select(JobAlert.id).where(JobAlert.user_id == seekers[s].id, JobAlert.name == name)):
                self.add(db, JobAlert(user_id=seekers[s].id, name=name, keywords=keyword, locations=[city],
                                      experience=Decimal(2 + (s * 3) % 9), salary_min=Decimal(600000 + s * 50000),
                                      frequency=freqs[n % 3], is_paused=(n == 7)))

        # recent + saved searches
        for s, seeker in enumerate(seekers):
            arch = D.SEEKER_ARCHETYPES[s % 10]
            queries = [(arch["skills"][0][0], {"location": D.CITIES[(s * 3) % 20][0]}),
                       (arch["headline"].split("|")[0].strip(), {}),
                       (arch["skills"][1][0], {"workMode": "REMOTE"})][: 2 + s % 2]
            for n, (query, filters) in enumerate(queries):
                if not db.scalar(select(RecentSearch.id).where(RecentSearch.user_id == seeker.id,
                                                               RecentSearch.query == query)):
                    self.add(db, RecentSearch(user_id=seeker.id, query=query, filters=filters or None,
                                              created_at=now - timedelta(hours=3 + n * 20 + s)))
            if s % 3 == 0:
                name = f"{arch['skills'][0][0]} roles"
                if not db.scalar(select(SavedSearch.id).where(SavedSearch.user_id == seeker.id, SavedSearch.name == name)):
                    self.add(db, SavedSearch(user_id=seeker.id, name=name, query=arch["skills"][0][0],
                                             filters={"experience": 3 + s % 4}))

        # company follows (one per seeker)
        for s, seeker in enumerate(seekers):
            company = companies[s % 3]
            if not db.scalar(select(CompanyFollow.id).where(CompanyFollow.user_id == seeker.id,
                                                            CompanyFollow.company_id == company.id)):
                self.add(db, CompanyFollow(user_id=seeker.id, company_id=company.id))

        # reviews
        reviews = [
            (0, 0, 5, "Great engineering culture", "Ownership, modern stack and supportive managers.", ReviewStatus.APPROVED),
            (1, 0, 4, "Fast-paced and rewarding", "Lots of learning; deadlines can be tight.", ReviewStatus.APPROVED),
            (2, 1, 4, "Good exposure to clients", "Varied projects and helpful recruiters.", ReviewStatus.APPROVED),
            (3, 2, 4, "Stable and well-structured", "Clear processes and good benefits.", ReviewStatus.APPROVED),
            (4, 2, 3, "Slow decision making", "Hiring process is thorough but takes time.", ReviewStatus.APPROVED),
            (5, 1, 2, "Needs moderation sample", "Awaiting admin review.", ReviewStatus.PENDING),
        ]
        for s, c, rating, title, body, status in reviews:
            if not db.scalar(select(CompanyReview.id).where(CompanyReview.company_id == companies[c].id,
                                                            CompanyReview.user_id == seekers[s].id)):
                self.add(db, CompanyReview(company_id=companies[c].id, user_id=seekers[s].id, rating=rating,
                                           title=title, body=body, status=status))

        # job reports for the admin queue
        for n, (s, j, reason) in enumerate([(6, 14, ReportReason.SPAM), (11, 33, ReportReason.MISLEADING)]):
            if not db.scalar(select(JobReport.id).where(JobReport.job_id == jobs[j].id, JobReport.user_id == seekers[s].id)):
                self.add(db, JobReport(job_id=jobs[j].id, user_id=seekers[s].id, reason=reason,
                                       details="Posting looks inconsistent with the company's profile."))

        # talent pool: folders, unlocks and profile views for company 1 (TechNova)
        tn, rec1 = companies[0], recruiters[0]
        unlock_targets = [seekers[0], seekers[2], seekers[4]]
        for cand in unlock_targets:
            if not db.scalar(select(ContactUnlock.id).where(ContactUnlock.company_id == tn.id,
                                                            ContactUnlock.candidate_id == cand.id)):
                self.add(db, ContactUnlock(company_id=tn.id, candidate_id=cand.id, unlocked_by=rec1.id))
                db.flush()
                locked = db.scalar(select(Company).where(Company.id == tn.id).with_for_update())
                locked.credits -= settings.unlock_credit_cost
                self.add(db, CreditLog(company_id=tn.id, user_id=rec1.id, delta=-settings.unlock_credit_cost,
                                       balance_after=locked.credits, reason="Contact unlock",
                                       ref_type="candidate", ref_id=str(cand.id)))
        folders = {"Shortlisted Python Talent": [seekers[0], seekers[10], seekers[2]],
                   "Interview Pipeline": [seekers[4], seekers[1]]}
        for fname, members in folders.items():
            folder = db.scalar(select(CandidateFolder).where(CandidateFolder.company_id == tn.id,
                                                             CandidateFolder.name == fname))
            if folder is None:
                folder = self.add(db, CandidateFolder(company_id=tn.id, name=fname, created_by=rec1.id))
                db.flush()
                for m in members:
                    self.add(db, FolderCandidate(folder_id=folder.id, candidate_id=m.id,
                                                 note="Added from candidate search"))
        for n, cand in enumerate([seekers[0], seekers[2], seekers[4], seekers[10], seekers[1]]):
            if not db.scalar(select(ProfileView.id).where(ProfileView.candidate_id == cand.id,
                                                          ProfileView.recruiter_id == rec1.id)):
                self.add(db, ProfileView(candidate_id=cand.id, recruiter_id=rec1.id, company_id=tn.id,
                                         viewed_at=now - timedelta(days=n, hours=3)))

        # notifications
        for rec, comp in zip(recruiters, companies):
            self._notify(db, rec.id, "RECRUITER_APPROVED", "Your company has been approved",
                         f"{comp.name} is verified. You can now post jobs and search candidates.", age_hours=300)
        shown = 0
        cat = {AS.VIEWED: "APPLICATION_VIEWED", AS.SHORTLISTED: "APPLICATION_SHORTLISTED",
               AS.INTERVIEW_SCHEDULED: "INTERVIEW_SCHEDULED"}
        for a in apps:
            if shown >= 14 or a.status == AS.APPLIED:
                continue
            title = jobs[job_index[a.job_id]].title
            company = next(c for c in companies if c.id == jobs[job_index[a.job_id]].company_id)
            self._notify(db, a.user_id, cat.get(a.status, "STATUS_CHANGE"),
                         f"Update on your application for {title}",
                         f"Your application at {company.name} is now {a.status.value.replace('_', ' ').title()}.",
                         data={"applicationId": str(a.id), "jobId": str(a.job_id)}, read=(shown % 3 == 0),
                         age_hours=10 + shown * 5)
            shown += 1
        new_app = 0
        for a in apps:
            job = jobs[job_index[a.job_id]]
            if new_app >= 6 or a.status != AS.APPLIED:
                continue
            rec = recruiters[next(i for i, c in enumerate(companies) if c.id == job.company_id)]
            self._notify(db, rec.id, "NEW_APPLICANT", f"New applicant for {job.title}",
                         "A candidate has applied and is waiting for your review.",
                         data={"applicationId": str(a.id), "jobId": str(job.id)}, age_hours=2 + new_app * 3)
            new_app += 1
        for s in range(5):
            job = jobs[(s * 11 + 3) % N_ACTIVE_JOBS]
            self._notify(db, seekers[s].id, "JOB_ALERT", f"New jobs matching your alert: {job.title}",
                         f"{job.title} was just posted in {job.locations[0]}.", data={"jobId": str(job.id)},
                         age_hours=20 + s)
        for s in (0, 1, 2):
            self._notify(db, seekers[s].id, "PROFILE_VIEWED", "A recruiter viewed your profile",
                         f"A recruiter from {tn.name} viewed your profile.", age_hours=30 + s)

        # message thread: recruiter1 <-> a TechNova applicant
        tn_jobs = {j.id for j in jobs if j.company_id == tn.id}
        target = next((a for a in apps if a.job_id in tn_jobs and a.status != AS.WITHDRAWN), None)
        if target is not None:
            candidate = next(s for s in seekers if s.id == target.user_id)
            thread = db.scalar(select(MessageThread).where(MessageThread.recruiter_id == rec1.id,
                                                           MessageThread.candidate_id == candidate.id))
            if thread is None:
                job_title = jobs[job_index[target.job_id]].title
                thread = self.add(db, MessageThread(recruiter_id=rec1.id, candidate_id=candidate.id,
                                                    company_id=tn.id, created_at=now - timedelta(days=2)))
                db.flush()
                convo = [
                    (rec1, f"Hi {candidate.name.split()[0]}, thanks for applying to {job_title} at {tn.name}. "
                           f"Do you have time for a quick call this week?", True),
                    (candidate, "Hello! Thanks for reaching out. Yes, I am available Thursday or Friday afternoon.", True),
                    (rec1, "Great, let's do Thursday at 3 PM. I will share a calendar invite shortly.", True),
                    (candidate, "Perfect, looking forward to it.", False),
                ]
                last = now
                for n, (sender, body, is_read) in enumerate(convo):
                    last = now - timedelta(hours=40 - n * 9)
                    self.add(db, Message(thread_id=thread.id, sender_id=sender.id, body=body, created_at=last,
                                         read_at=(last + timedelta(minutes=20)) if is_read else None))
                thread.last_message_at = last

    # ------------------------------------------------------------------ orchestration
    def run(self) -> None:
        started = time.perf_counter()
        init_db()
        phases = [("master data", self.phase_master), ("accounts", self.phase_accounts),
                  ("seekers", self.phase_seekers), ("jobs", self.phase_jobs),
                  ("applications", self.phase_applications), ("engagement", self.phase_engagement)]
        for label, fn in phases:
            before = Counter(self.created)
            t0 = time.perf_counter()
            with SessionLocal() as db:
                try:
                    fn(db)
                    db.commit()
                except BaseException:
                    db.rollback()
                    logger.exception("Seed phase '%s' failed; transaction rolled back", label)
                    raise
            delta = self.created - before
            logger.info("Phase %-13s done in %.1fs - created %s", label, time.perf_counter() - t0,
                        dict(delta) if delta else "nothing (already seeded)")
        self.log_totals()
        logger.info("Seeding finished in %.1fs; rows created this run: %d", time.perf_counter() - started,
                    sum(self.created.values()))

    @staticmethod
    def log_totals() -> None:
        with SessionLocal() as db:
            def n(model: type, *where: Any) -> int:
                return db.scalar(select(func.count()).select_from(model).where(*where)) or 0

            totals = {
                "skills": n(Skill), "industries": n(Industry), "departments": n(Department),
                "role_categories": n(RoleCategory), "locations": n(Location), "degrees": n(Degree),
                "notice_periods": n(NoticePeriodOption),
                "users": n(User), "admins": n(User, User.role == UserRole.ADMIN),
                "recruiters": n(User, User.role == UserRole.RECRUITER),
                "seekers": n(User, User.role == UserRole.JOB_SEEKER),
                "companies": n(Company), "jobs_total": n(Job), "jobs_active": n(Job, Job.status == JobStatus.ACTIVE),
                "screening_questions": n(ScreeningQuestion), "applications": n(Application),
                "status_history": n(StatusHistory), "interviews": n(Interview), "saved_jobs": n(SavedJob),
                "job_alerts": n(JobAlert), "recent_searches": n(RecentSearch), "company_follows": n(CompanyFollow),
                "reviews": n(CompanyReview), "notifications": n(Notification),
                "notification_preferences": n(NotificationPreference), "folders": n(CandidateFolder),
                "contact_unlocks": n(ContactUnlock), "credit_logs": n(CreditLog), "threads": n(MessageThread),
                "messages": n(Message), "resumes": n(Resume),
            }
            distinct_cities = len({c for locs in db.scalars(select(Job.locations).where(Job.status == JobStatus.ACTIVE)).all()
                                   for c in locs})
        logger.info("Totals: %s", totals)
        logger.info("Distinct cities across ACTIVE jobs: %d", distinct_cities)


def main() -> None:
    logging.basicConfig(level=logging.INFO, stream=sys.stdout,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s", force=True)
    Seeder().run()


if __name__ == "__main__":
    main()
