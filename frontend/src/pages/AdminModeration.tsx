import { useState } from 'react'
import { Link } from 'react-router-dom'
import toast from 'react-hot-toast'
import { jobPath } from '../components/JobCard'
import { TextAreaField } from '../components/fields'
import { ConfirmDialog, EmptyState, ErrorState, Modal, PageHeader, Skeleton, Stars, Tabs } from '../components/ui'
import { deleteReview, getAllReviews, getJobReports, getModerationJobs, resolveReport, setJobModeration } from '../data/store'
import { useAsync, useSeo } from '../hooks'
import type { Job, JobReport } from '../types'
import { formatDate } from '../utils/format'
import { validateMinLength } from '../validation'

type Tab = 'jobs' | 'reports' | 'reviews'

export function AdminModeration() {
  const [tab, setTab] = useState<Tab>('jobs')
  const jobs = useAsync(() => getModerationJobs(), [])
  const reports = useAsync(() => getJobReports(), [])
  const reviews = useAsync(() => getAllReviews(), [])
  const [rejecting, setRejecting] = useState<Job | null>(null)
  const [reason, setReason] = useState('')
  const [attempted, setAttempted] = useState(false)
  const [takeDown, setTakeDown] = useState<JobReport | null>(null)
  const [deleteId, setDeleteId] = useState<string | null>(null)
  useSeo('Moderation', 'Moderate jobs, reports and reviews.')
  const reasonError = validateMinLength(reason, 5, 'Reason')
  const openReports = reports.data?.filter((report) => !report.resolved) ?? []

  return (
    <div>
      <PageHeader title="Moderation" subtitle="Keep the platform safe and trustworthy." />
      <Tabs
        active={tab}
        onChange={(value) => setTab(value as typeof tab)}
        tabs={[
          { value: 'jobs', label: 'Job queue', count: jobs.data?.length },
          { value: 'reports', label: 'Reported jobs', count: openReports.length },
          { value: 'reviews', label: 'Reviews', count: reviews.data?.length },
        ]}
      />
      <div className="mt-4 space-y-3">
        {tab === 'jobs' && (
          <>
            {jobs.loading && <Skeleton className="h-20 w-full" />}
            {jobs.error && <ErrorState message={jobs.error} onRetry={jobs.reload} />}
            {jobs.data?.length === 0 && <EmptyState title="No jobs awaiting review" />}
            {jobs.data?.map((job) => (
              <article key={job.id} className="card flex flex-wrap items-center gap-3 p-4">
                <div className="min-w-0 flex-1">
                  <Link to={jobPath(job)} className="font-bold hover:text-primary">{job.title}</Link>
                  <p className="text-sm text-muted">{job.company.name} · {job.locations.join(', ')} · posted {formatDate(job.postedAt)}</p>
                </div>
                <Link to={jobPath(job)} className="btn-outline">View</Link>
                <button
                  type="button"
                  className="btn-primary"
                  onClick={async () => {
                    await setJobModeration(job.id, 'ACTIVE')
                    toast.success('Job approved')
                    jobs.reload()
                  }}
                >
                  Approve
                </button>
                <button type="button" className="btn-danger" onClick={() => setRejecting(job)}>Reject</button>
              </article>
            ))}
          </>
        )}

        {tab === 'reports' && (
          <>
            {reports.loading && <Skeleton className="h-20 w-full" />}
            {openReports.length === 0 && !reports.loading && <EmptyState title="No open reports" />}
            {openReports.map((report) => (
              <article key={report.id} className="card flex flex-wrap items-center gap-3 p-4">
                <div className="min-w-0 flex-1">
                  <Link to={jobPath({ id: report.jobId, title: report.jobTitle })} className="font-bold hover:text-primary">{report.jobTitle}</Link>
                  <p className="text-sm"><span className="font-semibold">{report.reason}</span> — {report.note || 'no details'}</p>
                  <p className="text-xs text-muted">Reported by {report.reportedBy} on {formatDate(report.createdAt)}</p>
                </div>
                <Link to={jobPath({ id: report.jobId, title: report.jobTitle })} className="btn-outline">View</Link>
                <button
                  type="button"
                  className="btn-outline"
                  onClick={async () => {
                    await resolveReport(report.id, false)
                    toast.success('Report dismissed')
                    reports.reload()
                  }}
                >
                  Dismiss
                </button>
                <button type="button" className="btn-danger" onClick={() => setTakeDown(report)}>Take down</button>
              </article>
            ))}
          </>
        )}

        {tab === 'reviews' && (
          <>
            {reviews.loading && <Skeleton className="h-20 w-full" />}
            {reviews.data?.length === 0 && <EmptyState title="No reviews" />}
            {reviews.data?.map((review) => (
              <article key={review.id} className="card flex flex-wrap items-start gap-3 p-4">
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-semibold">{review.companyName} · {review.title}</p>
                  <Stars value={review.rating} />
                  <p className="text-sm text-muted">{review.body}</p>
                  <p className="text-xs text-muted">{review.author} · {formatDate(review.createdAt)}</p>
                </div>
                <button type="button" className="btn-danger" onClick={() => setDeleteId(review.id)}>Remove</button>
              </article>
            ))}
          </>
        )}
      </div>

      <Modal open={Boolean(rejecting)} title={`Reject ${rejecting?.title ?? ''}`} onClose={() => setRejecting(null)}>
        <TextAreaField label="Reason" required rows={3} value={reason} error={attempted ? reasonError : ''} onChange={(event) => setReason(event.target.value)} />
        <div className="mt-4 flex justify-end gap-3">
          <button type="button" className="btn-outline" onClick={() => setRejecting(null)}>Cancel</button>
          <button
            type="button"
            className="btn-danger"
            onClick={async () => {
              setAttempted(true)
              if (reasonError || !rejecting) return
              await setJobModeration(rejecting.id, 'REJECTED', reason.trim())
              toast.success('Job rejected')
              setRejecting(null)
              setReason('')
              setAttempted(false)
              jobs.reload()
            }}
          >
            Reject job
          </button>
        </div>
      </Modal>

      <ConfirmDialog
        open={Boolean(takeDown)}
        danger
        title="Take down this job?"
        message={`"${takeDown?.jobTitle ?? ''}" will be removed from search results.`}
        confirmLabel="Take down"
        onCancel={() => setTakeDown(null)}
        onConfirm={async () => {
          if (takeDown) await resolveReport(takeDown.id, true)
          toast.success('Job taken down')
          setTakeDown(null)
          reports.reload()
        }}
      />
      <ConfirmDialog
        open={Boolean(deleteId)}
        danger
        title="Remove this review?"
        message="The review will be permanently deleted."
        confirmLabel="Remove"
        onCancel={() => setDeleteId(null)}
        onConfirm={async () => {
          if (deleteId) await deleteReview(deleteId)
          toast.success('Review removed')
          setDeleteId(null)
          reviews.reload()
        }}
      />
    </div>
  )
}
