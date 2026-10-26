import { useEffect, useState } from 'react'
import toast from 'react-hot-toast'
import { SelectField } from '../components/fields'
import { ErrorState, PageHeader, Skeleton, Toggle } from '../components/ui'
import { getNotificationPrefs, saveNotificationPrefs } from '../data/store'
import { useAsync, useSeo, useUnsavedWarning } from '../hooks'
import type { NotificationPrefs } from '../types'

const CHANNELS: { key: 'email' | 'sms' | 'inApp'; label: string }[] = [
  { key: 'email', label: 'Email' },
  { key: 'sms', label: 'SMS' },
  { key: 'inApp', label: 'In-app' },
]

const TOPICS: { key: 'jobAlerts' | 'applicationUpdates' | 'messages'; label: string }[] = [
  { key: 'jobAlerts', label: 'Job alerts and recommendations' },
  { key: 'applicationUpdates', label: 'Application status updates' },
  { key: 'messages', label: 'New messages from recruiters' },
]

export function NotificationPreferences() {
  const { data, loading, error, reload } = useAsync(() => getNotificationPrefs(), [])
  const [prefs, setPrefs] = useState<NotificationPrefs | null>(null)
  const [dirty, setDirty] = useState(false)
  const [saving, setSaving] = useState(false)
  useSeo('Notification preferences', 'Choose how you want to be notified.')
  useUnsavedWarning(dirty)

  useEffect(() => {
    if (data) setPrefs(data)
  }, [data])

  const update = (patch: Partial<NotificationPrefs>) => {
    setPrefs((current) => (current ? { ...current, ...patch } : current))
    setDirty(true)
  }

  if (loading || !prefs) return error ? <ErrorState message={error} onRetry={reload} /> : <Skeleton className="h-64 w-full" />

  return (
    <div className="max-w-2xl">
      <PageHeader title="Notification preferences" subtitle="Control which updates reach you and where." />
      <div className="card space-y-6 p-6">
        <section>
          <h2 className="mb-3 font-bold">Channels</h2>
          {CHANNELS.map((channel) => (
            <div key={channel.key} className="flex items-center justify-between py-2">
              <span>{channel.label}</span>
              <Toggle label={`${channel.label} notifications`} checked={prefs[channel.key]} onChange={(value) => update({ [channel.key]: value })} />
            </div>
          ))}
        </section>
        <section>
          <h2 className="mb-3 font-bold">What to notify me about</h2>
          {TOPICS.map((topic) => (
            <div key={topic.key} className="flex items-center justify-between py-2">
              <span>{topic.label}</span>
              <Toggle label={topic.label} checked={prefs[topic.key]} onChange={(value) => update({ [topic.key]: value })} />
            </div>
          ))}
        </section>
        <SelectField
          label="Email frequency"
          value={prefs.frequency}
          options={[{ value: 'INSTANT', label: 'Instant' }, { value: 'DAILY', label: 'Daily digest' }, { value: 'WEEKLY', label: 'Weekly digest' }]}
          onChange={(event) => update({ frequency: event.target.value as NotificationPrefs['frequency'] })}
        />
        <button
          type="button"
          className="btn-primary"
          disabled={saving || !dirty}
          onClick={async () => {
            setSaving(true)
            try {
              await saveNotificationPrefs(prefs)
              toast.success('Preferences saved')
              setDirty(false)
            } catch {
              // API client shows the error toast
            } finally {
              setSaving(false)
            }
          }}
        >
          {saving ? 'Saving…' : 'Save preferences'}
        </button>
      </div>
    </div>
  )
}
