import { Link, useNavigate } from 'react-router-dom'
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { Briefcase, Coins, Hourglass, PlusCircle, UserPlus } from 'lucide-react'
import { ErrorState, PageHeader, Skeleton } from '../components/ui'
import { getRecruiterDashboard } from '../data/store'
import { useAsync, useSeo } from '../hooks'
import { formatDate } from '../utils/format'

export function RecruiterDashboard() {
  const navigate = useNavigate()
  const { data, loading, error, reload } = useAsync(() => getRecruiterDashboard(), [])
  useSeo('Recruiter dashboard', 'Hiring overview.')

  if (loading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-24 w-full" />
        <Skeleton className="h-64 w-full" />
      </div>
    )
  }
  if (error || !data) return <ErrorState message={error || 'No data'} onRetry={reload} />

  const stats = [
    { label: 'Active jobs', value: data.activeJobs, icon: Briefcase },
    { label: 'New applicants today', value: data.newApplicantsToday, icon: UserPlus },
    { label: 'Credits balance', value: data.credits, icon: Coins },
  ]

  return (
    <div className="space-y-6">
      <PageHeader
        title="Recruiter dashboard"
        actions={
          <button type="button" className="btn-accent" onClick={() => navigate('/recruiter/post-job')}>
            <PlusCircle className="h-4 w-4" />
            Post a job
          </button>
        }
      />
      {data.companyStatus !== 'APPROVED' && (
        <div role="status" className="flex items-start gap-3 rounded-lg border border-warning/50 bg-warning/10 p-4 text-sm">
          <Hourglass className="mt-0.5 h-5 w-5 text-warning" />
          <p>
            Your company is <strong>awaiting admin approval</strong>. You can save drafts, but publishing jobs is restricted until approval.{' '}
            <Link to="/recruiter/company" className="font-semibold text-primary">Complete your company profile</Link>
          </p>
        </div>
      )}

      <div className="grid gap-4 sm:grid-cols-3">
        {stats.map((stat) => (
          <div key={stat.label} className="card flex items-center gap-4 p-5">
            <span className="rounded-full bg-soft p-3 text-primary"><stat.icon className="h-6 w-6" /></span>
            <div>
              <p className="text-3xl font-extrabold">{stat.value}</p>
              <p className="text-sm text-muted">{stat.label}</p>
            </div>
          </div>
        ))}
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <section className="card p-5" aria-label="Hiring funnel">
          <h2 className="mb-3 font-bold">Hiring funnel</h2>
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={data.funnel}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="stage" tick={{ fontSize: 11 }} />
                <YAxis allowDecimals={false} />
                <Tooltip />
                <Bar dataKey="count" fill="#2557d6" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </section>

        <section className="card p-5" aria-label="Upcoming interviews">
          <h2 className="mb-3 font-bold">Upcoming interviews</h2>
          <ul className="divide-y divide-line">
            {data.upcomingInterviews.map((interview) => (
              <li key={interview.applicationId} className="py-3 text-sm">
                <p className="font-semibold">{interview.candidateName}</p>
                <p className="text-muted">{interview.jobTitle} · {formatDate(interview.dateTime)} · {interview.mode}</p>
              </li>
            ))}
            {data.upcomingInterviews.length === 0 && <li className="py-6 text-center text-sm text-muted">No interviews scheduled</li>}
          </ul>
        </section>
      </div>

      <section className="card overflow-x-auto p-5" aria-label="Job performance">
        <h2 className="mb-3 font-bold">Job performance</h2>
        <table className="w-full min-w-[32rem] text-left text-sm">
          <thead className="text-xs uppercase text-muted">
            <tr>
              <th className="py-2">Job</th>
              <th>Views</th>
              <th>Applications</th>
              <th>Conversion</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-line">
            {data.performance.map((row) => (
              <tr key={row.jobId} className="cursor-pointer hover:bg-soft" onClick={() => navigate(`/recruiter/jobs/${row.jobId}/applicants`)}>
                <td className="py-3 font-semibold">{row.title}</td>
                <td>{row.views}</td>
                <td>{row.applications}</td>
                <td>{row.views ? `${Math.round((row.applications / row.views) * 100)}%` : '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {data.performance.length === 0 && <p className="py-6 text-center text-sm text-muted">No jobs posted yet.</p>}
      </section>
    </div>
  )
}
