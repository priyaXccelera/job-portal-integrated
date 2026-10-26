import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Calendar, ExternalLink, Link2 } from 'lucide-react'
import toast from 'react-hot-toast'
import { StatusTracker, Timeline } from '../components/StatusTracker'
import { TextAreaField } from '../components/fields'
import { ConfirmDialog, CompanyLogo, EmptyState, ErrorState, ListSkeleton, Modal, PageHeader, Pagination, StatusBadge, Tabs } from '../components/ui'
import { getMyApplications, respondToInterview, withdrawApplication } from '../data/store'
import { ALL_APPLICATION_STATUSES, PAGE_SIZE, STATUS_LABELS } from '../constants'
import { useAsync, useSeo } from '../hooks'
import { jobPath } from '../components/JobCard'
import type { Application, ApplicationStatus } from '../types'
import { formatDate } from '../utils/format'

type Tab = 'ALL' | ApplicationStatus

export function AppliedJobs() {
  const { data, loading, error, reload } = useAsync(() => getMyApplications(), [])
  const [tab, setTab] = useState<Tab>('ALL')
  const [page, setPage] = useState(1)
  const [withdrawing, setWithdrawing] = useState<Application | null>(null)
  const [rescheduling, setRescheduling] = useState<Application | null>(null)
  const [note, setNote] = useState('')
  const [noteError, setNoteError] = useState('')
  useSeo('Applied jobs', 'Track the status of your job applications.')

  const all = data ?? []
  const filtered = tab === 'ALL' ? all : all.filter((application) => application.status === tab)
  const tabs = [
    { value: 'ALL' as Tab, label: 'All', count: all.length },
    ...ALL_APPLICATION_STATUSES.map((status) => ({
      value: status as Tab,
      label: STATUS_LABELS[status],
      count: all.filter((application) => application.status === status).length,
    })),
  ]

  const confirmInterview = async (application: Application) => {
    await respondToInterview(application.id, 'CONFIRM', '')
    toast.success('Interview confirmed')
    reload()
  }

  const requestReschedule = async () => {
    if (!note.trim()) {
      setNoteError('Please tell the recruiter your preferred time')
      return
    }
    if (rescheduling) await respondToInterview(rescheduling.id, 'RESCHEDULE', note.trim())
    toast.success('Reschedule request sent')
    setRescheduling(null)
    setNote('')
    setNoteError('')
    reload()
  }

  return (
    <div>
      <PageHeader title="Applied jobs" subtitle="Track every application from one place." />
      <Tabs
        tabs={tabs}
        active={tab}
        onChange={(next) => {
          setTab(next)
          setPage(1)
        }}
      />
      <div className="mt-4 space-y-4">
        {loading && <ListSkeleton count={3} />}
        {error && <ErrorState message={error} onRetry={reload} />}
        {!loading && !error && filtered.length === 0 && (
          <EmptyState title="No applications here" message="Applications you submit will show up with their live status." action={<Link to="/jobs" className="btn-primary">Find jobs</Link>} />
        )}
        {filtered.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE).map((application) => (
          <article key={application.id} className="card space-y-4 p-5">
            <div className="flex items-start gap-3">
              <CompanyLogo src={application.company.logoUrl} name={application.company.name} />
              <div className="min-w-0 flex-1">
                <Link to={jobPath({ id: application.jobId, title: application.jobTitle })} className="font-bold hover:text-primary">
                  {application.jobTitle}
                </Link>
                <p className="text-sm text-muted">
                  {application.company.name} · Applied on {formatDate(application.appliedAt)}
                </p>
              </div>
              <StatusBadge status={application.status} />
            </div>

            <StatusTracker status={application.status} history={application.history} />

            <details className="text-sm">
              <summary className="cursor-pointer font-semibold text-primary">View timeline</summary>
              <div className="mt-3">
                <Timeline history={application.history} />
              </div>
            </details>

            {application.interview && application.status === 'INTERVIEW_SCHEDULED' && (
              <div className="rounded-lg bg-soft p-4 text-sm">
                <p className="mb-1 font-bold">Interview scheduled</p>
                <p className="flex items-center gap-2"><Calendar className="h-4 w-4" />{formatDate(application.interview.dateTime)} · {application.interview.mode}</p>
                <p className="flex items-center gap-2 text-muted"><Link2 className="h-4 w-4" />{application.interview.linkOrAddress}</p>
                {application.interview.response ? (
                  <p className="mt-2 font-semibold text-success">
                    {application.interview.response === 'CONFIRM' ? 'You confirmed this interview' : 'Reschedule requested'}
                  </p>
                ) : (
                  <div className="mt-3 flex gap-2">
                    <button type="button" className="btn-primary" onClick={() => confirmInterview(application)}>Confirm</button>
                    <button type="button" className="btn-outline" onClick={() => setRescheduling(application)}>Request reschedule</button>
                  </div>
                )}
              </div>
            )}

            <div className="flex gap-2">
              <Link to={jobPath({ id: application.jobId, title: application.jobTitle })} className="btn-outline">
                <ExternalLink className="h-4 w-4" />
                View job
              </Link>
              {!['WITHDRAWN', 'REJECTED', 'HIRED'].includes(application.status) && (
                <button type="button" className="btn-outline text-danger" onClick={() => setWithdrawing(application)}>
                  Withdraw
                </button>
              )}
            </div>
          </article>
        ))}
      </div>
      <Pagination page={page} pageSize={PAGE_SIZE} total={filtered.length} onChange={setPage} />

      <ConfirmDialog
        open={Boolean(withdrawing)}
        danger
        title="Withdraw application?"
        message={`Your application for ${withdrawing?.jobTitle ?? 'this job'} will be withdrawn.`}
        confirmLabel="Withdraw"
        onCancel={() => setWithdrawing(null)}
        onConfirm={async () => {
          if (withdrawing) await withdrawApplication(withdrawing.id)
          setWithdrawing(null)
          toast.success('Application withdrawn')
          reload()
        }}
      />

      <Modal open={Boolean(rescheduling)} title="Request reschedule" onClose={() => setRescheduling(null)}>
        <TextAreaField label="Message to recruiter" required value={note} error={noteError} onChange={(event) => setNote(event.target.value)} />
        <div className="mt-4 flex justify-end gap-3">
          <button type="button" className="btn-outline" onClick={() => setRescheduling(null)}>Cancel</button>
          <button type="button" className="btn-primary" onClick={requestReschedule}>Send request</button>
        </div>
      </Modal>
    </div>
  )
}
