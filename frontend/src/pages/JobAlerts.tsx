import { useState } from 'react'
import { BellOff, BellRing, Pause, Pencil, Play, Plus, Trash2 } from 'lucide-react'
import toast from 'react-hot-toast'
import { SelectField, TextField } from '../components/fields'
import { ConfirmDialog, EmptyState, ErrorState, Modal, PageHeader, Skeleton } from '../components/ui'
import { deleteAlert, getAlerts, saveAlert } from '../data/store'
import { useAsync, useSeo, useUnsavedWarning } from '../hooks'
import type { JobAlert } from '../types'
import { validateRequired } from '../validation'

const EMPTY_ALERT: Omit<JobAlert, 'id'> = { keywords: '', locations: '', experience: '', salary: '', frequency: 'DAILY', active: true }

export function JobAlerts() {
  const { data, loading, error, reload } = useAsync(() => getAlerts(), [])
  const [editing, setEditing] = useState<(Omit<JobAlert, 'id'> & { id?: string }) | null>(null)
  const [deleting, setDeleting] = useState<JobAlert | null>(null)
  const [attempted, setAttempted] = useState(false)
  const [saving, setSaving] = useState(false)
  useSeo('Job alerts', 'Manage your job alerts.')
  useUnsavedWarning(editing !== null)

  const keywordError = editing ? validateRequired(editing.keywords, 'Keywords') : ''
  const experienceError = editing && editing.experience && !/^\d+(-\d+)?$/.test(editing.experience) ? 'Use a number or a range like 2-5' : ''
  const isValid = !keywordError && !experienceError

  const save = async () => {
    setAttempted(true)
    if (!editing || !isValid || saving) return
    setSaving(true)
    try {
      await saveAlert(editing)
      toast.success(editing.id ? 'Alert updated' : 'Alert created')
      setEditing(null)
      setAttempted(false)
      reload()
    } catch {
      // API client shows the error toast
    } finally {
      setSaving(false)
    }
  }

  return (
    <div>
      <PageHeader
        title="Job alerts"
        subtitle="Get new matching jobs delivered to your inbox."
        actions={
          <button type="button" className="btn-primary" onClick={() => setEditing({ ...EMPTY_ALERT })}>
            <Plus className="h-4 w-4" />
            Create alert
          </button>
        }
      />
      {loading && <Skeleton className="h-32 w-full" />}
      {error && <ErrorState message={error} onRetry={reload} />}
      {data?.length === 0 && <EmptyState title="No job alerts" message="Create an alert to hear about new jobs first." />}
      <div className="space-y-3">
        {data?.map((alert) => (
          <article key={alert.id} className="card flex flex-wrap items-center gap-4 p-4">
            {alert.active ? <BellRing className="h-6 w-6 text-primary" /> : <BellOff className="h-6 w-6 text-muted" />}
            <div className="min-w-0 flex-1">
              <p className="font-bold">{alert.keywords}</p>
              <p className="text-sm text-muted">
                {alert.locations || 'Any location'} · {alert.experience ? `${alert.experience} yrs` : 'Any experience'} · {alert.salary ? `${alert.salary} Lacs+` : 'Any salary'} · {alert.frequency.toLowerCase()}
              </p>
            </div>
            <span className={`text-xs font-semibold ${alert.active ? 'text-success' : 'text-muted'}`}>{alert.active ? 'Active' : 'Paused'}</span>
            <button
              type="button"
              className="btn-outline"
              onClick={async () => {
                await saveAlert({ ...alert, active: !alert.active })
                toast.success(alert.active ? 'Alert paused' : 'Alert resumed')
                reload()
              }}
            >
              {alert.active ? <Pause className="h-4 w-4" /> : <Play className="h-4 w-4" />}
              {alert.active ? 'Pause' : 'Resume'}
            </button>
            <button type="button" aria-label={`Edit alert ${alert.keywords}`} className="rounded p-2 hover:bg-soft" onClick={() => setEditing(alert)}>
              <Pencil className="h-4 w-4" />
            </button>
            <button type="button" aria-label={`Delete alert ${alert.keywords}`} className="rounded p-2 text-danger hover:bg-soft" onClick={() => setDeleting(alert)}>
              <Trash2 className="h-4 w-4" />
            </button>
          </article>
        ))}
      </div>

      <Modal open={editing !== null} title={editing?.id ? 'Edit job alert' : 'Create job alert'} onClose={() => { setEditing(null); setAttempted(false) }}>
        {editing && (
          <form
            noValidate
            className="space-y-4"
            onSubmit={(event) => {
              event.preventDefault()
              save()
            }}
          >
            <TextField label="Keywords" required value={editing.keywords} error={attempted ? keywordError : ''} onChange={(event) => setEditing({ ...editing, keywords: event.target.value })} />
            <TextField label="Locations" value={editing.locations} help="Comma separated, e.g. Bengaluru, Remote" onChange={(event) => setEditing({ ...editing, locations: event.target.value })} />
            <TextField label="Experience (years)" value={editing.experience} help="A number or range, e.g. 2-5" error={attempted ? experienceError : ''} onChange={(event) => setEditing({ ...editing, experience: event.target.value })} />
            <TextField label="Minimum salary (Lacs PA)" type="number" min={0} value={editing.salary.replace('+', '')} onChange={(event) => setEditing({ ...editing, salary: event.target.value })} />
            <SelectField label="Frequency" value={editing.frequency} options={[{ value: 'INSTANT', label: 'Instant' }, { value: 'DAILY', label: 'Daily' }, { value: 'WEEKLY', label: 'Weekly' }]} onChange={(event) => setEditing({ ...editing, frequency: event.target.value as JobAlert['frequency'] })} />
            <div className="flex justify-end gap-3">
              <button type="button" className="btn-outline" onClick={() => setEditing(null)}>Cancel</button>
              <button type="submit" className="btn-primary" disabled={saving || (attempted && !isValid)}>
                {saving ? 'Saving…' : editing.id ? 'Update alert' : 'Save alert'}
              </button>
            </div>
          </form>
        )}
      </Modal>

      <ConfirmDialog
        open={Boolean(deleting)}
        danger
        title="Delete alert?"
        message={`You will stop receiving emails for "${deleting?.keywords ?? ''}".`}
        confirmLabel="Delete"
        onCancel={() => setDeleting(null)}
        onConfirm={async () => {
          if (deleting) await deleteAlert(deleting.id)
          setDeleting(null)
          toast.success('Alert deleted')
          reload()
        }}
      />
    </div>
  )
}
