import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { Hourglass, ImagePlus, Plus, X, XCircle } from 'lucide-react'
import toast from 'react-hot-toast'
import { SelectField, TextAreaField, TextField } from '../components/fields'
import { CompanyLogo, ErrorState, PageHeader, Skeleton } from '../components/ui'
import { getMasterList, getRecruiterCompany, updateRecruiterCompany } from '../data/store'
import { useAsync, useSeo, useUnsavedWarning } from '../hooks'
import type { Company } from '../types'
import { isImageFile, readFileAsDataUrl } from '../utils/files'
import { validateMinLength, validateRequired } from '../validation'

export function CompanyProfileEditor() {
  const { data, loading, error, reload } = useAsync(() => getRecruiterCompany(), [])
  const industries = useAsync(() => getMasterList('industries'), [])
  const [form, setForm] = useState<Company | null>(null)
  const [benefit, setBenefit] = useState('')
  const [imageError, setImageError] = useState('')
  const [attempted, setAttempted] = useState(false)
  const [saving, setSaving] = useState(false)
  const [dirty, setDirty] = useState(false)
  useSeo('Company profile', 'Edit your company profile.')
  useUnsavedWarning(dirty)

  useEffect(() => {
    if (data) setForm(data)
  }, [data])

  if (loading || !form) return error ? <ErrorState message={error} onRetry={reload} /> : <Skeleton className="h-96 w-full" />

  const change = (patch: Partial<Company>) => {
    setForm({ ...form, ...patch })
    setDirty(true)
  }

  const pickImage = async (file: File | undefined, apply: (url: string) => void) => {
    if (!file) return
    const problem = isImageFile(file)
    setImageError(problem)
    if (!problem) apply(await readFileAsDataUrl(file))
  }

  const errors = {
    name: validateRequired(form.name, 'Company name'),
    about: validateMinLength(form.about, 20, 'About'),
  }
  const isValid = !errors.name && !errors.about

  const save = async (event: FormEvent) => {
    event.preventDefault()
    setAttempted(true)
    if (!isValid || saving) return
    setSaving(true)
    try {
      await updateRecruiterCompany(form)
      toast.success('Company profile saved')
      setDirty(false)
    } catch {
      // API client shows the error toast
    } finally {
      setSaving(false)
    }
  }

  return (
    <form onSubmit={save} noValidate className="space-y-5">
      <PageHeader
        title="Company profile"
        subtitle="This is how candidates see your company."
        actions={<Link to="/recruiter/team" className="btn-outline">Manage team</Link>}
      />
      {form.status === 'PENDING' && (
        <div role="status" className="flex items-center gap-3 rounded-lg border border-warning/50 bg-warning/10 p-4 text-sm">
          <Hourglass className="h-5 w-5 text-warning" />
          Your company is awaiting admin approval. Posting jobs is restricted until it is approved.
        </div>
      )}
      {(form.status === 'REJECTED' || form.status === 'BLOCKED') && (
        <div role="alert" className="flex items-center gap-3 rounded-lg border border-danger/50 bg-danger/10 p-4 text-sm text-danger">
          <XCircle className="h-5 w-5" />
          Your company was {form.status.toLowerCase()} by the admin team. Contact support for details.
        </div>
      )}

      <section className="card space-y-4 p-5">
        <div className="relative h-36 overflow-hidden rounded-lg bg-soft">
          {form.bannerUrl && <img src={form.bannerUrl} alt="Company banner" className="h-full w-full object-cover" />}
          <label className="btn-outline absolute bottom-2 right-2 cursor-pointer">
            <ImagePlus className="h-4 w-4" />
            Banner
            <input type="file" accept="image/*" className="sr-only" aria-label="Upload banner" onChange={(event) => pickImage(event.target.files?.[0], (url) => change({ bannerUrl: url }))} />
          </label>
        </div>
        <div className="flex items-center gap-4">
          <CompanyLogo src={form.logoUrl} name={form.name} size="h-20 w-20" />
          <label className="btn-outline cursor-pointer">
            <ImagePlus className="h-4 w-4" />
            Upload logo
            <input type="file" accept="image/*" className="sr-only" aria-label="Upload logo" onChange={(event) => pickImage(event.target.files?.[0], (url) => change({ logoUrl: url }))} />
          </label>
        </div>
        {imageError && <p className="text-sm text-danger" role="alert">{imageError}</p>}
        <TextField label="Company name" required value={form.name} error={attempted ? errors.name : ''} onChange={(event) => change({ name: event.target.value })} />
        <div className="grid gap-4 sm:grid-cols-2">
          <SelectField label="Industry" value={form.industry} options={(industries.data ?? []).map((item) => item.name)} onChange={(event) => change({ industry: event.target.value })} />
          <TextField label="Headquarters" value={form.headquarters} onChange={(event) => change({ headquarters: event.target.value })} />
          <TextField label="Website" type="url" value={form.website} onChange={(event) => change({ website: event.target.value })} />
          <TextField label="Company size" value={form.size} onChange={(event) => change({ size: event.target.value })} />
        </div>
        <TextAreaField label="About the company" required rows={5} value={form.about} help="At least 20 characters" error={attempted ? errors.about : ''} onChange={(event) => change({ about: event.target.value })} />
      </section>

      <section className="card space-y-3 p-5">
        <h2 className="font-bold">Benefits</h2>
        <div className="flex flex-wrap gap-2">
          {form.benefits.map((item) => (
            <span key={item} className="chip">
              {item}
              <button type="button" aria-label={`Remove ${item}`} onClick={() => change({ benefits: form.benefits.filter((entry) => entry !== item) })}>
                <X className="h-3 w-3" />
              </button>
            </span>
          ))}
        </div>
        <div className="flex gap-2">
          <input className="input" aria-label="New benefit" placeholder="e.g. Free meals" value={benefit} onChange={(event) => setBenefit(event.target.value)} />
          <button
            type="button"
            className="btn-outline"
            disabled={!benefit.trim()}
            onClick={() => {
              change({ benefits: [...form.benefits, benefit.trim()] })
              setBenefit('')
            }}
          >
            <Plus className="h-4 w-4" />
            Add
          </button>
        </div>
      </section>

      <section className="card space-y-3 p-5">
        <h2 className="font-bold">Gallery</h2>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          {form.gallery.map((image, index) => (
            <div key={index} className="relative">
              <img src={image} alt={`Gallery ${index + 1}`} className="h-24 w-full rounded-lg object-cover" />
              <button type="button" aria-label={`Remove gallery image ${index + 1}`} className="absolute right-1 top-1 rounded-full bg-black/60 p-1 text-white" onClick={() => change({ gallery: form.gallery.filter((_, position) => position !== index) })}>
                <X className="h-3 w-3" />
              </button>
            </div>
          ))}
        </div>
        <label className="btn-outline cursor-pointer">
          <ImagePlus className="h-4 w-4" />
          Add images
          <input
            type="file"
            accept="image/*"
            multiple
            className="sr-only"
            aria-label="Upload gallery images"
            onChange={async (event) => {
              const files = Array.from(event.target.files ?? [])
              const urls: string[] = []
              for (const file of files) {
                const problem = isImageFile(file)
                setImageError(problem)
                if (!problem) urls.push(await readFileAsDataUrl(file))
              }
              if (urls.length) change({ gallery: [...form.gallery, ...urls] })
            }}
          />
        </label>
      </section>

      <button type="submit" className="btn-primary" disabled={saving || (attempted && !isValid)}>
        {saving ? 'Saving…' : 'Save company profile'}
      </button>
    </form>
  )
}
