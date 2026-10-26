import { useEffect, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { Check, Plus, Trash2 } from 'lucide-react'
import toast from 'react-hot-toast'
import { FormAlert } from '../components/AuthCard'
import { ChipInput, SelectField, SuggestInput, TextField } from '../components/fields'
import { RichTextEditor } from '../components/RichTextEditor'
import { Skeleton } from '../components/ui'
import { autosaveDraft, clearAutosavedDraft, getRecruiterCompany, getRecruiterJob, jobToDraft, loadAutosavedDraft, saveRecruiterJob } from '../data/store'
import { EDUCATION_LEVELS, EMPLOYMENT_TYPES, JOB_TYPES, WORK_MODES } from '../constants'
import { useAsync, useSeo, useUnsavedWarning } from '../hooks'
import type { NormalizedError } from '../api/client'
import type { PostJobDraft, ScreeningQuestion } from '../types'
import { formatExperience, formatSalary } from '../utils/format'
import { sanitizeHtml } from '../utils/sanitize'
import { EMPTY_DRAFT, POST_JOB_STEPS, validateAllSteps, validatePostJobStep } from '../validation/postJob'

export function PostJob() {
  const { id } = useParams()
  const navigate = useNavigate()
  const existing = useAsync(() => (id ? getRecruiterJob(id) : Promise.resolve(undefined)), [id])
  const company = useAsync(() => getRecruiterCompany(), [])
  const [draft, setDraft] = useState<PostJobDraft>(() => (id ? EMPTY_DRAFT : loadAutosavedDraft() ?? EMPTY_DRAFT))
  const [step, setStep] = useState(0)
  const [errors, setErrors] = useState<Record<string, string>>({})
  const [saving, setSaving] = useState(false)
  const [dirty, setDirty] = useState(false)
  const [serverError, setServerError] = useState('')
  const [autosavedAt, setAutosavedAt] = useState('')
  const loadedRef = useRef(false)
  useSeo(id ? 'Edit job' : 'Post a job', 'Create a job posting.')
  useUnsavedWarning(dirty)

  useEffect(() => {
    if (existing.data && !loadedRef.current) {
      loadedRef.current = true
      setDraft(jobToDraft(existing.data))
    }
  }, [existing.data])

  // Autosave the in-progress draft (new postings only)
  useEffect(() => {
    if (!dirty || id) return undefined
    const timer = setTimeout(() => {
      autosaveDraft(draft)
      setAutosavedAt(new Date().toLocaleTimeString())
    }, 800)
    return () => clearTimeout(timer)
  }, [draft, dirty, id])

  const change = (patch: Partial<PostJobDraft>) => {
    setDraft((current) => ({ ...current, ...patch }))
    setDirty(true)
  }

  const next = () => {
    const found = validatePostJobStep(draft, step)
    setErrors(found)
    if (Object.keys(found).length === 0) setStep((current) => Math.min(current + 1, POST_JOB_STEPS.length - 1))
  }

  const submit = async (publish: boolean) => {
    if (saving) return
    if (publish) {
      const failure = validateAllSteps(draft)
      if (failure) {
        setStep(failure.step)
        setErrors(failure.errors)
        toast.error('Please fix the highlighted fields')
        return
      }
    } else if (draft.title.trim().length < 3) {
      setStep(0)
      setErrors({ title: 'Add a job title before saving a draft' })
      return
    }
    setSaving(true)
    setServerError('')
    try {
      await saveRecruiterJob(draft, publish)
      clearAutosavedDraft()
      setDirty(false)
      toast.success(publish ? 'Job published' : 'Draft saved')
      navigate('/recruiter/jobs')
    } catch (caught) {
      setServerError((caught as NormalizedError).message)
      setErrors((caught as NormalizedError).fieldErrors ?? {})
    } finally {
      setSaving(false)
    }
  }

  const addQuestion = () => {
    const question: ScreeningQuestion = { id: `q${Date.now()}`, text: '', type: 'text', required: true }
    change({ screeningQuestions: [...draft.screeningQuestions, question] })
  }

  const updateQuestion = (questionId: string, patch: Partial<ScreeningQuestion>) =>
    change({ screeningQuestions: draft.screeningQuestions.map((question) => (question.id === questionId ? { ...question, ...patch } : question)) })

  if (id && existing.loading) return <Skeleton className="h-96 w-full" />

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-2xl font-bold">{id ? 'Edit job' : 'Post a job'}</h1>
        {company.data && company.data.status !== 'APPROVED' && (
          <p role="status" className="mt-2 rounded-lg bg-warning/10 p-3 text-sm">
            Your company is awaiting admin approval. You can save drafts, but publishing is restricted until approval.
          </p>
        )}
      </div>

      <ol className="flex items-center gap-1 overflow-x-auto" aria-label="Progress">
        {POST_JOB_STEPS.map((label, index) => (
          <li key={label} className="flex flex-1 items-center gap-2" aria-current={index === step ? 'step' : undefined}>
            <span className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-xs font-bold ${index < step ? 'bg-success text-white' : index === step ? 'bg-primary text-white' : 'bg-line text-muted'}`}>
              {index < step ? <Check className="h-4 w-4" /> : index + 1}
            </span>
            <span className={`hidden whitespace-nowrap text-xs font-semibold sm:inline ${index === step ? 'text-ink' : 'text-muted'}`}>{label}</span>
            {index < POST_JOB_STEPS.length - 1 && <span className="h-px flex-1 bg-line" />}
          </li>
        ))}
      </ol>

      <div className="card space-y-4 p-6">
        <FormAlert message={serverError} />

        {step === 0 && (
          <>
            <div className="space-y-1">
              <span className="block text-sm font-medium">Job title <span className="text-danger">*</span></span>
              <div className={`rounded-lg border bg-surface ${errors.title ? 'border-danger' : 'border-line'}`}>
                <SuggestInput type="job" label="Job title" placeholder="e.g. Senior React Developer" value={draft.title} onChange={(value) => change({ title: value })} />
              </div>
              {errors.title && <p className="text-xs text-danger" role="alert">{errors.title}</p>}
            </div>
            <ChipInput label="Locations" type="location" placeholder="Type a city" values={draft.locations} error={errors.locations} onChange={(values) => change({ locations: values })} />
            <div className="grid gap-4 sm:grid-cols-3">
              <SelectField label="Work mode" value={draft.workMode} options={WORK_MODES} onChange={(event) => change({ workMode: event.target.value })} />
              <SelectField label="Job type" value={draft.jobType} options={JOB_TYPES} onChange={(event) => change({ jobType: event.target.value })} />
              <SelectField label="Employment type" value={draft.employmentType} options={EMPLOYMENT_TYPES} onChange={(event) => change({ employmentType: event.target.value })} />
            </div>
            <TextField label="Number of openings" type="number" min={1} value={draft.openings} error={errors.openings} onChange={(event) => change({ openings: Number(event.target.value) })} />
          </>
        )}

        {step === 1 && (
          <>
            <div className="grid gap-4 sm:grid-cols-2">
              <TextField label="Minimum experience (years)" type="number" min={0} value={draft.experienceMin} error={errors.experienceMin} onChange={(event) => change({ experienceMin: Number(event.target.value) })} />
              <TextField label="Maximum experience (years)" type="number" min={0} value={draft.experienceMax} error={errors.experienceMax} onChange={(event) => change({ experienceMax: Number(event.target.value) })} />
            </div>
            <ChipInput label="Key skills" type="skill" placeholder="Type to search skills" values={draft.skills} error={errors.skills} onChange={(values) => change({ skills: values })} />
            <SelectField label="Education" value={draft.education} options={EDUCATION_LEVELS} onChange={(event) => change({ education: event.target.value })} />
          </>
        )}

        {step === 2 && (
          <>
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" className="h-4 w-4 accent-primary" checked={!draft.salaryDisclosed} onChange={(event) => change({ salaryDisclosed: !event.target.checked })} />
              Do not disclose salary
            </label>
            {draft.salaryDisclosed && (
              <div className="grid gap-4 sm:grid-cols-3">
                <SelectField label="Currency" value={draft.currency} options={['INR', 'USD']} onChange={(event) => change({ currency: event.target.value })} />
                <TextField label="Minimum (Lacs PA)" type="number" min={0} value={draft.salaryMin || ''} error={errors.salaryMin} onChange={(event) => change({ salaryMin: Number(event.target.value) })} />
                <TextField label="Maximum (Lacs PA)" type="number" min={0} value={draft.salaryMax || ''} error={errors.salaryMax} onChange={(event) => change({ salaryMax: Number(event.target.value) })} />
              </div>
            )}
          </>
        )}

        {step === 3 && <RichTextEditor value={draft.description} error={errors.description} onChange={(html) => change({ description: html })} />}

        {step === 4 && (
          <div className="space-y-4">
            <p className="text-sm text-muted">Optional questions candidates answer when applying. Without questions, candidates can quick-apply.</p>
            {draft.screeningQuestions.map((question, index) => (
              <div key={question.id} className="space-y-3 rounded-lg border border-line p-4">
                <div className="flex items-start gap-2">
                  <div className="flex-1">
                    <TextField label={`Question ${index + 1}`} value={question.text} error={errors[`question-${question.id}`]} onChange={(event) => updateQuestion(question.id, { text: event.target.value })} />
                  </div>
                  <button type="button" aria-label={`Remove question ${index + 1}`} className="mt-6 rounded p-2 text-danger hover:bg-soft" onClick={() => change({ screeningQuestions: draft.screeningQuestions.filter((entry) => entry.id !== question.id) })}>
                    <Trash2 className="h-4 w-4" />
                  </button>
                </div>
                <div className="grid gap-3 sm:grid-cols-2">
                  <SelectField label="Type" value={question.type} options={[{ value: 'text', label: 'Text' }, { value: 'yesno', label: 'Yes / No' }, { value: 'choice', label: 'Multiple choice' }]} onChange={(event) => updateQuestion(question.id, { type: event.target.value as ScreeningQuestion['type'], options: event.target.value === 'choice' ? ['', ''] : undefined })} />
                  <label className="flex items-center gap-2 pt-6 text-sm">
                    <input type="checkbox" className="h-4 w-4 accent-primary" checked={question.required} onChange={(event) => updateQuestion(question.id, { required: event.target.checked })} />
                    Required
                  </label>
                </div>
                {question.type === 'choice' && (
                  <TextField label="Options" value={(question.options ?? []).join(', ')} help="Comma separated, at least two" error={errors[`options-${question.id}`]} onChange={(event) => updateQuestion(question.id, { options: event.target.value.split(',').map((option) => option.trim()) })} />
                )}
              </div>
            ))}
            <button type="button" className="btn-outline" onClick={addQuestion}>
              <Plus className="h-4 w-4" />
              Add question
            </button>
          </div>
        )}

        {step === 5 && (
          <div className="space-y-3">
            <h2 className="text-lg font-bold">Preview — how candidates will see this job</h2>
            <div className="rounded-xl border border-line p-5">
              <h3 className="text-xl font-bold">{draft.title || 'Untitled job'}</h3>
              <p className="text-sm text-muted">{company.data?.name}</p>
              <p className="mt-2 text-sm text-muted">
                {formatExperience(draft.experienceMin, draft.experienceMax)} · {formatSalary(draft.salaryMin, draft.salaryMax, draft.salaryDisclosed)} · {draft.locations.join(', ')} · {draft.workMode}
              </p>
              <div className="mt-3 flex flex-wrap gap-2">
                {draft.skills.map((skill) => <span key={skill} className="chip">{skill}</span>)}
              </div>
              <div className="mt-4 text-sm text-muted" dangerouslySetInnerHTML={{ __html: sanitizeHtml(draft.description) }} />
              <p className="mt-4 text-xs text-muted">{draft.screeningQuestions.length} screening question(s) · {draft.openings} opening(s) · {draft.jobType} · {draft.employmentType}</p>
            </div>
          </div>
        )}
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <button type="button" className="btn-outline" disabled={step === 0} onClick={() => { setErrors({}); setStep(step - 1) }}>
          Back
        </button>
        {step < POST_JOB_STEPS.length - 1 ? (
          <button type="button" className="btn-primary" onClick={next}>Next</button>
        ) : (
          <button type="button" className="btn-accent" disabled={saving} onClick={() => submit(true)}>
            {saving ? 'Publishing…' : 'Publish job'}
          </button>
        )}
        <button type="button" className="btn-outline" disabled={saving} onClick={() => submit(false)}>Save as draft</button>
        {autosavedAt && <span className="text-xs text-muted">Draft autosaved at {autosavedAt}</span>}
      </div>
    </div>
  )
}
