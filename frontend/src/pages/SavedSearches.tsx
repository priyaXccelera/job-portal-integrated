import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { Eye, Pencil, Plus, Trash2 } from 'lucide-react'
import toast from 'react-hot-toast'
import { TextField } from '../components/fields'
import { ConfirmDialog, EmptyState, ErrorState, Modal, PageHeader, Skeleton } from '../components/ui'
import { deleteFolder, deleteSavedSearch, getFolderCandidates, getFolders, getSavedSearches, saveFolder } from '../data/store'
import { useAsync, useSeo } from '../hooks'
import type { Folder } from '../types'
import { formatCtc, formatDate } from '../utils/format'
import { validateMinLength } from '../validation'

export function SavedSearches() {
  const navigate = useNavigate()
  const searches = useAsync(() => getSavedSearches(), [])
  const folders = useAsync(() => getFolders(), [])
  const [editing, setEditing] = useState<{ id?: string; name: string } | null>(null)
  const [attempted, setAttempted] = useState(false)
  const [viewing, setViewing] = useState<Folder | null>(null)
  const viewed = useAsync(() => (viewing ? getFolderCandidates(viewing.id) : Promise.resolve([])), [viewing?.id])
  const [deleteTarget, setDeleteTarget] = useState<{ kind: 'folder' | 'search'; id: string; name: string } | null>(null)
  useSeo('Saved searches & folders', 'Manage saved searches and talent pools.')

  const nameError = editing ? validateMinLength(editing.name, 2, 'Folder name') : ''

  const submitFolder = async () => {
    setAttempted(true)
    if (!editing || nameError) return
    await saveFolder(editing.name.trim(), editing.id)
    toast.success(editing.id ? 'Folder updated' : 'Folder created')
    setEditing(null)
    setAttempted(false)
    folders.reload()
  }

  return (
    <div className="space-y-8">
      <PageHeader title="Saved searches & folders" />

      <section aria-label="Saved searches">
        <h2 className="mb-3 text-lg font-bold">Saved searches</h2>
        {searches.loading && <Skeleton className="h-20 w-full" />}
        {searches.error && <ErrorState message={searches.error} onRetry={searches.reload} />}
        {searches.data?.length === 0 && <EmptyState title="No saved searches" message="Save a search from the candidate database." action={<Link to="/recruiter/candidates" className="btn-primary">Search candidates</Link>} />}
        <div className="space-y-2">
          {searches.data?.map((search) => (
            <div key={search.id} className="card flex flex-wrap items-center gap-3 p-4">
              <div className="min-w-0 flex-1">
                <p className="font-semibold">{search.name}</p>
                <p className="truncate text-xs text-muted">{search.criteria || 'All candidates'} · updated {formatDate(search.updatedAt)}</p>
              </div>
              <button type="button" className="btn-outline" onClick={() => navigate(`/recruiter/candidates?${search.criteria}`)}>Run search</button>
              <button type="button" aria-label={`Delete search ${search.name}`} className="rounded p-2 text-danger hover:bg-soft" onClick={() => setDeleteTarget({ kind: 'search', id: search.id, name: search.name })}>
                <Trash2 className="h-4 w-4" />
              </button>
            </div>
          ))}
        </div>
      </section>

      <section aria-label="Folders">
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-lg font-bold">Folders (talent pools)</h2>
          <button type="button" className="btn-primary" onClick={() => setEditing({ name: '' })}>
            <Plus className="h-4 w-4" />
            New folder
          </button>
        </div>
        {folders.loading && <Skeleton className="h-20 w-full" />}
        {folders.data?.length === 0 && <EmptyState title="No folders yet" message="Create a folder to organise promising candidates." />}
        <div className="grid gap-3 sm:grid-cols-2">
          {folders.data?.map((folder) => (
            <div key={folder.id} className="card flex items-center gap-3 p-4">
              <div className="flex-1">
                <p className="font-semibold">{folder.name}</p>
                <p className="text-xs text-muted">{folder.candidateIds.length} candidates</p>
              </div>
              <button type="button" aria-label={`View ${folder.name}`} className="rounded p-2 hover:bg-soft" onClick={() => setViewing(folder)}>
                <Eye className="h-4 w-4" />
              </button>
              <button type="button" aria-label={`Edit ${folder.name}`} className="rounded p-2 hover:bg-soft" onClick={() => setEditing({ id: folder.id, name: folder.name })}>
                <Pencil className="h-4 w-4" />
              </button>
              <button type="button" aria-label={`Delete ${folder.name}`} className="rounded p-2 text-danger hover:bg-soft" onClick={() => setDeleteTarget({ kind: 'folder', id: folder.id, name: folder.name })}>
                <Trash2 className="h-4 w-4" />
              </button>
            </div>
          ))}
        </div>
      </section>

      <Modal open={editing !== null} title={editing?.id ? 'Edit folder' : 'Create folder'} onClose={() => { setEditing(null); setAttempted(false) }}>
        <form
          noValidate
          onSubmit={(event) => {
            event.preventDefault()
            submitFolder()
          }}
        >
          <TextField label="Folder name" required value={editing?.name ?? ''} error={attempted ? nameError : ''} onChange={(event) => setEditing(editing ? { ...editing, name: event.target.value } : editing)} />
          <div className="mt-4 flex justify-end gap-3">
            <button type="button" className="btn-outline" onClick={() => setEditing(null)}>Cancel</button>
            <button type="submit" className="btn-primary" disabled={attempted && Boolean(nameError)}>Save</button>
          </div>
        </form>
      </Modal>

      <Modal open={Boolean(viewing)} title={viewing?.name ?? ''} onClose={() => setViewing(null)} wide>
        {viewed.loading && <Skeleton className="h-16 w-full" />}
        {viewed.data?.length === 0 && <p className="text-sm text-muted">This folder is empty.</p>}
        <ul className="divide-y divide-line">
          {viewed.data?.map((candidate) => (
            <li key={candidate.id} className="py-3 text-sm">
              <p className="font-semibold">{candidate.name}</p>
              <p className="text-muted">{candidate.headline} · {candidate.location} · {formatCtc(candidate.expectedCtc)}</p>
              <p className="text-xs text-muted">{candidate.email} · {candidate.mobile}</p>
            </li>
          ))}
        </ul>
      </Modal>

      <ConfirmDialog
        open={Boolean(deleteTarget)}
        danger
        title={`Delete ${deleteTarget?.kind ?? ''}?`}
        message={`"${deleteTarget?.name ?? ''}" will be permanently removed.`}
        confirmLabel="Delete"
        onCancel={() => setDeleteTarget(null)}
        onConfirm={async () => {
          if (deleteTarget?.kind === 'folder') {
            await deleteFolder(deleteTarget.id)
            folders.reload()
          } else if (deleteTarget) {
            await deleteSavedSearch(deleteTarget.id)
            searches.reload()
          }
          toast.success('Deleted')
          setDeleteTarget(null)
        }}
      />
    </div>
  )
}
