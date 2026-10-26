# online-job-portal-frontend

A Naukri-style job portal frontend with public job and company search, job seeker tools (profile, resumes, applications, alerts), recruiter tools (job posting, applicant pipeline, candidate database) and an admin area (approvals, moderation, master data, analytics). It follows the `/api/v1` REST contract and runs on local demo data when no backend is available.

## Tech stack
React + TypeScript, Vite, Tailwind CSS, React Router, axios.

## Getting started
```
npm install --legacy-peer-deps
cp .env.example .env
npm run dev
```
Then open http://localhost:38687

Other scripts: `npm run build`, `npm test` (Vitest).

Docker: `docker build -t jobportal-frontend --build-arg VITE_API_URL=https://api.example.com --build-arg VITE_DEMO_MODE=false .` then `docker run -p 8080:80 jobportal-frontend`.

## Environment variables
See .env.example. VITE_API_URL is optional — every entity runs on local
mock data (USE_MOCK = true in src/data/storeCore.ts and src/auth/auth.ts) until it's set and each
entity's flag is flipped to false.

- `VITE_API_URL` — backend origin (the app appends `/api/v1`).
- `VITE_DEMO_MODE` — demo/mock switch. Anything except `false` serves sample data from the browser (localStorage). Set `false` to call the real backend.

## Demo credentials
Common password for every demo account: `Password@123`

| Role | Login |
|------|-------|
| Admin | admin@jobportal.com |
| Recruiter | recruiter1@company.com (approved company), recruiter2@company.com (company pending approval) |
| Job seeker | seeker1@mail.com … seeker5@mail.com |

In demo mode every OTP / reset code is `123456`; any non-empty email verification token works.

## Project structure
- `src/pages` — one component per screen (plus co-located smoke tests)
- `src/components` — layout, header/footer, job cards, drawers, modals, form fields, Kanban board
- `src/data` — mock data, localStorage store and the gated data-access functions (`store.ts`)
- `src/api` — shared axios client (auth header, token refresh, error toasts)
- `src/auth` — session handling, login/signup/OTP gates
- `src/hooks` — useAsync, debounce, SEO, unsaved-changes and media-query hooks
- `src/constants` — shared literal values and option lists
- `src/validation` — reusable field validators and post-job step validation
- `src/utils` — formatting (lakhs, dates, relative time), CSV, boolean search, HTML sanitising
- `src/routes` — router configuration
- `src/test` — behaviour tests (search/URL sync, apply flow, post-job validation, Kanban, route protection)
