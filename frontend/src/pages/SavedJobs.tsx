import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Trash2 } from 'lucide-react'
import toast from 'react-hot-toast'
import { JobCard } from '../components/JobCard'
import { ConfirmDialog, EmptyState, ErrorState, ListSkeleton, PageHeader, Pagination } from '../components/ui'
import { getSavedJobs, unsaveJob } from '../data/store'
import { PAGE_SIZE } from '../constants'
import { useAsync, useSeo } from '../hooks'

export function SavedJobs() {
  const { data, loading, error, reload } = useAsync(() => getSavedJobs(), [])
  const [page, setPage] = useState(1)
  const [removeId, setRemoveId] = useState<string | null>(null)
  useSeo('Saved jobs', 'Jobs you have bookmarked.')
  const jobs = data ?? []

  return (
    <div>
      <PageHeader title="Saved jobs" subtitle={`${jobs.length} saved`} />
      {loading && <ListSkeleton />}
      {error && <ErrorState message={error} onRetry={reload} />}
      {!loading && !error && jobs.length === 0 && (
        <EmptyState title="No saved jobs yet" message="Tap the bookmark icon on a job to save it for later." action={<Link to="/jobs" className="btn-primary">Browse jobs</Link>} />
      )}
      <div className="space-y-4">
        {jobs.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE).map((job) => (
          <div key={job.id} className="relative">
            <JobCard job={job} onSavedChange={() => reload()} />
            <button type="button" className="btn-outline mt-2" onClick={() => setRemoveId(job.id)}>
              <Trash2 className="h-4 w-4" />
              Remove from saved
            </button>
          </div>
        ))}
      </div>
      <Pagination page={page} pageSize={PAGE_SIZE} total={jobs.length} onChange={setPage} />
      <ConfirmDialog
        open={Boolean(removeId)}
        title="Remove saved job?"
        message="This job will be removed from your saved list."
        confirmLabel="Remove"
        danger
        onCancel={() => setRemoveId(null)}
        onConfirm={async () => {
          if (removeId) await unsaveJob(removeId)
          setRemoveId(null)
          toast.success('Removed from saved jobs')
          reload()
        }}
      />
    </div>
  )
}
