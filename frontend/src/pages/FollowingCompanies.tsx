import { useState } from 'react'
import { Link } from 'react-router-dom'
import toast from 'react-hot-toast'
import { CompanyCard, JobCard } from '../components/JobCard'
import { ConfirmDialog, EmptyState, ErrorState, PageHeader, Pagination, Skeleton } from '../components/ui'
import { getFollowingCompanies, searchJobs, unfollowCompany } from '../data/store'
import { useAsync, useSeo } from '../hooks'
import type { Company } from '../types'

const PAGE = 4

export function FollowingCompanies() {
  const companies = useAsync(() => getFollowingCompanies(), [])
  const names = (companies.data ?? []).map((company) => company.name).join(',')
  const jobs = useAsync(() => (names ? searchJobs({ company: names, sort: 'date', pageSize: '4' }) : Promise.resolve(undefined)), [names])
  const [page, setPage] = useState(1)
  const [target, setTarget] = useState<Company | null>(null)
  useSeo('Following companies', 'Companies you follow.')
  const list = companies.data ?? []

  return (
    <div>
      <PageHeader title="Following" subtitle="Companies you follow and their latest jobs." />
      {companies.loading && <Skeleton className="h-24 w-full" />}
      {companies.error && <ErrorState message={companies.error} onRetry={companies.reload} />}
      {!companies.loading && list.length === 0 && (
        <EmptyState title="You aren't following any company" message="Follow companies to see their new jobs here." action={<Link to="/companies" className="btn-primary">Explore companies</Link>} />
      )}
      <div className="grid gap-4 sm:grid-cols-2">
        {list.slice((page - 1) * PAGE, page * PAGE).map((company) => (
          <div key={company.id} className="space-y-2">
            <CompanyCard company={company} />
            <button type="button" className="btn-outline w-full" onClick={() => setTarget(company)}>
              Unfollow
            </button>
          </div>
        ))}
      </div>
      <Pagination page={page} pageSize={PAGE} total={list.length} onChange={setPage} />

      {jobs.data && jobs.data.data.length > 0 && (
        <section className="mt-8">
          <h2 className="mb-3 text-lg font-bold">Active jobs from followed companies</h2>
          <div className="space-y-3">
            {jobs.data.data.map((job) => <JobCard key={job.id} job={job} />)}
          </div>
        </section>
      )}

      <ConfirmDialog
        open={Boolean(target)}
        title="Unfollow company?"
        message={`You will stop seeing updates from ${target?.name ?? 'this company'}.`}
        confirmLabel="Unfollow"
        danger
        onCancel={() => setTarget(null)}
        onConfirm={async () => {
          if (target) await unfollowCompany(target.id)
          setTarget(null)
          toast.success('Unfollowed')
          companies.reload()
        }}
      />
    </div>
  )
}
