# online-job-portal-frontend — Routes & Navigation

## How to run
cd /workspace/frontend_runs/0c984545-0392-4fbb-96ea-5425f5e02cb7/project
npm install --legacy-peer-deps && npm run dev
Then open http://localhost:38687

## Routes

| Route | Page file | Description |
|-------|-----------|-------------|
| / | src/pages/Home.tsx | Public landing page (main screen): hero search, categories, companies, stats, featured jobs |
| /jobs | src/pages/JobSearch.tsx | Job search; every filter, sort and page lives in the URL; right-side detail panel on wide screens |
| /jobs/:slugId | src/pages/JobDetail.tsx | Job detail (slug-id URL), match section, apply/save/report, similar jobs |
| /jobs/:slugId/apply | src/pages/ApplyFlow.tsx | Apply / quick apply (JOB_SEEKER) |
| /companies | src/pages/CompaniesDirectory.tsx | Company directory with search/industry/type filters |
| /companies/:slugId | src/pages/CompanyDetail.tsx | Company profile, jobs, reviews, follow |
| /about, /contact, /terms, /privacy, /help | src/pages/StaticPage.tsx | Static pages (contact form, FAQ) |
| /register | src/pages/Register.tsx | Registration with role choice |
| /verify-email | src/pages/EmailVerification.tsx | Email verification |
| /verify-mobile | src/pages/MobileOtpVerification.tsx | 6-digit mobile OTP with resend timer |
| /login | src/pages/Login.tsx | Login with password |
| /login-otp | src/pages/LoginOtp.tsx | Login with OTP |
| /forgot-password | src/pages/ForgotPassword.tsx | Start password reset |
| /reset-password | src/pages/ResetPassword.tsx | Set new password |
| /not-authorized | src/pages/NotAuthorized.tsx | 403 page |
| /change-password | src/pages/ChangePassword.tsx | Change password (any logged-in role) |
| /messages | src/pages/MessagesInbox.tsx | Thread list + chat (seeker and recruiter) |
| /notifications | src/pages/NotificationsPage.tsx | Notifications list |
| /seeker/dashboard | src/pages/SeekerDashboard.tsx | Seeker home with completeness ring |
| /seeker/profile | src/pages/SeekerProfile.tsx | Editable profile, photo crop, resume manager |
| /seeker/recommended | src/pages/RecommendedJobs.tsx | Recommended jobs / based on recent searches |
| /seeker/saved | src/pages/SavedJobs.tsx | Saved jobs |
| /seeker/applied | src/pages/AppliedJobs.tsx | Applications with status tabs and trackers |
| /seeker/alerts | src/pages/JobAlerts.tsx | Job alerts CRUD |
| /seeker/following | src/pages/FollowingCompanies.tsx | Followed companies |
| /seeker/privacy | src/pages/PrivacySettings.tsx | Privacy settings |
| /seeker/notification-preferences | src/pages/NotificationPreferences.tsx | Notification preferences |
| /seeker/account | src/pages/AccountSettings.tsx | Account settings |
| /recruiter/dashboard | src/pages/RecruiterDashboard.tsx | Recruiter dashboard with funnel chart |
| /recruiter/company | src/pages/CompanyProfileEditor.tsx | Company profile editor |
| /recruiter/team | src/pages/TeamManagement.tsx | Team and invitations |
| /recruiter/post-job, /recruiter/post-job/:id | src/pages/PostJob.tsx | 6-step post/edit job form with autosave |
| /recruiter/jobs | src/pages/ManageJobs.tsx | Jobs table with status tabs and actions |
| /recruiter/jobs/:id/applicants | src/pages/Applicants.tsx | Applicants list/board toggle, filters, drawer, CSV export |
| /recruiter/candidates | src/pages/CandidateSearch.tsx | Candidate database search |
| /recruiter/saved | src/pages/SavedSearches.tsx | Saved searches and folders |
| /admin/dashboard | src/pages/AdminDashboard.tsx | Platform metrics and charts |
| /admin/companies | src/pages/AdminCompanies.tsx | Company approvals queue |
| /admin/moderation | src/pages/AdminModeration.tsx | Job queue, reported jobs, reviews |
| /admin/master | src/pages/AdminMasterData.tsx | Master data CRUD + CSV import |
| /admin/users | src/pages/AdminUsers.tsx | Users (block/unblock) and company credits/quota |
| /admin/analytics | src/pages/AdminAnalytics.tsx | Analytics with date range and CSV export |
| * | src/pages/NotFound.tsx | 404 |

Protected areas use `RequireAuth` (src/components/RequireAuth.tsx): logged-out users go to `/login?returnTo=<url>`, wrong role goes to `/not-authorized`.

## Navigation map
- Header -> Jobs, Companies, Dashboard (role home), Login, Register, For Employers / Post a Job
- Header notification bell -> Notifications (or the linked page); profile menu -> role links, Logout (confirm) -> Login
- Home -> JobSearch (hero search, category chips, location/skill tiles) ; Home -> CompanyDetail (company carousel) ; Home -> JobDetail (featured jobs)
- JobSearch -> JobDetail (card / full page link) ; JobSearch -> JobAlerts (Create job alert) ; JobSearch -> CompanyDetail
- JobDetail -> ApplyFlow (Apply) -> AppliedJobs (Track application) ; JobDetail -> Login (logged out apply/save, with returnTo)
- CompaniesDirectory -> CompanyDetail -> JobDetail
- Register -> EmailVerification -> MobileOtpVerification -> Login
- Login -> role dashboard or returnTo ; Login -> LoginOtp, ForgotPassword, Register
- ForgotPassword -> ResetPassword -> Login
- Seeker sidebar -> Dashboard, Profile, Recommended, Saved, Applied, Alerts, Following, Privacy, Notification settings, Account, Messages, Notifications, Change password
- Seeker Dashboard -> Profile (completion tasks), Recommended, Applied, JobDetail
- Applied jobs -> JobDetail (view job)
- Recruiter sidebar -> Dashboard, Post a job, Manage jobs, Candidate search, Searches & folders, Company profile, Team, Messages, Notifications, Change password
- RecruiterDashboard -> PostJob, CompanyProfileEditor, Applicants (performance row)
- ManageJobs -> PostJob/:id (edit), Applicants (count link), JobDetail
- Applicants -> CandidateDrawer (row / card) ; Applicants -> Messages (drawer Message button) ; Applicants list <-> board toggle
- CandidateSearch -> SavedSearches (saved searches re-run here) ; SavedSearches -> CandidateSearch (Run search)
- CompanyProfileEditor -> TeamManagement
- Admin sidebar -> Dashboard, Company approvals, Moderation, Master data, Users & credits, Analytics, Notifications, Change password
- AdminDashboard -> Users, Analytics, Moderation, Company approvals
- Any wrong-role URL -> NotAuthorized ; any unknown URL -> NotFound (Go Home / Go back)

## Shared components
- src/components/Header.tsx — top nav, theme toggle, notification bell dropdown, profile dropdown with logout confirmation
- src/components/Footer.tsx — about/contact/terms/privacy/help links and social links
- src/components/Layouts.tsx — PublicLayout (header+footer) and AreaLayout (role-based NavLink sidebar)
- src/components/navItems.ts — role-based nav definitions
- src/components/RequireAuth.tsx — route guard
- src/components/RouteError.tsx — error element with retry (500 page)
- src/components/ui.tsx — Skeleton, EmptyState, ErrorState, Modal, ConfirmDialog, Drawer, Tabs, Toggle, Stars, StatusBadge, Pagination, Breadcrumbs, PageHeader, CompanyLogo
- src/components/fields.tsx — TextField, SelectField, TextAreaField, PasswordStrength, SuggestInput (debounced typeahead), ChipInput, OtpInput, CheckboxField
- src/components/JobCard.tsx — JobCard and CompanyCard
- src/components/JobDetailView.tsx — job detail body (page and side panel)
- src/components/StatusTracker.tsx — horizontal tracker and timeline
- src/components/CandidateDrawer.tsx — candidate detail drawer
- src/components/KanbanBoard.tsx — drag-and-drop pipeline
- src/components/ResumeManager.tsx, PhotoCropper.tsx, RichTextEditor.tsx, AuthCard.tsx, SocialIcons.tsx

## Design tokens
Defined in tailwind.config.js (theme colors backed by CSS variables so dark mode swaps them):
- canvas, surface, ink, muted, line, soft (light/dark via CSS variables in src/index.css)
- primary (#2557d6) and primary-dark (#1a43aa)
- accent (#ff7555)
- success (#12a150), danger (#d92d20), warning (#f79009)

## Notes
- Data layer: every function in src/data/store.ts is gated by `USE_MOCK` (VITE_DEMO_MODE); mock data is seeded into localStorage so changes persist across reloads.
- Contact form, account deletion and revoke-all-sessions have no endpoint in the API contract and are tagged `MOCK:` in code.
- Tests: `npx vitest run` — 46 files, all passing (smoke tests per page + behaviour tests).
