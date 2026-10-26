import { useState } from 'react'
import { Link, useParams, useSearchParams } from 'react-router-dom'
import { Download, Kanban, List } from 'lucide-react'
import toast from 'react-hot-toast'
import { CandidateDrawer } from '../components/CandidateDrawer'
import { KanbanBoard } from '../components/KanbanBoard'
import { SelectField, TextAreaField, TextField } from '../components/fields'
import { Breadcrumbs, EmptyState, ErrorState, Modal, PageHeader, Skeleton, Stars, StatusBadge } from '../components/ui'
import { exportApplicantsCsv, getApplicants, getRecruiterJob, setApplicationStatus } from '../data/store'
import { ALL_APPLICATION_STATUSES, EDUCATION_LEVELS, NOTICE_PERIODS, STATUS_LABELS } from '../constants'
import { useAsync, useSeo } from '../hooks'
import type { Application, ApplicationStatus } from '../types'
import { formatCtc, formatDate } from '../utils/format'

const FILTER_KEYS = ['status', 'experienceMin', 'experienceMax', 'location', 'ctcMin', 'ctcMax', 'skills', 'noticePeriod', 'education', 'appliedAfter', 'screening', 'sort']

export function Applicants() {
  const { id = '' } = useParams()
  const [params, setParams] = useSearchParams()
  const view = params.get('view') === 'board' ? 'board' : 'list'
  const filters = Object.fromEntries(FILTER_KEYS.map((key) => [key, params.get(key) ?? '']).filter(([, value]) => value))
  const filtersKey = JSON.stringify(filters)
  const job = useAsync(() => getRecruiterJob(id), [id])
  const { data, loading, error, reload } = useAsync(() => getApplicants(id, filters), [id, filtersKey])
  const [selected, setSelected] = useState<string[]>([])
  const [openId, setOpenId] = useState<string | null>(null)
  const [bulkStatus, setBulkStatus] = useState<ApplicationStatus>('SHORTLISTED')
  const [pendingMove, setPendingMove] = useState<{ ids: string[]; status: ApplicationStatus } | null>(null)
  const [moveMessage, setMoveMessage] = useState('')
  useSeo('Applicants', 'Review applicants for this job.')

  const applications = data?.data ?? []
  const opened = applications.find((application) => application.id === openId) ?? null

  const setFilter = (key: string, value: string) => {
    const next = new URLSearchParams(params)
    if (value) next.set(key, value)
    else next.delete(key)
    setParams(next, { replace: true })
  }

  const applyMove = async () => {
    if (!pendingMove) return
    try {
      await setApplicationStatus(pendingMove.ids, pendingMove.status, moveMessage.trim())
      toast.success(`${pendingMove.ids.length} candidate(s) moved to ${STATUS_LABELS[pendingMove.status]}`)
      setSelected([])
      reload()
    } catch {
      // API client shows the error toast
    } finally {
      setPendingMove(null)
      setMoveMessage('')
    }
  }

  const allSelected = applications.length > 0 && selected.length === applications.length

  return (
    <div>
      <Breadcrumbs items={[{ label: 'Manage jobs', to: '/recruiter/jobs' }, { label: job.data?.title ?? 'Applicants' }]} />
      <PageHeader
        title={`Applicants${job.data ? ` · ${job.data.title}` : ''}`}
        subtitle={`${data?.meta.total ?? 0} candidates`}
        actions={
          <>
            <div className="flex overflow-hidden rounded-lg border border-line" role="group" aria-label="View mode">
              <button type="button" aria-pressed={view === 'list'} className={`flex items-center gap-1 px-3 py-2 text-sm font-semibold ${view === 'list' ? 'bg-primary text-white' : ''}`} onClick={() => setFilter('view', '')}>
                <List className="h-4 w-4" /> List
              </button>
              <button type="button" aria-pressed={view === 'board'} className={`flex items-center gap-1 px-3 py-2 text-sm font-semibold ${view === 'board' ? 'bg-primary text-white' : ''}`} onClick={() => setFilter('view', 'board')}>
                <Kanban className="h-4 w-4" /> Board
              </button>
            </div>
            <button type="button" className="btn-outline" onClick={() => exportApplicantsCsv(id, filters)}>
              <Download className="h-4 w-4" />
              Export CSV
            </button>
          </>
        }
      />

      <details className="card mb-4 p-4" open>
        <summary className="cursor-pointer font-bold">Filters &amp; sorting</summary>
        <div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <SelectField label="Status" value={filters.status ?? ''} placeholder="Any" options={ALL_APPLICATION_STATUSES.map((status) => ({ value: status, label: STATUS_LABELS[status] }))} onChange={(event) => setFilter('status', event.target.value)} />
          <TextField label="Min experience" type="number" min={0} value={filters.experienceMin ?? ''} onChange={(event) => setFilter('experienceMin', event.target.value)} />
          <TextField label="Max experience" type="number" min={0} value={filters.experienceMax ?? ''} onChange={(event) => setFilter('experienceMax', event.target.value)} />
          <TextField label="Location" value={filters.location ?? ''} onChange={(event) => setFilter('location', event.target.value)} />
          <TextField label="Min expected CTC" type="number" min={0} value={filters.ctcMin ?? ''} onChange={(event) => setFilter('ctcMin', event.target.value)} />
          <TextField label="Max expected CTC" type="number" min={0} value={filters.ctcMax ?? ''} onChange={(event) => setFilter('ctcMax', event.target.value)} />
          <TextField label="Skills" value={filters.skills ?? ''} help="Comma separated" onChange={(event) => setFilter('skills', event.target.value)} />
          <SelectField label="Notice period" value={filters.noticePeriod ?? ''} placeholder="Any" options={NOTICE_PERIODS} onChange={(event) => setFilter('noticePeriod', event.target.value)} />
          <SelectField label="Education" value={filters.education ?? ''} placeholder="Any" options={EDUCATION_LEVELS} onChange={(event) => setFilter('education', event.target.value)} />
          <TextField label="Applied after" type="date" value={filters.appliedAfter ?? ''} onChange={(event) => setFilter('appliedAfter', event.target.value)} />
          <SelectField label="Screening" value={filters.screening ?? ''} placeholder="Any" options={[{ value: 'in', label: 'Screened in' }, { value: 'out', label: 'Screened out' }]} onChange={(event) => setFilter('screening', event.target.value)} />
          <SelectField label="Sort by" value={filters.sort ?? ''} placeholder="Best match" options={[{ value: 'experience', label: 'Experience' }, { value: 'rating', label: 'Rating' }, { value: 'date', label: 'Applied date' }]} onChange={(event) => setFilter('sort', event.target.value)} />
        </div>
        <button type="button" className="mt-3 text-sm font-semibold text-primary" onClick={() => setParams(view === 'board' ? { view: 'board' } : {})}>
          Clear filters
        </button>
      </details>

      {loading && <Skeleton className="h-64 w-full" />}
      {error && <ErrorState message={error} onRetry={reload} />}
      {!loading && !error && applications.length === 0 && (
        <EmptyState title="No applicants match" message="Adjust the filters or wait for new applications." action={<Link to="/recruiter/jobs" className="btn-primary">Back to jobs</Link>} />
      )}

      {!loading && applications.length > 0 && view === 'board' && (
        <KanbanBoard
          applications={applications}
          onOpen={(application) => setOpenId(application.id)}
          onMove={(application, status) => setPendingMove({ ids: [application.id], status })}
        />
      )}

      {!loading && applications.length > 0 && view === 'list' && (
        <>
          {selected.length > 0 && (
            <div className="card mb-3 flex flex-wrap items-center gap-3 p-3" role="region" aria-label="Bulk actions">
              <span className="text-sm font-semibold">{selected.length} selected</span>
              <button type="button" className="btn-primary" onClick={() => setPendingMove({ ids: selected, status: 'SHORTLISTED' })}>Shortlist</button>
              <button type="button" className="btn-danger" onClick={() => setPendingMove({ ids: selected, status: 'REJECTED' })}>Reject</button>
              <select className="input w-auto" aria-label="Move to status" value={bulkStatus} onChange={(event) => setBulkStatus(event.target.value as ApplicationStatus)}>
                {ALL_APPLICATION_STATUSES.map((status) => <option key={status} value={status}>{STATUS_LABELS[status]}</option>)}
              </select>
              <button type="button" className="btn-outline" onClick={() => setPendingMove({ ids: selected, status: bulkStatus })}>Move</button>
            </div>
          )}
          <div className="card overflow-x-auto">
            <table className="w-full min-w-[60rem] text-left text-sm">
              <thead className="border-b border-line text-xs uppercase text-muted">
                <tr>
                  <th className="p-3">
                    <input type="checkbox" aria-label="Select all candidates" className="accent-primary" checked={allSelected} onChange={() => setSelected(allSelected ? [] : applications.map((application) => application.id))} />
                  </th>
                  <th>Candidate</th>
                  <th>Exp.</th>
                  <th>Location</th>
                  <th>Current / Expected CTC</th>
                  <th>Skills</th>
                  <th>Match</th>
                  <th>Rating</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {applications.map((application: Application) => (
                  <tr key={application.id} className="cursor-pointer hover:bg-soft/50" onClick={() => setOpenId(application.id)}>
                    <td className="p-3" onClick={(event) => event.stopPropagation()}>
                      <input
                        type="checkbox"
                        aria-label={`Select ${application.candidateName}`}
                        className="accent-primary"
                        checked={selected.includes(application.id)}
                        onChange={() => setSelected(selected.includes(application.id) ? selected.filter((entry) => entry !== application.id) : [...selected, application.id])}
                      />
                    </td>
                    <td>
                      <p className="font-semibold">{application.candidateName}</p>
                      <p className="max-w-56 truncate text-xs text-muted">{application.headline}</p>
                      <p className="text-xs text-muted">Applied {formatDate(application.appliedAt)}</p>
                    </td>
                    <td>{application.experience} yrs</td>
                    <td>{application.location}</td>
                    <td>{formatCtc(application.currentCtc)} / {formatCtc(application.expectedCtc)}</td>
                    <td className="max-w-48">
                      <div className="flex flex-wrap gap-1">
                        {application.skills.slice(0, 3).map((skill) => <span key={skill} className="rounded bg-canvas px-1.5 py-0.5 text-xs">{skill}</span>)}
                      </div>
                    </td>
                    <td className="font-semibold text-success">{application.matchPercentage}%</td>
                    <td><Stars value={application.rating} size="h-3.5 w-3.5" /></td>
                    <td><StatusBadge status={application.status} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}

      <CandidateDrawer application={opened} onClose={() => setOpenId(null)} onChanged={reload} />

      <Modal open={Boolean(pendingMove)} title={`Move to ${pendingMove ? STATUS_LABELS[pendingMove.status] : ''}`} onClose={() => setPendingMove(null)}>
        <p className="mb-3 text-sm text-muted">{pendingMove?.ids.length} candidate(s) will be updated.</p>
        <TextAreaField label="Message to candidate (optional)" rows={3} value={moveMessage} onChange={(event) => setMoveMessage(event.target.value)} />
        <div className="mt-4 flex justify-end gap-3">
          <button type="button" className="btn-outline" onClick={() => setPendingMove(null)}>Cancel</button>
          <button type="button" className="btn-primary" onClick={applyMove}>Confirm</button>
        </div>
      </Modal>
    </div>
  )
}
