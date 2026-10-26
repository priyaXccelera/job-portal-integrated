# Job Portal API

A Naukri-style online job portal back end: job seekers search and apply, recruiters post jobs and
manage applicants, admins moderate. Everything is served under `/api/v1`.

## Stack

| Layer | Technology |
|---|---|
| Language / runtime | Python 3.13.5 |
| Web framework | FastAPI 0.115.6 (served by uvicorn) |
| ORM / driver | SQLAlchemy 2.x with psycopg 3 (`postgresql+psycopg://`) |
| Database | PostgreSQL 17.2 (`postgres:17.2` image), `pg_trgm` extension |
| Validation / settings | pydantic 2 / pydantic-settings |
| Scheduler | APScheduler (in-process) |
| Tests | pytest against a real PostgreSQL database |

No Alembic: the schema is created by an idempotent `init_db()` (extension + `create_all` + search
indexes) that runs on application start and at the beginning of the seeder.

## Architecture / layout

```
app/
  main.py            FastAPI app, lifespan (init_db, scheduler, graceful shutdown), CORS, routers
  config.py          Environment based settings (fails fast without DATABASE_URL / JWT_SECRET)
  db.py              Engine, session factory, Base, init_db()
  seed.py            Idempotent demo data seeder  (python -m app.seed)
  seed_data.py       Constant lists used by the seeder (skills, cities, job templates ...)
  core/              errors (JSON envelope), responses (ok/paged/csv), security (JWT, bcrypt),
                     deps (auth/RBAC), ratelimit
  models/            SQLAlchemy 2 models (accounts, master, profile, company, jobs, applications)
  schemas/           pydantic request bodies (camelCase aliases)
  services/          business logic: search, matching, applications, alerts, credits,
                     candidate search, jobs lifecycle, notifications, senders, scheduler ...
  routers/           thin HTTP layer: auth, seeker, profile, recruiter, recruiter_jobs,
                     admin, public, common
tests/               pytest suite (real PostgreSQL)
Dockerfile, docker-compose.yml, .env.example
```

Layering: routers -> services -> models. Routers only parse input and serialise output; JSON is
camelCase, dates are `YYYY-MM-DD`, timestamps are ISO-8601 UTC (`...Z`). All primary keys are UUIDs.
Users, jobs and companies are soft-deleted (`deleted_at`).

## Configuration

All configuration is environment based. **`.env.example` is the reference for every variable**
(copy it to `.env` and adjust). `DATABASE_URL` and `JWT_SECRET` are required; the application refuses
to start without them. Frequently used ones:

| Variable | Purpose | Default |
|---|---|---|
| `DATABASE_URL` | SQLAlchemy URL (`postgresql://` is normalised to psycopg 3) | required |
| `JWT_SECRET` | JWT signing secret | required |
| `ACCESS_TOKEN_MINUTES` / `REFRESH_TOKEN_DAYS` | Token lifetimes | 30 / 7 |
| `EXPOSE_DEV_CODES` | Return `devOtp` / `devToken` in auth responses (dev only) | false in code, `true` in compose / `.env.example` |
| `CORS_ORIGINS` | Comma separated allowed origins | `*` |
| `FREE_EMAIL_DOMAINS` | Domains blocked for recruiter registration | gmail.com, yahoo.com, ... |
| `MAX_RESUME_MB`, `MAX_IMAGE_MB`, `UPLOAD_DIR` | Upload limits and location | 5, 2, `uploads` |
| `JOB_EXPIRY_DAYS`, `DEFAULT_JOB_QUOTA` | Job lifetime and quota for new companies | 30, 10 |
| `DEMO_CREDITS` | Credits given to seeded companies | 50 |
| `UNLOCK_CREDIT_COST`, `INVITE_CREDIT_COST` | Credit prices | 1, 2 |
| `RATE_LIMIT_*` | Rate limiting (see below) | enabled |
| `SCHEDULER_ENABLED` | Run background jobs | true |
| `MAX_PAGE_SIZE`, `DEFAULT_PAGE_SIZE` | Pagination | 100, 20 |
| `EMAIL_SENDER`, `OTP_SENDER` | Pluggable senders (`log` writes to the application log) | log |
| `SEED_*_PASSWORD`, `SEED_ADMIN_EMAIL` | Demo credentials used by the seeder | see below |

## Run with Docker Compose

```bash
docker compose up -d --build              # PostgreSQL 17.2 + API on http://localhost:8000
docker compose exec api python -m app.seed   # load demo data (safe to run repeatedly)
# tests run from a separate image that adds pytest/httpx (the runtime image has runtime deps only):
docker build --target test -t jobportal-test .
docker run --rm --network <compose-project>_default -e DATABASE_URL=postgresql://postgres:postgres@db:5432/app -e JWT_SECRET=testsecret jobportal-test pytest -q
```

The compose project works without a `.env` file (all values have defaults). The database is
published on host port `55432` (override with `DB_HOST_PORT`), the API on `8000` (`API_HOST_PORT`).
Uploads live in the `uploads` volume and the database in the `pgdata` volume.

* Interactive API docs (Swagger UI): <http://localhost:8000/docs>
* Health check: <http://localhost:8000/health> (also `/api/v1/health`)

## Local development without Docker

```bash
python3.13 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env                       # point DATABASE_URL at a PostgreSQL 17 instance
# e.g. start only the database from compose:  docker compose up -d db   (host port 55432)
python -m app.seed                         # optional demo data
uvicorn app.main:app --reload --port 8000
pytest -q                                  # derives <db name>_test from DATABASE_URL
```

## Seed data

`python -m app.seed` runs six transactional phases (master data, accounts, seekers, jobs,
applications, engagement). It is **idempotent**: every row is looked up by a natural key (email,
name, company + title, job + user ...) before insertion, so a second run creates nothing and logs
`created nothing (already seeded)` for each phase. Progress and final table counts are logged at INFO to stdout.

What it creates (when run against an empty database):

| Area | Content |
|---|---|
| Master data | 320 skills with synonyms (e.g. JavaScript: js, ecmascript; Kubernetes: k8s), 15 industries, 20 departments (functional areas), 30 role categories, 50 Indian cities (state + country), 19 degrees with specializations, 5 notice periods |
| Accounts | 1 admin, 3 APPROVED + verified companies each with one recruiter (company admin), 20 seekers; all email and mobile verified |
| Companies | TechNova Solutions (STARTUP, IT), GreenLeaf Consulting (CONSULTANCY), Finserve Bank (CORPORATE); `DEMO_CREDITS` credits each (with a "Demo credits" credit-log row), job quota 100 |
| Seekers | Complete profiles: headline, summary, locations, DOB, experience, CTCs, 7-8 skills with years, 1-3 employments, 1-2 educations, projects, certifications, languages, online profiles, career preferences, a resume PDF (stored under `UPLOAD_DIR/resumes/<user id>/`, skills parsed), mixed visibility (17 ALL_RECRUITERS, 2 APPLIED_ONLY, 1 HIDDEN) |
| Jobs | 60 ACTIVE jobs spread over all 15 industries and all 50 cities (some multi-city, some remote, some hidden salary, some walk-in), posted over the last 25 days and expiring 30 days after posting; screening questions (YES/NO knockout, multiple choice, text) on 15 jobs; plus 2 DRAFT, 2 PAUSED and 2 CLOSED jobs (totals: 66 jobs after the first run). Company `jobs_posted` counters match |
| Activity | 83 applications in every status (including 3 auto screened-out) with consistent status history, interviews, notes and answers; saved jobs, job alerts (instant / daily / weekly), recent and saved searches, company follows, reviews (5 approved, 1 pending), job reports, notifications, talent-pool folders, contact unlocks (with credit-log entries), profile views and a recruiter-candidate message thread |

### Demo credentials

| Role | Login (email) | Password | Notes |
|---|---|---|---|
| Admin | `admin@jobportal.demo` | `Admin@12345` | |
| Recruiter | `recruiter1@technova.com` | `Recruiter@123` | TechNova Solutions (company admin) |
| Recruiter | `recruiter2@greenleaf.in` | `Recruiter@123` | GreenLeaf Consulting (consultancy, company admin) |
| Recruiter | `recruiter3@finserve.co.in` | `Recruiter@123` | Finserve Bank (company admin) |
| Job seeker | `seeker1@example.com` ... `seeker20@example.com` | `Seeker@12345` | Complete profiles; seeker 10 and 15 are APPLIED_ONLY, seeker 19 is HIDDEN |

Passwords come from `SEED_ADMIN_PASSWORD`, `SEED_RECRUITER_PASSWORD`, `SEED_SEEKER_PASSWORD`
(defaults above). Seeker mobile numbers are `+919820000001` ... `+919820000020`; login also works with a mobile number.
Change these credentials for anything other than local use.

## API overview

All routes are under `/api/v1` (Swagger UI at `/docs` lists every request and response schema).

| Group | Routes (prefix `/api/v1`) | Access |
|---|---|---|
| Auth | `POST /auth/register`, `/auth/login`, `/auth/send-otp`, `/auth/login-otp`, `/auth/refresh`, `/auth/logout`, `/auth/logout-all`, `/auth/verify-email`, `/auth/resend-verification`, `/auth/send-mobile-otp`, `/auth/verify-mobile`, `/auth/forgot-password`, `/auth/reset-password`, `/auth/change-password`; `GET /auth/me` | public / any user |
| Public search | `GET /jobs/search`, `/jobs/{id}`, `/jobs/{id}/similar`, `/jobs/{id}/company-jobs`, `/suggestions`, `/companies/{id}`, `/companies/{id}/jobs`, `/companies/{id}/reviews`, `/master/{type}` (skills, industries, departments, role-categories, locations, degrees, notice-periods) | public (auth optional) |
| Seeker | `GET /jobs/saved`, `/jobs/recommended`, `/jobs/based-on-searches`; `POST/DELETE /jobs/{id}/save`; `POST /jobs/{id}/report`, `/jobs/{id}/apply`; `GET /applications/me`, `/applications/{id}`; `POST /applications/{id}/withdraw`, `/applications/{id}/interview-response`; `/job-alerts` CRUD + pause/resume; `/companies/following`, `POST/DELETE /companies/{id}/follow`, `POST /companies/{id}/reviews`; `/searches/recent`, `/searches/saved` | job seeker |
| Profile | `/profile/me`, `/profile/completeness`, `/profile/photo`, `/profile/skills`, `/profile/employments`, `/educations`, `/projects`, `/certifications`, `/profile/languages`, `/profile/online-profiles`, `/profile/career-preferences`, `/profile/privacy`, `/profile/hidden-companies`, `/profile/views`; `/resumes` (upload, list, download, set default, parse, delete) | job seeker |
| Recruiter company | `/recruiter/company` (+ logo, banner, recruiters, invitations), `/recruiter/credits`, `/recruiter/credits/log`, `/recruiter/candidates/search`, `/recruiter/candidates/{id}` (+ `/unlock`, `/invite`), `/recruiter/folders` (+ candidates) | recruiter |
| Recruiter jobs | `/recruiter/dashboard`, `/recruiter/jobs` CRUD, `PATCH /recruiter/jobs/{id}/status`, `/jobs/{id}/duplicate`, `/jobs/{id}/refresh`, `/jobs/{id}/applicants` (+ `/export` CSV), `/recruiter/applications/{id}` (+ status, notes, rating, resume, interview), `/recruiter/applications/bulk-status`, `/bulk-reject` | recruiter (own company) |
| Admin | `/admin/companies` (+ status, verify, credits, quota), `/admin/jobs` (+ moderation queue, status), `/admin/job-reports`, `/admin/reviews`, `/admin/master/{type}` CRUD, `/admin/users` (+ block, unblock, reset-verification), `/admin/analytics` (+ `/export` CSV), `/admin/audit-logs` | admin |
| Common | `/notifications` (+ unread-count, read-all, read, delete), `/notification-preferences`, `/messages/threads` (+ messages, read), `/messages/unread-count`, `/files/{kind}/{filename}` (public images), `GET /health` | authenticated (health, files public) |

Lists are paginated in the database with `page` (default 1) and `pageSize` (default 20, max 100) and
sortable via `sort` / `order` where documented.

### Response envelope

```jsonc
// success
{ "success": true, "data": { ... } }
// list endpoints
{ "success": true, "data": [ ... ], "meta": { "page": 1, "pageSize": 20, "total": 60, "facets": { ... } } }  // facets only on job search
// error
{ "success": false, "error": { "code": "VALIDATION_ERROR", "message": "...", "details": [ { "field": "email", "message": "..." } ] } }
```

| Code | HTTP | Meaning |
|---|---|---|
| `VALIDATION_ERROR` | 422 | Schema / parameter validation failed (invalid UUIDs included) |
| `MALFORMED_BODY` | 400 | Body is not valid JSON |
| `BAD_REQUEST` / `JOB_CLOSED` | 400 | Invalid request / job closed or expired |
| `UNAUTHORIZED` | 401 | Missing or invalid credentials |
| `FORBIDDEN` / `QUOTA_EXCEEDED` | 403 | Role or ownership violation / job quota reached |
| `NOT_FOUND` | 404 | Unknown resource or route |
| `METHOD_NOT_ALLOWED` | 405 | Wrong method (`Allow` header is sent) |
| `CONFLICT` / `DUPLICATE_APPLICATION` / `INVALID_TRANSITION` | 409 | Conflicts, duplicate application, illegal status change |
| `INSUFFICIENT_CREDITS` | 402 | Not enough credits (e.g. unlocking a contact) |
| `RATE_LIMITED` | 429 | Too many requests |
| `INTERNAL_ERROR` | 500 | Unexpected error (no stack trace in the response) |

## Authentication flow

1. `POST /auth/register` (`name, email, mobile, password, role`, plus `companyName` for recruiters).
   Recruiters must use a work email (free domains from `FREE_EMAIL_DOMAINS` are rejected); the first
   recruiter creates a PENDING company and becomes its company admin. Jobs of unapproved companies go to
   moderation (`PENDING_REVIEW`).
2. Verify the email with a token (`/auth/verify-email`) and the mobile with an OTP (`/auth/send-mobile-otp`, `/auth/verify-mobile`).
   Delivery goes through the pluggable email / OTP senders; the default `log` sender writes the
   message to the application log. With `EXPOSE_DEV_CODES=true` the responses also carry
   `devOtp` / `devToken` so the flow can be exercised without a mail or SMS gateway. **Dev only - disable in production.**
3. `POST /auth/login` with `identifier` (email or mobile) and `password`, or `POST /auth/send-otp` then `POST /auth/login-otp`.
   The response contains a short-lived JWT access token and a refresh token.
4. Send `Authorization: Bearer <accessToken>`. `POST /auth/refresh` rotates the refresh token;
   `POST /auth/logout` revokes it. Blocked or soft-deleted users cannot log in.
5. Password reset: `/auth/forgot-password` then `/auth/reset-password`; `/auth/change-password` when signed in.

Missing or invalid credentials return a `401` JSON envelope; wrong role or ownership returns `403`.
Recruiters only see applicants of their own company's jobs.

## Search

`GET /jobs/search` (public, rate limited) supports:

* **Keyword relevance** over title, skills, company name and description, using PostgreSQL full-text search
  with weights (title and skills above company name above description); multiple keywords are supported.
* **Synonyms** from the master skills (`js` finds JavaScript jobs, `k8s` finds Kubernetes ...).
* **Typo tolerance** through `pg_trgm` similarity.
* **Filters** (multi-values comma separated): `location`, `experience`, `salaryMin`/`salaryMax`, `department`,
  `roleCategory`, `industry`, `companyType`, `company`, `jobType`, `employmentType`, `workMode`, `education`,
  `freshness` (1/3/7/15/30 days), posted by company or consultancy, walk-in only.
* **Sorting** by relevance or date, paginated in the database, with **facet counts** per filter dimension in `meta.facets`.
* `GET /suggestions` typeahead (job titles, skills, companies, locations), recent and saved searches per user,
  recommended jobs and jobs based on recent searches, similar jobs and a company's other jobs.
* Job detail adds `isApplied`, `isSaved`, a `matchScore` (`percentage`, `matchingSkills`, `missingSkills`) and a
  view counter that increments once per user per day.

## Application state machine

```
APPLIED ──> VIEWED ──> SHORTLISTED ⇄ INTERVIEW_SCHEDULED ──> OFFERED ──> HIRED
   │                       ▲  │                                ▲
   │                       │  └────────────────────────────────┘  (SHORTLISTED -> OFFERED directly)
   └───────────────────────┘                                       (APPLIED -> SHORTLISTED directly)

Every non-terminal state can also go to REJECTED or WITHDRAWN.
REJECTED, WITHDRAWN and HIRED are terminal.
```

Allowed transitions:

| From | To |
|---|---|
| APPLIED | VIEWED, SHORTLISTED, REJECTED, WITHDRAWN |
| VIEWED | SHORTLISTED, REJECTED, WITHDRAWN |
| SHORTLISTED | INTERVIEW_SCHEDULED, OFFERED, REJECTED, WITHDRAWN |
| INTERVIEW_SCHEDULED | SHORTLISTED, OFFERED, REJECTED, WITHDRAWN |
| OFFERED | HIRED, REJECTED, WITHDRAWN |
| HIRED, REJECTED, WITHDRAWN | terminal |

Illegal changes return `409 INVALID_TRANSITION`. Every change is written to the status timeline and
notifies the candidate. Opening an application as a recruiter moves it APPLIED -> VIEWED. An application
that fails a knockout screening question stays `APPLIED` with `screenedOut=true` and a reason; recruiters can still see it.

## Jobs, credits and quota

Job statuses: `DRAFT`, `PENDING_REVIEW`, `ACTIVE`, `PAUSED`, `CLOSED`, `EXPIRED`, `REJECTED`. Jobs expire
`JOB_EXPIRY_DAYS` (30) days after posting. `jobs_posted` counts jobs that left DRAFT; publishing beyond
`job_quota` returns `403 QUOTA_EXCEEDED`. Unlocking a candidate's contact details costs `UNLOCK_CREDIT_COST`
credit (charged once per company and candidate) and inviting a candidate to apply costs `INVITE_CREDIT_COST`;
every change is recorded in the credit log (`GET /recruiter/credits`).

## Rate limits

In-memory sliding window per client IP (`RATE_LIMIT_WINDOW_SECONDS`, 60 s): login 30 (`RATE_LIMIT_LOGIN`),
OTP / verification / password-reset requests 15 (`RATE_LIMIT_OTP`), job search and suggestions 120
(`RATE_LIMIT_SEARCH`). Exceeding a limit returns `429 RATE_LIMITED`. Set `RATE_LIMIT_ENABLED=false` to disable (the test suite does).

## Scheduler

An in-process APScheduler starts with the API when `SCHEDULER_ENABLED=true` and is stopped on shutdown:

| Job | Schedule | Action |
|---|---|---|
| `expire_jobs` | every `SCHEDULER_EXPIRY_MINUTES` (60) | Expire jobs past `expires_at`, notify recruiters of jobs expiring within `EXPIRING_SOON_DAYS` |
| `alerts_instant` | every `SCHEDULER_ALERT_INSTANT_MINUTES` (5) | Dispatch `instant` job alerts |
| `alerts_daily` | daily 08:00 UTC | Dispatch `daily` job alerts |
| `alerts_weekly` | Mondays 08:00 UTC | Dispatch `weekly` job alerts |

Alert matches create in-app notifications and emails through the pluggable email sender.

## Uploads

* Resumes (PDF, DOC, DOCX; max `MAX_RESUME_MB`) are stored at `<UPLOAD_DIR>/resumes/<user id>/<uuid>.<ext>`
  and are never served publicly; the owner downloads them with `GET /resumes/{id}/download` and recruiters
  fetch an applicant's resume with `GET /recruiter/applications/{id}/resume`.
  A keyword-based parser (pluggable, `app/services/resume_parser.py`) extracts skills from uploads.
* Public images (logos, banners, photos; max `MAX_IMAGE_MB`) are stored under `<UPLOAD_DIR>/{logos,banners,photos}`
  and served by `GET /api/v1/files/{kind}/{filename}`.

## Testing

```bash
docker build --target test -t jobportal-test .
docker run --rm --network <compose-project>_default \
  -e DATABASE_URL=postgresql://postgres:postgres@db:5432/app -e JWT_SECRET=testsecret \
  jobportal-test pytest -q
```

The suite runs against a real PostgreSQL database (a separate `<name>_test` database is created and
reset automatically; the scheduler and, except for the rate-limit tests, rate limiting are disabled).

<!-- integrationx:deployment:start -->
## Deployment (via IntegrationX)

Integrated with a React 19 + Vite + TypeScript frontend by IntegrationX. Before deploying for real:

- **Frontend to backend routing**: In this job the frontend reached the backend through its dev-server proxy, which exists only while the dev server runs. For a real deployment, serve both from one origin (a reverse proxy) or set the frontend's API base URL to your deployed backend.
- **Secrets**: Any SECRET_KEY/JWT signing key, API keys, or passwords generated for this test run should be replaced with real, non-shared values before going live.
- **PostgreSQL (DATABASE_URL)**: This job used a local ephemeral PostgreSQL container with no persistent volume — its data does not survive a restart and is not meant for production. Point DATABASE_URL at a real, backed-up PostgreSQL instance.
- **CORS origins**: To make testing through a temporary address work, this job may have widened which origins the backend accepts (for example allow_origins=["*"]). Check your CORS configuration and restrict it to your real frontend's domain before deploying.
<!-- integrationx:deployment:end -->
