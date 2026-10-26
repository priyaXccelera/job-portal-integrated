import { useEffect, useMemo, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { BellPlus, ChevronDown, ChevronUp, SlidersHorizontal, X } from 'lucide-react'
import toast from 'react-hot-toast'
import { useAuth } from '../auth/auth'
import { JobCard } from '../components/JobCard'
import { JobDetailView } from '../components/JobDetailView'
import { Breadcrumbs, EmptyState, ErrorState, ListSkeleton, Modal, Pagination } from '../components/ui'
import { saveAlert, searchJobs } from '../data/store'
import { PAGE_SIZE, FRESHNESS_OPTIONS, POPULAR_CATEGORIES } from '../constants'
import { useAsync, useMediaQuery, useSeo } from '../hooks'
import type { Facets, Job } from '../types'

const FILTER_GROUPS = [
  { key: 'location', label: 'Location' },
  { key: 'department', label: 'Department' },
  { key: 'roleCategory', label: 'Role category' },
  { key: 'industry', label: 'Industry' },
  { key: 'companyType', label: 'Company type' },
  { key: 'jobType', label: 'Job type' },
  { key: 'employmentType', label: 'Employment type' },
  { key: 'workMode', label: 'Work mode' },
  { key: 'education', label: 'Education' },
  { key: 'company', label: 'Posted by' },
] as const

const SALARY_STEPS = [0, 3, 6, 10, 15, 25, 40]
const FILTER_KEYS = ['location', 'experience', 'salaryMin', 'salaryMax', 'freshness', ...FILTER_GROUPS.map((group) => group.key)]

function FilterGroup({
  label,
  options,
  selected,
  onToggle,
}: {
  label: string
  options: [string, number][]
  selected: string[]
  onToggle: (value: string) => void
}) {
  const [open, setOpen] = useState(true)
  const [showAll, setShowAll] = useState(false)
  const visible = showAll ? options : options.slice(0, 5)
  if (options.length === 0 && selected.length === 0) return null
  return (
    <fieldset className="border-b border-line py-3">
      <legend className="sr-only">{label}</legend>
      <button type="button" aria-expanded={open} className="flex w-full items-center justify-between text-sm font-bold" onClick={() => setOpen(!open)}>
        {label}
        {open ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
      </button>
      {open && (
        <div className="mt-2 space-y-1.5">
          {visible.map(([value, count]) => (
            <label key={value} className="flex cursor-pointer items-center gap-2 text-sm">
              <input type="checkbox" className="h-4 w-4 accent-primary" checked={selected.includes(value)} onChange={() => onToggle(value)} />
              <span className="flex-1 truncate">{value}</span>
              <span className="text-xs text-muted">({count})</span>
            </label>
          ))}
          {options.length > 5 && (
            <button type="button" className="text-xs font-semibold text-primary" onClick={() => setShowAll(!showAll)}>
              {showAll ? 'Show less' : `Show ${options.length - 5} more`}
            </button>
          )}
        </div>
      )}
    </fieldset>
  )
}

function FiltersPanel({
  facets,
  params,
  update,
  toggle,
  onClear,
}: {
  facets: Facets
  params: URLSearchParams
  update: (changes: Record<string, string>) => void
  toggle: (key: string, value: string) => void
  onClear: () => void
}) {
  const [experience, setExperience] = useState(params.get('experience') ?? '0')
  useEffect(() => setExperience(params.get('experience') ?? '0'), [params])
  const listFor = (key: string) => (params.get(key) ?? '').split(',').filter(Boolean)
  const commitExperience = () => update({ experience: experience === '0' && !params.get('experience') ? '' : experience })

  return (
    <div>
      <div className="flex items-center justify-between border-b border-line pb-3">
        <h2 className="font-bold">Filters</h2>
        <button type="button" className="text-sm font-semibold text-primary" onClick={onClear}>
          Clear all
        </button>
      </div>
      <div className="border-b border-line py-3">
        <label htmlFor="experience-slider" className="flex justify-between text-sm font-bold">
          Experience <span className="font-normal text-muted">{experience} yrs</span>
        </label>
        <input
          id="experience-slider"
          type="range"
          min={0}
          max={30}
          value={experience}
          className="mt-2 w-full accent-primary"
          onChange={(event) => setExperience(event.target.value)}
          onPointerUp={commitExperience}
          onKeyUp={commitExperience}
        />
      </div>
      <div className="border-b border-line py-3">
        <p className="text-sm font-bold">Salary (Lacs PA)</p>
        <div className="mt-2 flex items-center gap-2">
          <select aria-label="Minimum salary" className="input py-1" value={params.get('salaryMin') ?? ''} onChange={(event) => update({ salaryMin: event.target.value })}>
            <option value="">Min</option>
            {SALARY_STEPS.slice(1).map((step) => (
              <option key={step} value={step}>
                {step}
              </option>
            ))}
          </select>
          <span className="text-muted">to</span>
          <select aria-label="Maximum salary" className="input py-1" value={params.get('salaryMax') ?? ''} onChange={(event) => update({ salaryMax: event.target.value })}>
            <option value="">Max</option>
            {SALARY_STEPS.slice(2).map((step) => (
              <option key={step} value={step}>
                {step}
              </option>
            ))}
          </select>
        </div>
      </div>
      {FILTER_GROUPS.map((group) => (
        <FilterGroup
          key={group.key}
          label={group.label}
          selected={listFor(group.key)}
          options={Object.entries(facets[group.key] ?? {}).sort((first, second) => second[1] - first[1])}
          onToggle={(value) => toggle(group.key, value)}
        />
      ))}
      <fieldset className="py-3">
        <legend className="mb-2 text-sm font-bold">Freshness</legend>
        <div className="space-y-1.5">
          {FRESHNESS_OPTIONS.map((option) => (
            <label key={option.value} className="flex cursor-pointer items-center gap-2 text-sm">
              <input
                type="radio"
                name="freshness"
                className="h-4 w-4 accent-primary"
                checked={params.get('freshness') === option.value}
                onChange={() => update({ freshness: option.value })}
              />
              <span className="flex-1">{option.label}</span>
              <span className="text-xs text-muted">({facets.freshness?.[option.value] ?? 0})</span>
            </label>
          ))}
        </div>
      </fieldset>
    </div>
  )
}

export function JobSearch() {
  const navigate = useNavigate()
  const { role } = useAuth()
  const [params, setParams] = useSearchParams()
  const [mobileFilters, setMobileFilters] = useState(false)
  const [alertOpen, setAlertOpen] = useState(false)
  const [selectedJob, setSelectedJob] = useState<Job | null>(null)
  const isWide = useMediaQuery('(min-width: 1280px)')
  const query = params.get('q') ?? ''
  const page = Number(params.get('page') || 1)
  const paramsKey = params.toString()
  useSeo(query ? `${query} jobs` : 'Search jobs', `Browse and filter jobs${query ? ` for ${query}` : ''} on JobHub.`)

  const { data, loading, error, reload } = useAsync(() => {
    const flat: Record<string, string> = {}
    params.forEach((value, key) => {
      flat[key] = value
    })
    return searchJobs({ ...flat, pageSize: String(PAGE_SIZE) })
  }, [paramsKey])

  // Preserve scroll position when returning from a job detail page
  useEffect(() => {
    const key = `scroll:${paramsKey}`
    if (!loading && data) {
      const saved = sessionStorage.getItem(key)
      if (saved) window.scrollTo(0, Number(saved))
    }
    return () => {
      sessionStorage.setItem(key, String(window.scrollY))
    }
  }, [loading, data, paramsKey])

  const update = (changes: Record<string, string>) => {
    const next = new URLSearchParams(params)
    Object.entries(changes).forEach(([key, value]) => {
      if (value) next.set(key, value)
      else next.delete(key)
    })
    if (!('page' in changes)) next.delete('page')
    setParams(next)
  }

  const toggle = (key: string, value: string) => {
    const current = (params.get(key) ?? '').split(',').filter(Boolean)
    const next = current.includes(value) ? current.filter((entry) => entry !== value) : [...current, value]
    update({ [key]: next.join(',') })
  }

  const clearAll = () => {
    const next = new URLSearchParams()
    if (query) next.set('q', query)
    setParams(next)
  }

  const chips = useMemo(
    () =>
      FILTER_KEYS.flatMap((key) => {
        const raw = params.get(key)
        if (!raw) return []
        if (key === 'experience') return [{ key, value: raw, label: `${raw} yrs experience` }]
        if (key === 'salaryMin') return [{ key, value: raw, label: `Min ${raw} Lacs` }]
        if (key === 'salaryMax') return [{ key, value: raw, label: `Max ${raw} Lacs` }]
        if (key === 'freshness') return [{ key, value: raw, label: FRESHNESS_OPTIONS.find((option) => option.value === raw)?.label ?? raw }]
        return raw.split(',').map((value) => ({ key, value, label: value }))
      }),
    [params],
  )

  const removeChip = (key: string, value: string) => {
    if (['experience', 'salaryMin', 'salaryMax', 'freshness'].includes(key)) update({ [key]: '' })
    else toggle(key, value)
  }

  const createAlert = async () => {
    try {
      await saveAlert({
        keywords: query,
        locations: params.get('location') ?? '',
        experience: params.get('experience') ?? '',
        salary: params.get('salaryMin') ?? '',
        frequency: 'DAILY',
        active: true,
      })
      toast.success('Job alert created')
      setAlertOpen(false)
      navigate('/seeker/alerts')
    } catch {
      // error toast shown by API client
    }
  }

  const filters = (
    <FiltersPanel facets={data?.meta.facets ?? {}} params={params} update={update} toggle={toggle} onClear={clearAll} />
  )

  return (
    <div className="mx-auto max-w-7xl px-4 py-6">
      <Breadcrumbs items={[{ label: 'Home', to: '/' }, { label: 'Jobs' }]} />
      <div className="flex gap-6">
        <aside className="hidden w-64 shrink-0 lg:block">
          <div className="card sticky top-20 max-h-[calc(100vh-6rem)] overflow-y-auto p-4">{filters}</div>
        </aside>

        <section className="min-w-0 flex-1" aria-live="polite">
          <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
            <h1 className="text-xl font-bold">
              {loading ? 'Searching…' : `${data?.meta.total ?? 0} jobs found`}
              {query && <span className="font-normal text-muted"> for “{query}”</span>}
            </h1>
            <div className="flex items-center gap-2">
              <button type="button" className="btn-outline lg:hidden" onClick={() => setMobileFilters(true)}>
                <SlidersHorizontal className="h-4 w-4" />
                Filters
              </button>
              {role === 'JOB_SEEKER' && (
                <button type="button" className="btn-outline" onClick={() => setAlertOpen(true)}>
                  <BellPlus className="h-4 w-4" />
                  Create job alert
                </button>
              )}
              <label className="flex items-center gap-2 text-sm">
                <span className="text-muted">Sort by</span>
                <select className="input w-auto py-1.5" value={params.get('sort') ?? 'relevance'} onChange={(event) => update({ sort: event.target.value === 'relevance' ? '' : event.target.value })}>
                  <option value="relevance">Relevance</option>
                  <option value="date">Date</option>
                </select>
              </label>
            </div>
          </div>

          {chips.length > 0 && (
            <div className="mb-4 flex flex-wrap items-center gap-2">
              {chips.map((chip) => (
                <span key={`${chip.key}-${chip.value}`} className="chip">
                  {chip.label}
                  <button type="button" aria-label={`Remove ${chip.label}`} onClick={() => removeChip(chip.key, chip.value)}>
                    <X className="h-3 w-3" />
                  </button>
                </span>
              ))}
              <button type="button" className="text-sm font-semibold text-primary" onClick={clearAll}>
                Clear all
              </button>
            </div>
          )}

          <div className="flex gap-6">
            <div className="min-w-0 flex-1 space-y-4">
              {loading && <ListSkeleton count={5} />}
              {error && <ErrorState message={error} onRetry={reload} />}
              {!loading && !error && data && data.data.length === 0 && (
                <EmptyState
                  title="No jobs match your search"
                  message="Try removing some filters, checking the spelling, or searching a related keyword."
                  action={
                    <div className="space-y-3">
                      <button type="button" className="btn-primary" onClick={clearAll}>
                        Clear all filters
                      </button>
                      <div className="flex flex-wrap justify-center gap-2">
                        {POPULAR_CATEGORIES.slice(0, 5).map((category) => (
                          <Link key={category} to={`/jobs?q=${encodeURIComponent(category)}`} className="chip">
                            {category}
                          </Link>
                        ))}
                      </div>
                    </div>
                  }
                />
              )}
              {!loading &&
                data?.data.map((job) => (
                  <JobCard key={job.id} job={job} selected={selectedJob?.id === job.id} onOpen={isWide ? setSelectedJob : undefined} />
                ))}
              {data && (
                <Pagination
                  page={page}
                  pageSize={PAGE_SIZE}
                  total={data.meta.total}
                  onChange={(next) => {
                    window.scrollTo(0, 0)
                    update({ page: String(next) })
                  }}
                />
              )}
            </div>
            {isWide && selectedJob && (
              <aside className="card sticky top-20 hidden h-[calc(100vh-6rem)] w-[28rem] shrink-0 overflow-y-auto p-5 xl:block" aria-label="Job details">
                <button type="button" className="mb-2 text-xs font-semibold text-muted hover:text-ink" onClick={() => setSelectedJob(null)}>
                  Close panel
                </button>
                <JobDetailView jobId={selectedJob.id} compact />
              </aside>
            )}
          </div>
        </section>
      </div>

      {mobileFilters && (
        <div className="fixed inset-0 z-50 flex items-end bg-black/50 lg:hidden">
          <div role="dialog" aria-modal="true" aria-label="Filters" className="max-h-[85vh] w-full overflow-y-auto rounded-t-2xl bg-surface p-4">
            <div className="mb-2 flex justify-end">
              <button type="button" className="btn-primary" onClick={() => setMobileFilters(false)}>
                Show {data?.meta.total ?? 0} jobs
              </button>
            </div>
            {filters}
          </div>
        </div>
      )}

      <Modal open={alertOpen} title="Create job alert" onClose={() => setAlertOpen(false)}>
        <p className="text-sm text-muted">
          We will email you new jobs matching “{query || 'all jobs'}”
          {params.get('location') ? ` in ${params.get('location')}` : ''}.
        </p>
        <div className="mt-6 flex justify-end gap-3">
          <button type="button" className="btn-outline" onClick={() => setAlertOpen(false)}>
            Cancel
          </button>
          <button type="button" className="btn-primary" onClick={createAlert}>
            Create alert
          </button>
        </div>
      </Modal>
    </div>
  )
}
