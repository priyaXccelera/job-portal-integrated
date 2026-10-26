import { useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { Search } from 'lucide-react'
import { CompanyCard } from '../components/JobCard'
import { Breadcrumbs, EmptyState, ErrorState, Pagination, Skeleton } from '../components/ui'
import { getCompanies, getMasterList } from '../data/store'
import { useAsync, useDebouncedValue, useSeo } from '../hooks'

const COMPANY_TYPES = ['Corporate', 'Startup', 'MNC']

export function CompaniesDirectory() {
  const [params, setParams] = useSearchParams()
  const [search, setSearch] = useState(params.get('q') ?? '')
  const debounced = useDebouncedValue(search)
  const industry = params.get('industry') ?? ''
  const companyType = params.get('type') ?? ''
  const page = Number(params.get('page') || 1)
  useSeo('Companies', 'Browse top companies hiring on JobHub.')

  const industries = useAsync(() => getMasterList('industries'), [])
  const result = useAsync(() => getCompanies({ q: debounced, industry, companyType, page }), [debounced, industry, companyType, page])

  const update = (changes: Record<string, string>) => {
    const next = new URLSearchParams(params)
    Object.entries(changes).forEach(([key, value]) => (value ? next.set(key, value) : next.delete(key)))
    if (!('page' in changes)) next.delete('page')
    setParams(next)
  }

  return (
    <div className="mx-auto max-w-5xl px-4 py-6">
      <Breadcrumbs items={[{ label: 'Home', to: '/' }, { label: 'Companies' }]} />
      <h1 className="mb-4 text-2xl font-bold">Explore companies</h1>
      <div className="card mb-6 flex flex-col gap-3 p-4 sm:flex-row">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-2.5 h-4 w-4 text-muted" />
          <input className="input pl-9" type="search" aria-label="Search companies by name" placeholder="Search by company name" value={search} onChange={(event) => setSearch(event.target.value)} />
        </div>
        <select className="input sm:w-52" aria-label="Industry" value={industry} onChange={(event) => update({ industry: event.target.value })}>
          <option value="">All industries</option>
          {industries.data?.map((item) => (
            <option key={item.id} value={item.name}>{item.name}</option>
          ))}
        </select>
        <select className="input sm:w-44" aria-label="Company type" value={companyType} onChange={(event) => update({ type: event.target.value })}>
          <option value="">All types</option>
          {COMPANY_TYPES.map((type) => (
            <option key={type} value={type}>{type}</option>
          ))}
        </select>
      </div>

      {result.error && <ErrorState message={result.error} onRetry={result.reload} />}
      {result.loading && (
        <div className="grid gap-4 sm:grid-cols-2">
          {Array.from({ length: 4 }, (_, index) => <Skeleton key={index} className="h-24 w-full" />)}
        </div>
      )}
      {!result.loading && result.data && result.data.data.length === 0 && (
        <EmptyState title="No companies found" message="Try a different name, industry or type." />
      )}
      <div className="grid gap-4 sm:grid-cols-2">
        {!result.loading && result.data?.data.map((company) => <CompanyCard key={company.id} company={company} />)}
      </div>
      {result.data && (
        <Pagination page={page} pageSize={result.data.meta.pageSize} total={result.data.meta.total} onChange={(next) => update({ page: String(next) })} />
      )}
    </div>
  )
}
