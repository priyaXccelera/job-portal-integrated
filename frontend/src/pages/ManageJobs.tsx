import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { Copy, Pause, Pencil, Play, PlusCircle, RefreshCw, XCircle } from 'lucide-react'
import toast from 'react-hot-toast'
import { jobPath } from '../components/JobCard'
import { ConfirmDialog, EmptyState, ErrorState, PageHeader, Pagination, Skeleton, StatusBadge, Tabs } from '../components/ui'
import { duplicateJob, getRecruiterJobs, refreshJob, setRecruiterJobStatus } from '../data/store'
import { PAGE_SIZE, RECRUITER_JOB_TABS, STATUS_LABELS } from '../constants'
import { useAsync, useSeo } from '../hooks'
import type { Job, JobStatus } from '../types'
import { formatDate } from '../utils/format'

export function ManageJobs() {
  const navigate = useNavigate()
  const { data, loading, error, reload } = useAsync(() => getRecruiterJobs(), [])
  const [tab, setTab] = useState<JobStatus>('ACTIVE')
  const [sort, setSort] = useState('posted')
  const [page, setPage] = useState(1)
  const [closing, setClosing] = useState<Job | null>(null)
  useSeo('Manage jobs', 'Manage your job postings.')

  const all = data ?? []
  const filtered = all
    .filter((job) => job.status === tab)
    .sort((first, second) =>
      sort === 'applicants' ? second.applicantsCount - first.applicantsCount : sort === 'views' ? second.views - first.views : new Date(second.postedAt).getTime() - new Date(first.postedAt).getTime(),
    )

  const act = async (action: () => Promise<unknown>, message: string) => {
    try {
      await action()
      toast.success(message)
      reload()
    } catch {
      // API client shows the error toast
    }
  }

  return (
    <div>
      <PageHeader
        title="Manage jobs"
        actions={
          <button type="button" className="btn-accent" onClick={() => navigate('/recruiter/post-job')}>
            <PlusCircle className="h-4 w-4" />
            Post a job
          </button>
        }
      />
      <Tabs
        active={tab}
        onChange={(next) => {
          setTab(next)
          setPage(1)
        }}
        tabs={RECRUITER_JOB_TABS.map((status) => ({ value: status, label: STATUS_LABELS[status], count: all.filter((job) => job.status === status).length }))}
      />
      <div className="my-4 flex justify-end">
        <select className="input w-auto" aria-label="Sort jobs" value={sort} onChange={(event) => setSort(event.target.value)}>
          <option value="posted">Newest first</option>
          <option value="applicants">Most applicants</option>
          <option value="views">Most views</option>
        </select>
      </div>

      {loading && <Skeleton className="h-48 w-full" />}
      {error && <ErrorState message={error} onRetry={reload} />}
      {!loading && !error && filtered.length === 0 && (
        <EmptyState title={`No ${STATUS_LABELS[tab].toLowerCase()} jobs`} action={<Link to="/recruiter/post-job" className="btn-primary">Post a job</Link>} />
      )}
      {filtered.length > 0 && (
        <div className="card overflow-x-auto">
          <table className="w-full min-w-[56rem] text-left text-sm">
            <thead className="border-b border-line text-xs uppercase text-muted">
              <tr>
                <th className="p-3">Job</th>
                <th>Status</th>
                <th>Applicants</th>
                <th>Views</th>
                <th>Posted</th>
                <th>Expires</th>
                <th className="pr-3 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {filtered.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE).map((job) => (
                <tr key={job.id} className="hover:bg-soft/50">
                  <td className="p-3">
                    <Link to={jobPath(job)} className="font-semibold hover:text-primary">{job.title}</Link>
                    <p className="text-xs text-muted">{job.locations.join(', ')}</p>
                  </td>
                  <td><StatusBadge status={job.status} /></td>
                  <td>
                    <Link to={`/recruiter/jobs/${job.id}/applicants`} className="font-semibold text-primary hover:underline">{job.applicantsCount}</Link>
                  </td>
                  <td>{job.views}</td>
                  <td>{formatDate(job.postedAt)}</td>
                  <td>{formatDate(job.expiresAt)}</td>
                  <td className="pr-3">
                    <div className="flex justify-end gap-1">
                      <button type="button" aria-label={`Edit ${job.title}`} title="Edit" className="rounded p-2 hover:bg-soft" onClick={() => navigate(`/recruiter/post-job/${job.id}`)}>
                        <Pencil className="h-4 w-4" />
                      </button>
                      {job.status === 'ACTIVE' && (
                        <button type="button" aria-label={`Pause ${job.title}`} title="Pause" className="rounded p-2 hover:bg-soft" onClick={() => act(() => setRecruiterJobStatus(job.id, 'PAUSED'), 'Job paused')}>
                          <Pause className="h-4 w-4" />
                        </button>
                      )}
                      {job.status === 'PAUSED' && (
                        <button type="button" aria-label={`Resume ${job.title}`} title="Resume" className="rounded p-2 hover:bg-soft" onClick={() => act(() => setRecruiterJobStatus(job.id, 'ACTIVE'), 'Job resumed')}>
                          <Play className="h-4 w-4" />
                        </button>
                      )}
                      {(job.status === 'ACTIVE' || job.status === 'PAUSED') && (
                        <button type="button" aria-label={`Close ${job.title}`} title="Close" className="rounded p-2 text-danger hover:bg-soft" onClick={() => setClosing(job)}>
                          <XCircle className="h-4 w-4" />
                        </button>
                      )}
                      <button type="button" aria-label={`Duplicate ${job.title}`} title="Duplicate" className="rounded p-2 hover:bg-soft" onClick={() => act(() => duplicateJob(job.id), 'Job duplicated as a draft')}>
                        <Copy className="h-4 w-4" />
                      </button>
                      {['ACTIVE', 'CLOSED', 'EXPIRED'].includes(job.status) && (
                        <button type="button" aria-label={`Refresh ${job.title}`} title="Refresh / repost" className="rounded p-2 hover:bg-soft" onClick={() => act(() => refreshJob(job.id), 'Job refreshed')}>
                          <RefreshCw className="h-4 w-4" />
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <Pagination page={page} pageSize={PAGE_SIZE} total={filtered.length} onChange={setPage} />

      <ConfirmDialog
        open={Boolean(closing)}
        danger
        title="Close this job?"
        message={`"${closing?.title ?? ''}" will stop accepting applications.`}
        confirmLabel="Close job"
        onCancel={() => setClosing(null)}
        onConfirm={() => {
          if (closing) act(() => setRecruiterJobStatus(closing.id, 'CLOSED'), 'Job closed')
          setClosing(null)
        }}
      />
    </div>
  )
}
