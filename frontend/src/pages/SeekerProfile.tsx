import { useRef, useState } from 'react'
import { Camera, Pencil, Plus, Trash2 } from 'lucide-react'
import toast from 'react-hot-toast'
import { ChipInput, SelectField, TextAreaField, TextField } from '../components/fields'
import { PhotoCropper } from '../components/PhotoCropper'
import { ResumeManager } from '../components/ResumeManager'
import { ConfirmDialog, ErrorState, Modal, PageHeader, Skeleton } from '../components/ui'
import { getProfile, updateProfile, uploadProfilePhoto } from '../data/store'
import { EMPLOYMENT_TYPES, JOB_TYPES, NOTICE_PERIODS } from '../constants'
import { useAsync, useSeo, useUnsavedWarning } from '../hooks'
import type { Profile, ProfileItem } from '../types'
import { validateRequired } from '../validation'

type ItemSectionKey = 'employments' | 'educations' | 'projects' | 'certifications' | 'languages' | 'onlineProfiles'

const ITEM_SECTIONS: { key: ItemSectionKey; title: string; labels: [string, string, string?]; withDescription: boolean }[] = [
  { key: 'employments', title: 'Employment history', labels: ['Designation', 'Company', 'Period (e.g. 2021 - Present)'], withDescription: true },
  { key: 'educations', title: 'Education', labels: ['Degree', 'Institute', 'Period (e.g. 2017 - 2021)'], withDescription: false },
  { key: 'projects', title: 'Projects', labels: ['Project name', 'Client / link', 'Period'], withDescription: true },
  { key: 'certifications', title: 'Certifications', labels: ['Certification', 'Issued by', 'Year'], withDescription: false },
  { key: 'languages', title: 'Languages', labels: ['Language', 'Proficiency'], withDescription: false },
  { key: 'onlineProfiles', title: 'Online profiles', labels: ['Platform', 'Profile URL'], withDescription: false },
]

function SectionCard({ title, onEdit, onAdd, children }: { title: string; onEdit?: () => void; onAdd?: () => void; children: React.ReactNode }) {
  return (
    <section className="card p-5" aria-label={title}>
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-lg font-bold">{title}</h2>
        <div className="flex gap-1">
          {onAdd && (
            <button type="button" aria-label={`Add to ${title}`} className="rounded p-2 text-primary hover:bg-soft" onClick={onAdd}>
              <Plus className="h-4 w-4" />
            </button>
          )}
          {onEdit && (
            <button type="button" aria-label={`Edit ${title}`} className="rounded p-2 text-primary hover:bg-soft" onClick={onEdit}>
              <Pencil className="h-4 w-4" />
            </button>
          )}
        </div>
      </div>
      {children}
    </section>
  )
}

function ItemModal({
  config,
  item,
  onClose,
  onSave,
}: {
  config: (typeof ITEM_SECTIONS)[number]
  item: ProfileItem | null
  onClose: () => void
  onSave: (item: ProfileItem) => void
}) {
  const [draft, setDraft] = useState<ProfileItem>(item ?? { id: '', title: '', subtitle: '', period: '', description: '' })
  const [attempted, setAttempted] = useState(false)
  const titleError = validateRequired(draft.title, config.labels[0])
  const subtitleError = validateRequired(draft.subtitle, config.labels[1])
  const isValid = !titleError && !subtitleError
  useUnsavedWarning(JSON.stringify(draft) !== JSON.stringify(item ?? {}))

  return (
    <Modal open title={`${item ? 'Edit' : 'Add'} ${config.title.toLowerCase()}`} onClose={onClose}>
      <form
        noValidate
        className="space-y-4"
        onSubmit={(event) => {
          event.preventDefault()
          setAttempted(true)
          if (isValid) onSave(draft)
        }}
      >
        <TextField label={config.labels[0]} required value={draft.title} error={attempted ? titleError : ''} onChange={(event) => setDraft({ ...draft, title: event.target.value })} />
        <TextField label={config.labels[1]} required value={draft.subtitle} error={attempted ? subtitleError : ''} onChange={(event) => setDraft({ ...draft, subtitle: event.target.value })} />
        {config.labels[2] && <TextField label={config.labels[2]} value={draft.period} onChange={(event) => setDraft({ ...draft, period: event.target.value })} />}
        {config.withDescription && <TextAreaField label="Description" value={draft.description} onChange={(event) => setDraft({ ...draft, description: event.target.value })} />}
        <div className="flex justify-end gap-3">
          <button type="button" className="btn-outline" onClick={onClose}>
            Cancel
          </button>
          <button type="submit" className="btn-primary" disabled={attempted && !isValid}>
            Save
          </button>
        </div>
      </form>
    </Modal>
  )
}

export function SeekerProfile() {
  const { data, loading, error, reload } = useAsync(() => getProfile(), [])
  const [editing, setEditing] = useState<null | 'headline' | 'skills' | 'personal' | 'career'>(null)
  const [itemEdit, setItemEdit] = useState<{ key: ItemSectionKey; item: ProfileItem | null } | null>(null)
  const [itemDelete, setItemDelete] = useState<{ key: ItemSectionKey; id: string } | null>(null)
  const [headline, setHeadline] = useState('')
  const [skills, setSkills] = useState<string[]>([])
  const [personal, setPersonal] = useState<Profile['personal'] | null>(null)
  const [career, setCareer] = useState<Profile['career'] | null>(null)
  const [photoFile, setPhotoFile] = useState<File | null>(null)
  const [saving, setSaving] = useState(false)
  const photoInput = useRef<HTMLInputElement>(null)
  useSeo('My profile', 'Edit your JobHub profile, skills and resume.')
  useUnsavedWarning(editing !== null)

  const save = async (patch: Partial<Profile>, message = 'Profile updated') => {
    setSaving(true)
    try {
      await updateProfile(patch)
      toast.success(message)
      setEditing(null)
      setItemEdit(null)
      reload()
    } catch {
      // API client shows the error toast
    } finally {
      setSaving(false)
    }
  }

  if (loading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-32 w-full" />
        <Skeleton className="h-40 w-full" />
      </div>
    )
  }
  if (error || !data) return <ErrorState message={error || 'Profile not found'} onRetry={reload} />
  const profile = data

  const upsertItem = (key: ItemSectionKey, item: ProfileItem) => {
    const list = profile[key]
    const next = item.id ? list.map((entry) => (entry.id === item.id ? item : entry)) : [...list, { ...item, id: `${key}-${Date.now()}` }]
    save({ [key]: next } as Partial<Profile>, 'Saved')
  }

  const headlineError = validateRequired(headline, 'Headline')

  return (
    <div className="space-y-5">
      <PageHeader title="My profile" subtitle="A complete profile gets up to 3x more recruiter views." />

      <section className="card flex flex-wrap items-center gap-5 p-5">
        <div className="relative">
          {profile.photoUrl ? (
            <img src={profile.photoUrl} alt="Your profile" className="h-24 w-24 rounded-full object-cover" />
          ) : (
            <div className="flex h-24 w-24 items-center justify-center rounded-full bg-soft text-3xl font-bold text-primary">{profile.name.slice(0, 1)}</div>
          )}
          <button type="button" aria-label="Upload profile photo" className="absolute -bottom-1 -right-1 rounded-full bg-primary p-2 text-white" onClick={() => photoInput.current?.click()}>
            <Camera className="h-4 w-4" />
          </button>
          <input
            ref={photoInput}
            type="file"
            accept="image/*"
            className="sr-only"
            aria-label="Choose profile photo"
            onChange={(event) => {
              const file = event.target.files?.[0]
              if (file && file.type.startsWith('image/')) setPhotoFile(file)
              else if (file) toast.error('Please choose an image file')
              event.target.value = ''
            }}
          />
        </div>
        <div className="min-w-0 flex-1">
          <h2 className="text-xl font-bold">{profile.name}</h2>
          <p className="text-sm text-muted">{profile.headline || 'Add a resume headline'}</p>
          <p className="text-sm text-muted">{profile.personal.location}</p>
        </div>
      </section>

      <SectionCard
        title="Resume headline"
        onEdit={() => {
          setHeadline(profile.headline)
          setEditing('headline')
        }}
      >
        <p className="text-sm text-muted">{profile.headline || 'Add a short headline that summarises your profile.'}</p>
      </SectionCard>

      <SectionCard
        title="Key skills"
        onEdit={() => {
          setSkills(profile.skills)
          setEditing('skills')
        }}
      >
        <div className="flex flex-wrap gap-2">
          {profile.skills.map((skill) => (
            <span key={skill} className="chip">{skill}</span>
          ))}
          {profile.skills.length === 0 && <p className="text-sm text-muted">Add skills to get better job matches.</p>}
        </div>
      </SectionCard>

      {ITEM_SECTIONS.map((section) => (
        <SectionCard key={section.key} title={section.title} onAdd={() => setItemEdit({ key: section.key, item: null })}>
          <ul className="space-y-3">
            {profile[section.key].map((item) => (
              <li key={item.id} className="flex items-start justify-between gap-3 border-b border-line pb-3 last:border-0 last:pb-0">
                <div>
                  <p className="font-semibold">{item.title}</p>
                  <p className="text-sm text-muted">
                    {item.subtitle}
                    {item.period && ` · ${item.period}`}
                  </p>
                  {item.description && <p className="mt-1 text-sm text-muted">{item.description}</p>}
                </div>
                <div className="flex shrink-0">
                  <button type="button" aria-label={`Edit ${item.title}`} className="rounded p-2 hover:bg-soft" onClick={() => setItemEdit({ key: section.key, item })}>
                    <Pencil className="h-4 w-4" />
                  </button>
                  <button type="button" aria-label={`Remove ${item.title}`} className="rounded p-2 text-danger hover:bg-soft" onClick={() => setItemDelete({ key: section.key, id: item.id })}>
                    <Trash2 className="h-4 w-4" />
                  </button>
                </div>
              </li>
            ))}
            {profile[section.key].length === 0 && <li className="text-sm text-muted">Nothing added yet.</li>}
          </ul>
        </SectionCard>
      ))}

      <SectionCard
        title="Personal details"
        onEdit={() => {
          setPersonal(profile.personal)
          setEditing('personal')
        }}
      >
        <dl className="grid grid-cols-2 gap-3 text-sm">
          <div><dt className="text-muted">Date of birth</dt><dd>{profile.personal.dob || '—'}</dd></div>
          <div><dt className="text-muted">Gender</dt><dd>{profile.personal.gender || '—'}</dd></div>
          <div><dt className="text-muted">Location</dt><dd>{profile.personal.location || '—'}</dd></div>
          <div><dt className="text-muted">Marital status</dt><dd>{profile.personal.maritalStatus || '—'}</dd></div>
        </dl>
      </SectionCard>

      <SectionCard
        title="Career profile & preferences"
        onEdit={() => {
          setCareer(profile.career)
          setEditing('career')
        }}
      >
        <dl className="grid grid-cols-2 gap-3 text-sm">
          <div><dt className="text-muted">Preferred locations</dt><dd>{profile.career.preferredLocations || '—'}</dd></div>
          <div><dt className="text-muted">Expected salary</dt><dd>{profile.career.expectedSalary || '—'}</dd></div>
          <div><dt className="text-muted">Job type</dt><dd>{profile.career.jobType || '—'}</dd></div>
          <div><dt className="text-muted">Employment type</dt><dd>{profile.career.employmentType || '—'}</dd></div>
          <div><dt className="text-muted">Industry</dt><dd>{profile.career.industry || '—'}</dd></div>
          <div><dt className="text-muted">Notice period</dt><dd>{profile.career.noticePeriod || '—'}</dd></div>
        </dl>
      </SectionCard>

      <ResumeManager onChange={reload} />

      <PhotoCropper
        file={photoFile}
        onCancel={() => setPhotoFile(null)}
        onSave={async (dataUrl) => {
          await uploadProfilePhoto(dataUrl)
          setPhotoFile(null)
          toast.success('Profile photo updated')
          reload()
        }}
      />

      <Modal open={editing === 'headline'} title="Resume headline" onClose={() => setEditing(null)}>
        <form
          noValidate
          className="space-y-4"
          onSubmit={(event) => {
            event.preventDefault()
            if (!headlineError) save({ headline: headline.trim() })
          }}
        >
          <TextAreaField label="Headline" required rows={3} maxLength={250} value={headline} help="Up to 250 characters" error={headlineError && headline !== profile.headline ? headlineError : ''} onChange={(event) => setHeadline(event.target.value)} />
          <div className="flex justify-end gap-3">
            <button type="button" className="btn-outline" onClick={() => setEditing(null)}>Cancel</button>
            <button type="submit" className="btn-primary" disabled={Boolean(headlineError) || saving}>Save</button>
          </div>
        </form>
      </Modal>

      <Modal open={editing === 'skills'} title="Key skills" onClose={() => setEditing(null)}>
        <div className="space-y-4">
          <ChipInput label="Skills" type="skill" values={skills} onChange={setSkills} placeholder="Type to search skills" />
          <div className="flex justify-end gap-3">
            <button type="button" className="btn-outline" onClick={() => setEditing(null)}>Cancel</button>
            <button type="button" className="btn-primary" disabled={saving} onClick={() => save({ skills })}>Save</button>
          </div>
        </div>
      </Modal>

      <Modal open={editing === 'personal' && Boolean(personal)} title="Personal details" onClose={() => setEditing(null)}>
        {personal && (
          <form
            className="space-y-4"
            onSubmit={(event) => {
              event.preventDefault()
              save({ personal })
            }}
          >
            <TextField label="Date of birth" type="date" value={personal.dob} onChange={(event) => setPersonal({ ...personal, dob: event.target.value })} />
            <SelectField label="Gender" value={personal.gender} placeholder="Select" options={['Female', 'Male', 'Other']} onChange={(event) => setPersonal({ ...personal, gender: event.target.value })} />
            <TextField label="Location" value={personal.location} onChange={(event) => setPersonal({ ...personal, location: event.target.value })} />
            <SelectField label="Marital status" value={personal.maritalStatus} placeholder="Select" options={['Single', 'Married']} onChange={(event) => setPersonal({ ...personal, maritalStatus: event.target.value })} />
            <div className="flex justify-end gap-3">
              <button type="button" className="btn-outline" onClick={() => setEditing(null)}>Cancel</button>
              <button type="submit" className="btn-primary" disabled={saving}>Save</button>
            </div>
          </form>
        )}
      </Modal>

      <Modal open={editing === 'career' && Boolean(career)} title="Career profile & preferences" onClose={() => setEditing(null)}>
        {career && (
          <form
            className="space-y-4"
            onSubmit={(event) => {
              event.preventDefault()
              save({ career })
            }}
          >
            <TextField label="Preferred locations" value={career.preferredLocations} onChange={(event) => setCareer({ ...career, preferredLocations: event.target.value })} />
            <TextField label="Expected salary" value={career.expectedSalary} help="e.g. 12-18 Lacs PA" onChange={(event) => setCareer({ ...career, expectedSalary: event.target.value })} />
            <SelectField label="Job type" value={career.jobType} placeholder="Select" options={JOB_TYPES} onChange={(event) => setCareer({ ...career, jobType: event.target.value })} />
            <SelectField label="Employment type" value={career.employmentType} placeholder="Select" options={EMPLOYMENT_TYPES} onChange={(event) => setCareer({ ...career, employmentType: event.target.value })} />
            <TextField label="Industry" value={career.industry} onChange={(event) => setCareer({ ...career, industry: event.target.value })} />
            <SelectField label="Notice period" value={career.noticePeriod} placeholder="Select" options={NOTICE_PERIODS} onChange={(event) => setCareer({ ...career, noticePeriod: event.target.value })} />
            <div className="flex justify-end gap-3">
              <button type="button" className="btn-outline" onClick={() => setEditing(null)}>Cancel</button>
              <button type="submit" className="btn-primary" disabled={saving}>Save</button>
            </div>
          </form>
        )}
      </Modal>

      {itemEdit && (
        <ItemModal
          config={ITEM_SECTIONS.find((section) => section.key === itemEdit.key)!}
          item={itemEdit.item}
          onClose={() => setItemEdit(null)}
          onSave={(item) => upsertItem(itemEdit.key, item)}
        />
      )}

      <ConfirmDialog
        open={Boolean(itemDelete)}
        danger
        title="Remove this entry?"
        message="This will be removed from your profile."
        confirmLabel="Remove"
        onCancel={() => setItemDelete(null)}
        onConfirm={() => {
          if (itemDelete) save({ [itemDelete.key]: profile[itemDelete.key].filter((entry) => entry.id !== itemDelete.id) } as Partial<Profile>, 'Removed')
          setItemDelete(null)
        }}
      />
    </div>
  )
}
