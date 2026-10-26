import { useRef, useState } from 'react'
import { Pencil, Plus, Trash2, Upload } from 'lucide-react'
import toast from 'react-hot-toast'
import { TextField } from '../components/fields'
import { ConfirmDialog, EmptyState, ErrorState, Modal, PageHeader, Pagination, Skeleton, Tabs } from '../components/ui'
import { deleteMasterItem, getMasterList, importMasterItems, saveMasterItem } from '../data/store'
import { PAGE_SIZE } from '../constants'
import { useAsync, useDebouncedValue, useSeo } from '../hooks'
import type { MasterItem, MasterType } from '../types'
import { parseCsv } from '../utils/format'
import { validateRequired } from '../validation'

const TYPES: { value: MasterType; label: string }[] = [
  { value: 'skills', label: 'Skills' },
  { value: 'industries', label: 'Industries' },
  { value: 'departments', label: 'Departments' },
  { value: 'role-categories', label: 'Role categories' },
  { value: 'locations', label: 'Locations' },
  { value: 'degrees', label: 'Degrees' },
]

export function AdminMasterData() {
  const [type, setType] = useState<MasterType>('skills')
  const [search, setSearch] = useState('')
  const debounced = useDebouncedValue(search)
  const [page, setPage] = useState(1)
  const { data, loading, error, reload } = useAsync(() => getMasterList(type, debounced), [type, debounced])
  const [editing, setEditing] = useState<{ id?: string; name: string; synonyms: string } | null>(null)
  const [attempted, setAttempted] = useState(false)
  const [deleting, setDeleting] = useState<MasterItem | null>(null)
  const fileInput = useRef<HTMLInputElement>(null)
  useSeo('Master data', 'Manage master data.')

  const items = data ?? []
  const nameError = editing ? validateRequired(editing.name, 'Name') : ''

  const save = async () => {
    setAttempted(true)
    if (!editing || nameError) return
    await saveMasterItem(type, { id: editing.id, name: editing.name.trim(), synonyms: editing.synonyms.trim() })
    toast.success(editing.id ? 'Updated' : 'Added')
    setEditing(null)
    setAttempted(false)
    reload()
  }

  const importCsv = async (file: File | undefined) => {
    if (!file) return
    if (!file.name.toLowerCase().endsWith('.csv')) {
      toast.error('Please choose a .csv file')
      return
    }
    const rows = parseCsv(await file.text())
    const names = rows.map((row) => row[0]).filter((name) => name && name.toLowerCase() !== 'name')
    const added = await importMasterItems(type, names)
    toast.success(`${added} item(s) imported`)
    reload()
  }

  return (
    <div>
      <PageHeader
        title="Master data"
        actions={
          <>
            <button type="button" className="btn-outline" onClick={() => fileInput.current?.click()}>
              <Upload className="h-4 w-4" />
              Import CSV
            </button>
            <input ref={fileInput} type="file" accept=".csv" className="sr-only" aria-label="Import CSV file" onChange={(event) => { importCsv(event.target.files?.[0]); event.target.value = '' }} />
            <button type="button" className="btn-primary" onClick={() => setEditing({ name: '', synonyms: '' })}>
              <Plus className="h-4 w-4" />
              Add
            </button>
          </>
        }
      />
      <Tabs active={type} onChange={(next) => { setType(next); setPage(1); setSearch('') }} tabs={TYPES} />
      <input className="input my-4 max-w-sm" type="search" aria-label="Search master data" placeholder="Search…" value={search} onChange={(event) => { setSearch(event.target.value); setPage(1) }} />

      {loading && <Skeleton className="h-48 w-full" />}
      {error && <ErrorState message={error} onRetry={reload} />}
      {!loading && items.length === 0 && <EmptyState title="No entries found" />}
      {items.length > 0 && (
        <div className="card overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="border-b border-line text-xs uppercase text-muted">
              <tr>
                <th className="p-3">Name</th>
                {type === 'skills' && <th>Synonyms</th>}
                <th className="pr-3 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {items.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE).map((item) => (
                <tr key={item.id}>
                  <td className="p-3 font-medium">{item.name}</td>
                  {type === 'skills' && <td className="text-muted">{item.synonyms || '—'}</td>}
                  <td className="pr-3 text-right">
                    <button type="button" aria-label={`Edit ${item.name}`} className="rounded p-2 hover:bg-soft" onClick={() => setEditing({ id: item.id, name: item.name, synonyms: item.synonyms ?? '' })}>
                      <Pencil className="h-4 w-4" />
                    </button>
                    <button type="button" aria-label={`Delete ${item.name}`} className="rounded p-2 text-danger hover:bg-soft" onClick={() => setDeleting(item)}>
                      <Trash2 className="h-4 w-4" />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <Pagination page={page} pageSize={PAGE_SIZE} total={items.length} onChange={setPage} />

      <Modal open={editing !== null} title={editing?.id ? 'Edit entry' : 'Add entry'} onClose={() => { setEditing(null); setAttempted(false) }}>
        <form
          noValidate
          className="space-y-4"
          onSubmit={(event) => {
            event.preventDefault()
            save()
          }}
        >
          <TextField label="Name" required value={editing?.name ?? ''} error={attempted ? nameError : ''} onChange={(event) => setEditing(editing ? { ...editing, name: event.target.value } : editing)} />
          {type === 'skills' && <TextField label="Synonyms" value={editing?.synonyms ?? ''} help="Comma separated, e.g. JS, ECMAScript" onChange={(event) => setEditing(editing ? { ...editing, synonyms: event.target.value } : editing)} />}
          <div className="flex justify-end gap-3">
            <button type="button" className="btn-outline" onClick={() => setEditing(null)}>Cancel</button>
            <button type="submit" className="btn-primary" disabled={attempted && Boolean(nameError)}>Save</button>
          </div>
        </form>
      </Modal>

      <ConfirmDialog
        open={Boolean(deleting)}
        danger
        title="Delete entry?"
        message={`"${deleting?.name ?? ''}" will be removed from master data.`}
        confirmLabel="Delete"
        onCancel={() => setDeleting(null)}
        onConfirm={async () => {
          if (deleting) await deleteMasterItem(type, deleting.id)
          toast.success('Deleted')
          setDeleting(null)
          reload()
        }}
      />
    </div>
  )
}
