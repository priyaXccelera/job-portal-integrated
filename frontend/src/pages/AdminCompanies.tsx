import { useState } from 'react'
import toast from 'react-hot-toast'
import { TextAreaField } from '../components/fields'
import { CompanyLogo, EmptyState, ErrorState, Modal, PageHeader, Skeleton, StatusBadge, Tabs } from '../components/ui'
import { getAdminCompanies, setCompanyStatus } from '../data/store'
import { useAsync, useSeo } from '../hooks'
import type { Company, CompanyStatus } from '../types'
import { validateMinLength } from '../validation'

export function AdminCompanies() {
  const [tab, setTab] = useState<CompanyStatus>('PENDING')
  const { data, loading, error, reload } = useAsync(() => getAdminCompanies(tab), [tab])
  const [detail, setDetail] = useState<Company | null>(null)
  const [rejecting, setRejecting] = useState<Company | null>(null)
  const [reason, setReason] = useState('')
  const [attempted, setAttempted] = useState(false)
  useSeo('Company approvals', 'Review company registrations.')
  const reasonError = validateMinLength(reason, 5, 'Reason')

  const approve = async (company: Company) => {
    await setCompanyStatus(company.id, 'APPROVED')
    toast.success(`${company.name} approved`)
    setDetail(null)
    reload()
  }

  const reject = async () => {
    setAttempted(true)
    if (reasonError || !rejecting) return
    await setCompanyStatus(rejecting.id, 'REJECTED', reason.trim())
    toast.success(`${rejecting.name} rejected`)
    setRejecting(null)
    setReason('')
    setAttempted(false)
    reload()
  }

  return (
    <div>
      <PageHeader title="Company approvals" subtitle="Approve or reject recruiter companies before they can post." />
      <Tabs
        active={tab}
        onChange={(value) => setTab(value as typeof tab)}
        tabs={[
          { value: 'PENDING', label: 'Pending' },
          { value: 'APPROVED', label: 'Approved' },
          { value: 'REJECTED', label: 'Rejected' },
          { value: 'BLOCKED', label: 'Blocked' },
        ]}
      />
      <div className="mt-4 space-y-3">
        {loading && <Skeleton className="h-20 w-full" />}
        {error && <ErrorState message={error} onRetry={reload} />}
        {!loading && !error && data?.length === 0 && <EmptyState title="Nothing in this queue" />}
        {data?.map((company) => (
          <article key={company.id} className="card flex flex-wrap items-center gap-4 p-4">
            <CompanyLogo src={company.logoUrl} name={company.name} />
            <div className="min-w-0 flex-1">
              <p className="font-bold">{company.name}</p>
              <p className="text-sm text-muted">{company.industry} · {company.headquarters || 'No location'}</p>
            </div>
            <StatusBadge status={company.status} />
            <button type="button" className="btn-outline" onClick={() => setDetail(company)}>View details</button>
            {company.status !== 'APPROVED' && <button type="button" className="btn-primary" onClick={() => approve(company)}>Approve</button>}
            {company.status !== 'REJECTED' && <button type="button" className="btn-danger" onClick={() => setRejecting(company)}>Reject</button>}
          </article>
        ))}
      </div>

      <Modal open={Boolean(detail)} title={detail?.name ?? ''} onClose={() => setDetail(null)} wide>
        {detail && (
          <div className="space-y-3 text-sm">
            <dl className="grid grid-cols-2 gap-3">
              <div><dt className="text-muted">Industry</dt><dd>{detail.industry}</dd></div>
              <div><dt className="text-muted">Type</dt><dd>{detail.companyType}</dd></div>
              <div><dt className="text-muted">Headquarters</dt><dd>{detail.headquarters || '—'}</dd></div>
              <div><dt className="text-muted">Website</dt><dd>{detail.website || '—'}</dd></div>
            </dl>
            <p className="text-muted">{detail.about || 'No description provided.'}</p>
            <div className="flex justify-end gap-3">
              <button type="button" className="btn-danger" onClick={() => { setRejecting(detail); setDetail(null) }}>Reject</button>
              <button type="button" className="btn-primary" onClick={() => approve(detail)}>Approve</button>
            </div>
          </div>
        )}
      </Modal>

      <Modal open={Boolean(rejecting)} title={`Reject ${rejecting?.name ?? ''}`} onClose={() => setRejecting(null)}>
        <TextAreaField label="Reason" required rows={3} value={reason} error={attempted ? reasonError : ''} help="Shared with the recruiter" onChange={(event) => setReason(event.target.value)} />
        <div className="mt-4 flex justify-end gap-3">
          <button type="button" className="btn-outline" onClick={() => setRejecting(null)}>Cancel</button>
          <button type="button" className="btn-danger" onClick={reject}>Reject company</button>
        </div>
      </Modal>
    </div>
  )
}
