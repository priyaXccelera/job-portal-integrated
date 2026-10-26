import { Link, useNavigate } from 'react-router-dom'
import { CheckCircle2, Circle, Eye } from 'lucide-react'
import { useAuth } from '../auth/auth'
import { jobPath } from '../components/JobCard'
import { CompanyLogo, ErrorState, PageHeader, Skeleton, StatusBadge } from '../components/ui'
import { getAlerts, getCompleteness, getMyApplications, getProfile, getProfileViews, getRecommendedJobs } from '../data/store'
import { useAsync, useSeo } from '../hooks'
import { formatDate, formatSalary, timeAgo } from '../utils/format'

const TASK_LINKS: Record<string, string> = {
  resume: '/seeker/profile',
  skills: '/seeker/profile',
  education: '/seeker/profile',
  employment: '/seeker/profile',
  headline: '/seeker/profile',
  photo: '/seeker/profile',
}

function CompletenessRing({ percentage, photoUrl, name }: { percentage: number; photoUrl: string; name: string }) {
  const radius = 52
  const circumference = 2 * Math.PI * radius
  return (
    <div className="relative h-32 w-32 shrink-0">
      <svg viewBox="0 0 120 120" className="h-full w-full -rotate-90" role="img" aria-label={`Profile ${percentage}% complete`}>
        <circle cx="60" cy="60" r={radius} className="fill-none stroke-line" strokeWidth="8" />
        <circle
          cx="60"
          cy="60"
          r={radius}
          className="fill-none stroke-success"
          strokeWidth="8"
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={circumference * (1 - percentage / 100)}
        />
      </svg>
      {photoUrl ? (
        <img src={photoUrl} alt="" className="absolute inset-3 h-[calc(100%-1.5rem)] w-[calc(100%-1.5rem)] rounded-full object-cover" />
      ) : (
        <span className="absolute inset-3 flex items-center justify-center rounded-full bg-soft text-3xl font-bold text-primary">{name.slice(0, 1)}</span>
      )}
      <span className="absolute -bottom-1 left-1/2 -translate-x-1/2 rounded-full bg-success px-2 py-0.5 text-xs font-bold text-white">{percentage}%</span>
    </div>
  )
}

export function SeekerDashboard() {
  const navigate = useNavigate()
  const { user } = useAuth()
  const profile = useAsync(() => getProfile(), [])
  const completeness = useAsync(() => getCompleteness(), [])
  const recommended = useAsync(() => getRecommendedJobs(), [])
  const applications = useAsync(() => getMyApplications(), [])
  const views = useAsync(() => getProfileViews(), [])
  const alerts = useAsync(() => getAlerts(), [])
  useSeo('Dashboard', 'Your personalised job seeker dashboard.')

  if (profile.error) return <ErrorState message={profile.error} onRetry={profile.reload} />

  return (
    <div className="space-y-6">
      <PageHeader title={`Welcome back, ${user?.name.split(' ')[0] ?? ''}`} subtitle="Here's what's happening with your job search." />

      <section className="card flex flex-wrap items-center gap-6 p-5">
        {completeness.loading || profile.loading ? (
          <Skeleton className="h-32 w-full" />
        ) : (
          <>
            <CompletenessRing percentage={completeness.data?.percentage ?? 0} photoUrl={profile.data?.photoUrl ?? ''} name={user?.name ?? ''} />
            <div className="min-w-0 flex-1">
              <h2 className="font-bold">Complete your profile</h2>
              <ul className="mt-2 grid gap-1 sm:grid-cols-2">
                {completeness.data?.tasks.map((task) => (
                  <li key={task.key}>
                    <Link to={TASK_LINKS[task.key]} className={`flex items-center gap-2 rounded px-2 py-1 text-sm hover:bg-soft ${task.done ? 'text-muted line-through' : ''}`}>
                      {task.done ? <CheckCircle2 className="h-4 w-4 text-success" /> : <Circle className="h-4 w-4 text-muted" />}
                      {task.label}
                    </Link>
                  </li>
                ))}
              </ul>
            </div>
          </>
        )}
      </section>

      <div className="grid gap-4 sm:grid-cols-3">
        <div className="card p-5">
          <p className="flex items-center gap-2 text-sm text-muted"><Eye className="h-4 w-4" /> Profile views</p>
          <p className="mt-1 text-3xl font-extrabold">{views.data?.views ?? '—'}</p>
        </div>
        <Link to="/seeker/alerts" className="card p-5 hover:border-primary">
          <p className="text-sm text-muted">Job alerts</p>
          <p className="mt-1 text-3xl font-extrabold">{alerts.data?.filter((alert) => alert.active).length ?? '—'}</p>
          <p className="text-xs text-muted">{alerts.data?.length ?? 0} total · manage alerts</p>
        </Link>
        <Link to="/seeker/applied" className="card p-5 hover:border-primary">
          <p className="text-sm text-muted">Applications</p>
          <p className="mt-1 text-3xl font-extrabold">{applications.data?.length ?? '—'}</p>
          <p className="text-xs text-muted">track your status</p>
        </Link>
      </div>

      <section>
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-lg font-bold">Recommended jobs</h2>
          <Link to="/seeker/recommended" className="text-sm font-semibold text-primary">View all</Link>
        </div>
        <div className="grid gap-3 md:grid-cols-3">
          {recommended.loading && Array.from({ length: 3 }, (_, index) => <Skeleton key={index} className="h-36 w-full" />)}
          {recommended.data?.slice(0, 3).map((job) => (
            <button key={job.id} type="button" className="card p-4 text-left hover:border-primary" onClick={() => navigate(jobPath(job))}>
              <CompanyLogo src={job.company.logoUrl} name={job.company.name} size="h-10 w-10" />
              <p className="mt-2 font-semibold">{job.title}</p>
              <p className="text-sm text-muted">{job.company.name}</p>
              <p className="mt-1 text-xs text-muted">{formatSalary(job.salaryMin, job.salaryMax, job.salaryDisclosed)}</p>
              {job.matchScore && <p className="mt-1 text-xs font-semibold text-success">{job.matchScore.percentage}% match</p>}
            </button>
          ))}
        </div>
      </section>

      <section>
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-lg font-bold">Recent applications</h2>
          <Link to="/seeker/applied" className="text-sm font-semibold text-primary">View all</Link>
        </div>
        <div className="card divide-y divide-line">
          {applications.loading && <Skeleton className="m-4 h-12" />}
          {applications.data?.slice(0, 4).map((application) => (
            <div key={application.id} className="flex items-center gap-3 p-4">
              <CompanyLogo src={application.company.logoUrl} name={application.company.name} size="h-10 w-10" />
              <div className="min-w-0 flex-1">
                <p className="truncate font-semibold">{application.jobTitle}</p>
                <p className="text-xs text-muted">{application.company.name} · Applied {formatDate(application.appliedAt)}</p>
              </div>
              <StatusBadge status={application.status} />
            </div>
          ))}
          {applications.data?.length === 0 && <p className="p-4 text-sm text-muted">You haven't applied to any jobs yet.</p>}
        </div>
      </section>

      <section>
        <h2 className="mb-3 text-lg font-bold">Recruiters who viewed your profile</h2>
        <div className="card divide-y divide-line">
          {views.data?.viewers.map((viewer) => (
            <div key={viewer.id} className="flex items-center justify-between p-4 text-sm">
              <span>
                <span className="font-semibold">{viewer.name}</span> <span className="text-muted">· {viewer.company}</span>
              </span>
              <span className="text-xs text-muted">{timeAgo(viewer.at)}</span>
            </div>
          ))}
          {views.data?.viewers.length === 0 && <p className="p-4 text-sm text-muted">No profile views yet.</p>}
        </div>
      </section>
    </div>
  )
}
