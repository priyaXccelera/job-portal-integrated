import { useEffect, useState } from 'react'
import toast from 'react-hot-toast'
import { SelectField, TextAreaField } from '../components/fields'
import { Toggle, ErrorState, PageHeader, Skeleton } from '../components/ui'
import { getProfile, savePrivacy } from '../data/store'
import { useAsync, useSeo, useUnsavedWarning } from '../hooks'
import type { Profile } from '../types'

export function PrivacySettings() {
  const { data, loading, error, reload } = useAsync(() => getProfile(), [])
  const [visibility, setVisibility] = useState<Profile['visibility']>('PUBLIC')
  const [hideEnabled, setHideEnabled] = useState(false)
  const [hidden, setHidden] = useState('')
  const [saving, setSaving] = useState(false)
  const [dirty, setDirty] = useState(false)
  useSeo('Privacy settings', 'Control who can see your profile.')
  useUnsavedWarning(dirty)

  useEffect(() => {
    if (data) {
      setVisibility(data.visibility)
      setHidden(data.hideFromCompanies)
      setHideEnabled(Boolean(data.hideFromCompanies))
    }
  }, [data])

  const save = async () => {
    setSaving(true)
    try {
      await savePrivacy(visibility, hideEnabled ? hidden : '')
      toast.success('Privacy settings saved')
      setDirty(false)
    } catch {
      // API client shows the error toast
    } finally {
      setSaving(false)
    }
  }

  if (loading) return <Skeleton className="h-48 w-full" />
  if (error) return <ErrorState message={error} onRetry={reload} />

  return (
    <div className="max-w-2xl">
      <PageHeader title="Privacy settings" subtitle="Decide who can discover your profile." />
      <div className="card space-y-6 p-6">
        <SelectField
          label="Profile visibility"
          value={visibility}
          help="Public profiles appear in recruiter searches. Private profiles are only visible to you."
          options={[
            { value: 'PUBLIC', label: 'Visible to all recruiters' },
            { value: 'RECRUITERS_ONLY', label: 'Only recruiters I apply to' },
            { value: 'PRIVATE', label: 'Hidden (private)' },
          ]}
          onChange={(event) => {
            setVisibility(event.target.value as Profile['visibility'])
            setDirty(true)
          }}
        />
        <div className="flex items-center justify-between gap-4">
          <div>
            <p className="font-semibold">Hide profile from specific companies</p>
            <p className="text-sm text-muted">Useful to keep your job search confidential from your current employer.</p>
          </div>
          <Toggle
            label="Hide from companies"
            checked={hideEnabled}
            onChange={(value) => {
              setHideEnabled(value)
              setDirty(true)
            }}
          />
        </div>
        {hideEnabled && (
          <TextAreaField
            label="Companies to hide from"
            rows={2}
            value={hidden}
            help="Comma separated company names"
            onChange={(event) => {
              setHidden(event.target.value)
              setDirty(true)
            }}
          />
        )}
        <button type="button" className="btn-primary" disabled={saving || !dirty} onClick={save}>
          {saving ? 'Saving…' : 'Save changes'}
        </button>
      </div>
    </div>
  )
}
