import { createBrowserRouter } from 'react-router-dom'
import App from '../App'
import { AreaLayout, PublicLayout } from '../components/Layouts'
import { RequireAuth } from '../components/RequireAuth'
import { RouteError } from '../components/RouteError'
import { AccountSettings } from '../pages/AccountSettings'
import { AdminAnalytics } from '../pages/AdminAnalytics'
import { AdminCompanies } from '../pages/AdminCompanies'
import { AdminDashboard } from '../pages/AdminDashboard'
import { AdminMasterData } from '../pages/AdminMasterData'
import { AdminModeration } from '../pages/AdminModeration'
import { AdminUsers } from '../pages/AdminUsers'
import { AppliedJobs } from '../pages/AppliedJobs'
import { ApplyFlow } from '../pages/ApplyFlow'
import { Applicants } from '../pages/Applicants'
import { CandidateSearch } from '../pages/CandidateSearch'
import { ChangePassword } from '../pages/ChangePassword'
import { CompaniesDirectory } from '../pages/CompaniesDirectory'
import { CompanyDetail } from '../pages/CompanyDetail'
import { CompanyProfileEditor } from '../pages/CompanyProfileEditor'
import { EmailVerification } from '../pages/EmailVerification'
import { FollowingCompanies } from '../pages/FollowingCompanies'
import { ForgotPassword } from '../pages/ForgotPassword'
import { Home } from '../pages/Home'
import { JobAlerts } from '../pages/JobAlerts'
import { JobDetail } from '../pages/JobDetail'
import { JobSearch } from '../pages/JobSearch'
import { Login } from '../pages/Login'
import { LoginOtp } from '../pages/LoginOtp'
import { ManageJobs } from '../pages/ManageJobs'
import { MessagesInbox } from '../pages/MessagesInbox'
import { MobileOtpVerification } from '../pages/MobileOtpVerification'
import { NotAuthorized } from '../pages/NotAuthorized'
import { NotFound } from '../pages/NotFound'
import { NotificationPreferences } from '../pages/NotificationPreferences'
import { NotificationsPage } from '../pages/NotificationsPage'
import { PostJob } from '../pages/PostJob'
import { PrivacySettings } from '../pages/PrivacySettings'
import { RecommendedJobs } from '../pages/RecommendedJobs'
import { RecruiterDashboard } from '../pages/RecruiterDashboard'
import { Register } from '../pages/Register'
import { ResetPassword } from '../pages/ResetPassword'
import { SavedJobs } from '../pages/SavedJobs'
import { SavedSearches } from '../pages/SavedSearches'
import { SeekerDashboard } from '../pages/SeekerDashboard'
import { SeekerProfile } from '../pages/SeekerProfile'
import { StaticPage } from '../pages/StaticPage'
import { TeamManagement } from '../pages/TeamManagement'

export const routes = [
  {
    path: '/',
    element: <App />,
    errorElement: <RouteError />,
    children: [
      {
        element: <PublicLayout />,
        children: [
          // "/" is the main screen (public landing page), so no redirect is needed.
          { index: true, element: <Home /> },
          { path: 'jobs', element: <JobSearch /> },
          { path: 'jobs/:slugId', element: <JobDetail /> },
          { path: 'companies', element: <CompaniesDirectory /> },
          { path: 'companies/:slugId', element: <CompanyDetail /> },
          { path: 'about', element: <StaticPage page="about" /> },
          { path: 'contact', element: <StaticPage page="contact" /> },
          { path: 'terms', element: <StaticPage page="terms" /> },
          { path: 'privacy', element: <StaticPage page="privacy" /> },
          { path: 'help', element: <StaticPage page="help" /> },
          { path: 'register', element: <Register /> },
          { path: 'verify-email', element: <EmailVerification /> },
          { path: 'verify-mobile', element: <MobileOtpVerification /> },
          { path: 'login', element: <Login /> },
          { path: 'login-otp', element: <LoginOtp /> },
          { path: 'forgot-password', element: <ForgotPassword /> },
          { path: 'reset-password', element: <ResetPassword /> },
          { path: 'not-authorized', element: <NotAuthorized /> },
          {
            element: <RequireAuth roles={['JOB_SEEKER']} />,
            children: [{ path: 'jobs/:slugId/apply', element: <ApplyFlow /> }],
          },
        ],
      },
      {
        element: <RequireAuth roles={['JOB_SEEKER']} />,
        children: [
          {
            element: <AreaLayout />,
            children: [
              { path: 'seeker/dashboard', element: <SeekerDashboard /> },
              { path: 'seeker/profile', element: <SeekerProfile /> },
              { path: 'seeker/recommended', element: <RecommendedJobs /> },
              { path: 'seeker/saved', element: <SavedJobs /> },
              { path: 'seeker/applied', element: <AppliedJobs /> },
              { path: 'seeker/alerts', element: <JobAlerts /> },
              { path: 'seeker/following', element: <FollowingCompanies /> },
              { path: 'seeker/privacy', element: <PrivacySettings /> },
              { path: 'seeker/notification-preferences', element: <NotificationPreferences /> },
              { path: 'seeker/account', element: <AccountSettings /> },
            ],
          },
        ],
      },
      {
        element: <RequireAuth roles={['RECRUITER']} />,
        children: [
          {
            element: <AreaLayout />,
            children: [
              { path: 'recruiter/dashboard', element: <RecruiterDashboard /> },
              { path: 'recruiter/company', element: <CompanyProfileEditor /> },
              { path: 'recruiter/team', element: <TeamManagement /> },
              { path: 'recruiter/post-job', element: <PostJob /> },
              { path: 'recruiter/post-job/:id', element: <PostJob /> },
              { path: 'recruiter/jobs', element: <ManageJobs /> },
              { path: 'recruiter/jobs/:id/applicants', element: <Applicants /> },
              { path: 'recruiter/candidates', element: <CandidateSearch /> },
              { path: 'recruiter/saved', element: <SavedSearches /> },
            ],
          },
        ],
      },
      {
        element: <RequireAuth roles={['ADMIN']} />,
        children: [
          {
            element: <AreaLayout />,
            children: [
              { path: 'admin/dashboard', element: <AdminDashboard /> },
              { path: 'admin/companies', element: <AdminCompanies /> },
              { path: 'admin/moderation', element: <AdminModeration /> },
              { path: 'admin/master', element: <AdminMasterData /> },
              { path: 'admin/users', element: <AdminUsers /> },
              { path: 'admin/analytics', element: <AdminAnalytics /> },
            ],
          },
        ],
      },
      {
        element: <RequireAuth />,
        children: [
          {
            element: <AreaLayout />,
            children: [
              { path: 'messages', element: <MessagesInbox /> },
              { path: 'notifications', element: <NotificationsPage /> },
              { path: 'change-password', element: <ChangePassword /> },
            ],
          },
        ],
      },
      { path: '*', element: <NotFound /> },
    ],
  },
]

export const router = createBrowserRouter(routes)
