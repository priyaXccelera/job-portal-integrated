import { Link } from 'react-router-dom'
import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { Briefcase, Building2, ShieldAlert, Users } from 'lucide-react'
import { ErrorState, PageHeader, Skeleton } from '../components/ui'
import { getAdminCompanies, getAnalytics, getJobReports, getUserList } from '../data/store'
import { useAsync, useSeo } from '../hooks'
import { formatDate, formatIndianNumber } from '../utils/format'

export function AdminDashboard() {
  const analytics = useAsync(() => getAnalytics('', ''), [])
  const users = useAsync(() => getUserList(), [])
  const pending = useAsync(() => getAdminCompanies('PENDING'), [])
  const reports = useAsync(() => getJobReports(), [])
  useSeo('Admin dashboard', 'Platform metrics.')

  if (analytics.error) return <ErrorState message={analytics.error} onRetry={analytics.reload} />
  const data = analytics.data
  const openReports = reports.data?.filter((report) => !report.resolved).length ?? 0

  const cards = [
    { label: 'Registered users', value: users.data?.length, icon: Users, to: '/admin/users' },
    { label: 'Registrations (period)', value: data?.totals.registrations, icon: Users, to: '/admin/analytics' },
    { label: 'Jobs posted (period)', value: data?.totals.jobs, icon: Briefcase, to: '/admin/moderation' },
    { label: 'Companies pending', value: pending.data?.length, icon: Building2, to: '/admin/companies' },
    { label: 'Open job reports', value: openReports, icon: ShieldAlert, to: '/admin/moderation' },
  ]

  return (
    <div className="space-y-6">
      <PageHeader title="Admin dashboard" subtitle="Platform health at a glance." />
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-5">
        {cards.map((card) => (
          <Link key={card.label} to={card.to} className="card p-4 hover:border-primary">
            <card.icon className="h-5 w-5 text-primary" />
            <p className="mt-2 text-2xl font-extrabold">{card.value === undefined ? '—' : formatIndianNumber(card.value)}</p>
            <p className="text-xs text-muted">{card.label}</p>
          </Link>
        ))}
      </div>

      <section className="card p-5" aria-label="Growth chart">
        <h2 className="mb-3 font-bold">Registrations, jobs and applications over time</h2>
        {analytics.loading ? (
          <Skeleton className="h-72 w-full" />
        ) : (
          <div className="h-72">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={data?.series.map((point) => ({ ...point, date: formatDate(point.date) }))}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="date" tick={{ fontSize: 11 }} />
                <YAxis />
                <Tooltip />
                <Legend />
                <Line type="monotone" dataKey="registrations" stroke="#2557d6" strokeWidth={2} dot={false} />
                <Line type="monotone" dataKey="jobs" stroke="#ff7555" strokeWidth={2} dot={false} />
                <Line type="monotone" dataKey="applications" stroke="#12a150" strokeWidth={2} dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        )}
      </section>

      <div className="grid gap-6 lg:grid-cols-2">
        <section className="card p-5" aria-label="Top keywords">
          <h2 className="mb-3 font-bold">Top search keywords</h2>
          <ol className="space-y-2 text-sm">
            {data?.topKeywords.map((entry, index) => (
              <li key={entry.keyword} className="flex justify-between">
                <span>{index + 1}. {entry.keyword}</span>
                <span className="text-muted">{formatIndianNumber(entry.count)}</span>
              </li>
            ))}
          </ol>
        </section>
        <section className="card p-5" aria-label="Top companies">
          <h2 className="mb-3 font-bold">Top companies</h2>
          <ol className="space-y-2 text-sm">
            {data?.topCompanies.map((entry, index) => (
              <li key={entry.name} className="flex justify-between">
                <span>{index + 1}. {entry.name}</span>
                <span className="text-muted">{entry.applications} applications · {entry.jobs} jobs</span>
              </li>
            ))}
          </ol>
        </section>
      </div>
    </div>
  )
}
