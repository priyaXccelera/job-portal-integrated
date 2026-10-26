import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { JobCard } from '../components/JobCard'
import { EmptyState, ErrorState, ListSkeleton, PageHeader, Pagination, Tabs } from '../components/ui'
import { getRecentSearches, getRecommendedJobs } from '../data/store'
import { PAGE_SIZE } from '../constants'
import { useAsync, useSeo } from '../hooks'
import { WORK_MODES } from '../constants'

type Tab = 'profile' | 'searches'

export function RecommendedJobs() {
  const [tab, setTab] = useState<Tab>('profile')
  const [sort, setSort] = useState<'match' | 'date'>('match')
  const [workMode, setWorkMode] = useState('')
  const [page, setPage] = useState(1)
  const jobs = useAsync(() => getRecommendedJobs(), [])
  const searches = useAsync(() => getRecentSearches(), [])
  useSeo('Recommended jobs', 'Jobs recommended for you based on your profile and recent searches.')

  const visible = useMemo(() => {
    let list = jobs.data ?? []
    if (tab === 'searches') {
      const terms = (searches.data ?? []).map((term) => term.toLowerCase())
      list = list.filter((job) => terms.some((term) => job.title.toLowerCase().includes(term) || job.skills.some((skill) => skill.toLowerCase().includes(term))))
    }
    if (workMode) list = list.filter((job) => job.workMode === workMode)
    return [...list].sort((first, second) =>
      sort === 'date' ? new Date(second.postedAt).getTime() - new Date(first.postedAt).getTime() : (second.matchScore?.percentage ?? 0) - (first.matchScore?.percentage ?? 0),
    )
  }, [jobs.data, searches.data, tab, sort, workMode])

  return (
    <div>
      <PageHeader title="Recommended jobs" subtitle="Based on your profile skills and recent activity." />
      <Tabs
        active={tab}
        onChange={(next) => {
          setTab(next)
          setPage(1)
        }}
        tabs={[
          { value: 'profile', label: 'Based on your profile' },
          { value: 'searches', label: 'Based on recent searches' },
        ]}
      />
      <div className="my-4 flex flex-wrap gap-3">
        <select className="input w-auto" aria-label="Sort" value={sort} onChange={(event) => setSort(event.target.value as 'match' | 'date')}>
          <option value="match">Best match</option>
          <option value="date">Most recent</option>
        </select>
        <select className="input w-auto" aria-label="Work mode" value={workMode} onChange={(event) => setWorkMode(event.target.value)}>
          <option value="">All work modes</option>
          {WORK_MODES.map((mode) => (
            <option key={mode} value={mode}>{mode}</option>
          ))}
        </select>
        {tab === 'searches' && searches.data && searches.data.length > 0 && (
          <span className="self-center text-sm text-muted">Recent: {searches.data.join(', ')}</span>
        )}
      </div>
      {jobs.loading && <ListSkeleton />}
      {jobs.error && <ErrorState message={jobs.error} onRetry={jobs.reload} />}
      {!jobs.loading && !jobs.error && visible.length === 0 && (
        <EmptyState title="No recommendations yet" message="Add skills to your profile or run a few searches to get recommendations." action={<Link to="/jobs" className="btn-primary">Search jobs</Link>} />
      )}
      <div className="space-y-4">
        {visible.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE).map((job) => (
          <JobCard key={job.id} job={job} />
        ))}
      </div>
      <Pagination page={page} pageSize={PAGE_SIZE} total={visible.length} onChange={setPage} />
    </div>
  )
}
