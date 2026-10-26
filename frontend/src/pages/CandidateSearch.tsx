import { useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { FolderPlus, Lock, Mail, Phone, Save, Send } from 'lucide-react'
import toast from 'react-hot-toast'
import { SelectField, TextAreaField, TextField } from '../components/fields'
import { EmptyState, ErrorState, ListSkeleton, Modal, PageHeader, Pagination } from '../components/ui'
import {
  UNLOCK_COST,
  addCandidateToFolder,
  getCredits,
  getFolders,
  getRecruiterJobs,
  inviteCandidate,
  saveSearch,
  searchCandidates,
  unlockCandidate,
} from '../data/store'
import type { CandidateResult } from '../data/storeRecruiter'
import { EDUCATION_LEVELS, NOTICE_PERIODS, PAGE_SIZE } from '../constants'
import { useAsync, useSeo } from '../hooks'
import { formatCtc, timeAgo } from '../utils/format'
import { validateRequired } from '../validation'

const KEYS = ['q', 'skills', 'experienceMin', 'experienceMax', 'location', 'ctcMin', 'ctcMax', 'noticePeriod', 'education', 'industry', 'lastActive', 'page']

export function CandidateSearch() {
  const [params, setParams] = useSearchParams()
  const filters = Object.fromEntries(KEYS.map((key) => [key, params.get(key) ?? '']).filter(([, value]) => value))
  const filtersKey = JSON.stringify(filters)
  const page = Number(params.get('page') || 1)
  const { data, loading, error, reload } = useAsync(() => searchCandidates(filters), [filtersKey])
  const credits = useAsync(() => getCredits(), [])
  const folders = useAsync(() => getFolders(), [])
  const jobs = useAsync(() => getRecruiterJobs('ACTIVE'), [])
  const [keyword, setKeyword] = useState(params.get('q') ?? '')
  const [unlocking, setUnlocking] = useState<CandidateResult | null>(null)
  const [folderTarget, setFolderTarget] = useState<CandidateResult | null>(null)
  const [folderId, setFolderId] = useState('')
  const [inviteTarget, setInviteTarget] = useState<CandidateResult | null>(null)
  const [inviteJob, setInviteJob] = useState('')
  const [inviteMessage, setInviteMessage] = useState('')
  const [inviteAttempted, setInviteAttempted] = useState(false)
  const [saveOpen, setSaveOpen] = useState(false)
  const [searchName, setSearchName] = useState('')
  useSeo('Candidate search', 'Search the candidate database.')

  const setFilter = (key: string, value: string) => {
    const next = new URLSearchParams(params)
    if (value) next.set(key, value)
    else next.delete(key)
    if (key !== 'page') next.delete('page')
    setParams(next, { replace: true })
  }

  const inviteErrors = { job: inviteJob ? '' : 'Select a job', message: validateRequired(inviteMessage, 'Message') }

  const run = async (action: () => Promise<unknown>, message: string) => {
    try {
      await action()
      toast.success(message)
      return true
    } catch {
      return false
    }
  }

  return (
    <div>
      <PageHeader
        title="Candidate database"
        subtitle="Use AND, OR, NOT to refine keywords, e.g. react AND typescript NOT angular"
        actions={
          <span className="chip" aria-label="Credits balance">
            <Lock className="h-3 w-3" />
            {credits.data?.balance ?? '—'} credits · {UNLOCK_COST} per contact
          </span>
        }
      />
      <form
        className="card mb-4 space-y-3 p-4"
        onSubmit={(event) => {
          event.preventDefault()
          setFilter('q', keyword.trim())
        }}
        role="search"
      >
        <div className="flex gap-2">
          <input className="input" aria-label="Keywords" placeholder="Keywords (skills, designation)…" value={keyword} onChange={(event) => setKeyword(event.target.value)} />
          <button type="submit" className="btn-primary">Search</button>
          <button type="button" className="btn-outline" onClick={() => setSaveOpen(true)}>
            <Save className="h-4 w-4" />
            Save search
          </button>
        </div>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <TextField label="Skills" value={filters.skills ?? ''} help="Comma separated" onChange={(event) => setFilter('skills', event.target.value)} />
          <TextField label="Min experience" type="number" min={0} value={filters.experienceMin ?? ''} onChange={(event) => setFilter('experienceMin', event.target.value)} />
          <TextField label="Max experience" type="number" min={0} value={filters.experienceMax ?? ''} onChange={(event) => setFilter('experienceMax', event.target.value)} />
          <TextField label="Location" value={filters.location ?? ''} onChange={(event) => setFilter('location', event.target.value)} />
          <TextField label="Min expected CTC" type="number" min={0} value={filters.ctcMin ?? ''} onChange={(event) => setFilter('ctcMin', event.target.value)} />
          <TextField label="Max expected CTC" type="number" min={0} value={filters.ctcMax ?? ''} onChange={(event) => setFilter('ctcMax', event.target.value)} />
          <SelectField label="Notice period" value={filters.noticePeriod ?? ''} placeholder="Any" options={NOTICE_PERIODS} onChange={(event) => setFilter('noticePeriod', event.target.value)} />
          <SelectField label="Education" value={filters.education ?? ''} placeholder="Any" options={EDUCATION_LEVELS} onChange={(event) => setFilter('education', event.target.value)} />
          <TextField label="Industry" value={filters.industry ?? ''} onChange={(event) => setFilter('industry', event.target.value)} />
          <SelectField label="Last active" value={filters.lastActive ?? ''} placeholder="Any time" options={[{ value: '1', label: 'Last 24 hours' }, { value: '7', label: 'Last 7 days' }, { value: '30', label: 'Last 30 days' }]} onChange={(event) => setFilter('lastActive', event.target.value)} />
        </div>
      </form>

      {loading && <ListSkeleton count={3} />}
      {error && <ErrorState message={error} onRetry={reload} />}
      {!loading && !error && data?.data.length === 0 && <EmptyState title="No candidates found" message="Try fewer filters or different keywords." />}
      <div className="space-y-3">
        {data?.data.map((candidate) => (
          <article key={candidate.id} className="card p-5">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <h2 className="font-bold">{candidate.name}</h2>
                <p className="text-sm text-muted">{candidate.headline}</p>
                <p className="mt-1 text-xs text-muted">
                  {candidate.experience} yrs · {candidate.location} · Current {formatCtc(candidate.currentCtc)} · Expected {formatCtc(candidate.expectedCtc)} · Notice: {candidate.noticePeriod} · Active {timeAgo(candidate.lastActive)}
                </p>
              </div>
              <div className="flex flex-wrap gap-2">
                <button type="button" className="btn-outline" onClick={() => { setFolderTarget(candidate); setFolderId('') }}>
                  <FolderPlus className="h-4 w-4" />
                  Save to folder
                </button>
                <button type="button" className="btn-outline" onClick={() => { setInviteTarget(candidate); setInviteAttempted(false) }}>
                  <Send className="h-4 w-4" />
                  Invite to apply
                </button>
              </div>
            </div>
            <div className="mt-3 flex flex-wrap gap-2">
              {candidate.skills.map((skill) => <span key={skill} className="chip">{skill}</span>)}
            </div>
            <div className="mt-3 flex flex-wrap items-center gap-4 text-sm">
              <span className="flex items-center gap-1"><Mail className="h-4 w-4 text-muted" />{candidate.email}</span>
              <span className="flex items-center gap-1"><Phone className="h-4 w-4 text-muted" />{candidate.mobile}</span>
              {!candidate.unlocked && (
                <button type="button" className="btn-primary" onClick={() => setUnlocking(candidate)}>
                  <Lock className="h-4 w-4" />
                  View contact ({UNLOCK_COST} credits)
                </button>
              )}
            </div>
          </article>
        ))}
      </div>
      {data && <Pagination page={page} pageSize={PAGE_SIZE} total={data.meta.total} onChange={(next) => setFilter('page', String(next))} />}

      <Modal open={Boolean(unlocking)} title="Unlock contact details" onClose={() => setUnlocking(null)}>
        <p className="text-sm">
          Viewing contact details for <strong>{unlocking?.name}</strong> costs <strong>{UNLOCK_COST} credits</strong>. You have <strong>{credits.data?.balance ?? 0}</strong> credits; {(credits.data?.balance ?? 0) - UNLOCK_COST} will remain.
        </p>
        <div className="mt-4 flex justify-end gap-3">
          <button type="button" className="btn-outline" onClick={() => setUnlocking(null)}>Cancel</button>
          <button
            type="button"
            className="btn-primary"
            onClick={async () => {
              if (unlocking && (await run(() => unlockCandidate(unlocking.id), 'Contact unlocked'))) {
                reload()
                credits.reload()
              }
              setUnlocking(null)
            }}
          >
            Unlock
          </button>
        </div>
      </Modal>

      <Modal open={Boolean(folderTarget)} title="Save to folder" onClose={() => setFolderTarget(null)}>
        <SelectField label="Folder" value={folderId} placeholder="Select a folder" options={(folders.data ?? []).map((folder) => ({ value: folder.id, label: folder.name }))} onChange={(event) => setFolderId(event.target.value)} />
        <div className="mt-4 flex justify-end gap-3">
          <button type="button" className="btn-outline" onClick={() => setFolderTarget(null)}>Cancel</button>
          <button
            type="button"
            className="btn-primary"
            disabled={!folderId}
            onClick={async () => {
              if (folderTarget) await run(() => addCandidateToFolder(folderId, folderTarget.id), 'Saved to folder')
              setFolderTarget(null)
            }}
          >
            Save
          </button>
        </div>
      </Modal>

      <Modal open={Boolean(inviteTarget)} title={`Invite ${inviteTarget?.name ?? ''} to apply`} onClose={() => setInviteTarget(null)}>
        <div className="space-y-4">
          <SelectField label="Job" required value={inviteJob} placeholder="Select a job" error={inviteAttempted ? inviteErrors.job : ''} options={(jobs.data ?? []).map((job) => ({ value: job.id, label: job.title }))} onChange={(event) => setInviteJob(event.target.value)} />
          <TextAreaField label="Message" required rows={3} value={inviteMessage} error={inviteAttempted ? inviteErrors.message : ''} onChange={(event) => setInviteMessage(event.target.value)} />
          <div className="flex justify-end gap-3">
            <button type="button" className="btn-outline" onClick={() => setInviteTarget(null)}>Cancel</button>
            <button
              type="button"
              className="btn-primary"
              onClick={async () => {
                setInviteAttempted(true)
                if (inviteErrors.job || inviteErrors.message || !inviteTarget) return
                await run(() => inviteCandidate(inviteTarget.id, inviteJob, inviteMessage.trim()), 'Invitation sent')
                setInviteTarget(null)
                setInviteMessage('')
              }}
            >
              Send invite
            </button>
          </div>
        </div>
      </Modal>

      <Modal open={saveOpen} title="Save this search" onClose={() => setSaveOpen(false)}>
        <TextField label="Search name" value={searchName} error={searchName.trim() ? '' : undefined} onChange={(event) => setSearchName(event.target.value)} />
        <div className="mt-4 flex justify-end gap-3">
          <button type="button" className="btn-outline" onClick={() => setSaveOpen(false)}>Cancel</button>
          <button
            type="button"
            className="btn-primary"
            disabled={!searchName.trim()}
            onClick={async () => {
              await run(() => saveSearch(searchName.trim(), params.toString()), 'Search saved')
              setSaveOpen(false)
              setSearchName('')
            }}
          >
            Save
          </button>
        </div>
      </Modal>
    </div>
  )
}
