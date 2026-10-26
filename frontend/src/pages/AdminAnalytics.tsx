import { useState } from 'react'
import { Area, AreaChart, Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { Download } from 'lucide-react'
import { TextField } from '../components/fields'
import { ErrorState, PageHeader, Skeleton } from '../components/ui'
import { exportAnalyticsCsv, getAnalytics } from '../data/store'
import { useAsync, useSeo } from '../hooks'
import { formatDate, toApiDate } from '../utils/format'

export function AdminAnalytics() {
  const today = new Date()
  const [from, setFrom] = useState(toApiDate(new Date(today.getTime() - 84 * 86400000)))
  const [to, setTo] = useState(toApiDate(today))
  const rangeError = from && to && from > to ? 'Start date must be before the end date' : ''
  const { data, loading, error, reload } = useAsync(() => (rangeError ? Promise.resolve(undefined) : getAnalytics(from, to)), [from, to])
  useSeo('Analytics', 'Platform analytics.')

  return (
    <div className="space-y-6">
      <PageHeader
        title="Analytics"
        actions={
          <button type="button" className="btn-outline" disabled={Boolean(rangeError)} onClick={() => exportAnalyticsCsv(from, to)}>
            <Download className="h-4 w-4" />
            Export CSV
          </button>
        }
      />
      <div className="card flex flex-wrap gap-4 p-4">
        <TextField label="From" type="date" value={from} onChange={(event) => setFrom(event.target.value)} />
        <TextField label="To" type="date" value={to} error={rangeError} onChange={(event) => setTo(event.target.value)} />
      </div>
      {error && <ErrorState message={error} onRetry={reload} />}
      {loading && <Skeleton className="h-72 w-full" />}
      {data && (
        <>
          <div className="grid gap-4 sm:grid-cols-3">
            {[
              ['Registrations', data.totals.registrations],
              ['Jobs posted', data.totals.jobs],
              ['Applications', data.totals.applications],
            ].map(([label, value]) => (
              <div key={label} className="card p-5">
                <p className="text-sm text-muted">{label}</p>
                <p className="text-3xl font-extrabold">{value}</p>
              </div>
            ))}
          </div>
          <section className="card p-5" aria-label="Applications over time">
            <h2 className="mb-3 font-bold">Applications over time</h2>
            <div className="h-64">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={data.series.map((point) => ({ ...point, date: formatDate(point.date) }))}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} />
                  <XAxis dataKey="date" tick={{ fontSize: 11 }} />
                  <YAxis />
                  <Tooltip />
                  <Area type="monotone" dataKey="applications" stroke="#2557d6" fill="#2557d633" />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          </section>
          <section className="card p-5" aria-label="Registrations and jobs">
            <h2 className="mb-3 font-bold">Registrations &amp; jobs posted</h2>
            <div className="h-64">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={data.series.map((point) => ({ ...point, date: formatDate(point.date) }))}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} />
                  <XAxis dataKey="date" tick={{ fontSize: 11 }} />
                  <YAxis />
                  <Tooltip />
                  <Legend />
                  <Bar dataKey="registrations" fill="#2557d6" />
                  <Bar dataKey="jobs" fill="#ff7555" />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </section>
        </>
      )}
    </div>
  )
}
