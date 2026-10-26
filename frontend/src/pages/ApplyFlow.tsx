import { useState } from 'react'
import type { FormEvent } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { CheckCircle2 } from 'lucide-react'
import { FormAlert } from '../components/AuthCard'
import { JobCard, jobPath } from '../components/JobCard'
import { SelectField, TextAreaField, TextField } from '../components/fields'
import { Breadcrumbs, EmptyState, ErrorState, Skeleton } from '../components/ui'
import { applyToJob, getJob, getResumes, getSimilarJobs } from '../data/store'
import { NOTICE_PERIODS } from '../constants'
import { useAsync, useSeo, useUnsavedWarning } from '../hooks'
import type { NormalizedError } from '../api/client'
import { idFromSlug } from '../utils/format'

export function ApplyFlow() {
  const { slugId } = useParams()
  const jobId = idFromSlug(slugId)
  const navigate = useNavigate()
  const job = useAsync(() => getJob(jobId), [jobId])
  const resumes = useAsync(() => getResumes(), [])
  const similar = useAsync(() => getSimilarJobs(jobId), [jobId])
  const [resumeChoice, setResumeChoice] = useState('')
  const [coverNote, setCoverNote] = useState('')
  const [answers, setAnswers] = useState<Record<string, string>>({})
  const [expectedCtc, setExpectedCtc] = useState('')
  const [noticePeriod, setNoticePeriod] = useState('')
  const [attempted, setAttempted] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [done, setDone] = useState(false)
  const [serverError, setServerError] = useState('')
  useSeo('Apply', 'Submit your application.')
  useUnsavedWarning(Boolean(coverNote || expectedCtc || Object.keys(answers).length) && !done)

  if (job.loading || resumes.loading) return <div className="mx-auto max-w-2xl space-y-3 px-4 py-8"><Skeleton className="h-10 w-1/2" /><Skeleton className="h-64 w-full" /></div>
  if (job.error) return <div className="mx-auto max-w-2xl px-4 py-8"><ErrorState message={job.error} onRetry={job.reload} /></div>
  const current = job.data
  if (!current) return <div className="mx-auto max-w-2xl px-4 py-8"><EmptyState title="Job not found" /></div>

  const questions = current.screeningQuestions
  const isQuick = questions.length === 0
  const resumeList = resumes.data ?? []
  const selectedResume = resumeChoice || resumeList.find((resume) => resume.isDefault)?.id || ''

  const errors: Record<string, string> = {}
  if (!selectedResume) errors.resume = 'Choose a resume (upload one in your profile first)'
  questions.forEach((question) => {
    if (question.required && !(answers[question.id] ?? '').trim()) errors[question.id] = 'This question is required'
  })
  if (expectedCtc && !(Number(expectedCtc) > 0)) errors.ctc = 'Enter a valid amount in lakhs'
  if (!isQuick && !expectedCtc) errors.ctc = 'Expected CTC is required'
  if (!isQuick && !noticePeriod) errors.notice = 'Select your notice period'
  const isValid = Object.keys(errors).length === 0

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    setAttempted(true)
    if (!isValid || submitting) return
    setSubmitting(true)
    setServerError('')
    try {
      await applyToJob(current.id, {
        resumeId: selectedResume,
        coverNote: coverNote.trim(),
        answers: questions.map((question) => ({ questionId: question.id, answer: answers[question.id] ?? '' })),
        expectedCtc: expectedCtc ? Number(expectedCtc) : undefined,
        noticePeriod: noticePeriod || undefined,
      })
      setDone(true)
    } catch (caught) {
      setServerError((caught as NormalizedError).message)
    } finally {
      setSubmitting(false)
    }
  }

  if (done) {
    return (
      <div className="mx-auto max-w-3xl px-4 py-10">
        <div className="card flex flex-col items-center p-8 text-center" role="status">
          <CheckCircle2 className="h-14 w-14 text-success" aria-hidden="true" />
          <h1 className="mt-3 text-2xl font-bold">Application submitted!</h1>
          <p className="mt-1 text-muted">Your application for {current.title} at {current.company.name} has been sent.</p>
          <div className="mt-5 flex gap-3">
            <button type="button" className="btn-primary" onClick={() => navigate('/seeker/applied')}>Track application</button>
            <Link to="/jobs" className="btn-outline">Keep searching</Link>
          </div>
        </div>
        <h2 className="mb-3 mt-8 font-bold">Similar jobs you may like</h2>
        <div className="space-y-3">
          {similar.data?.slice(0, 3).map((entry) => <JobCard key={entry.id} job={entry} />)}
        </div>
      </div>
    )
  }

  return (
    <div className="mx-auto max-w-2xl px-4 py-6">
      <Breadcrumbs items={[{ label: 'Home', to: '/' }, { label: current.title, to: jobPath(current) }, { label: 'Apply' }]} />
      <h1 className="text-2xl font-bold">{isQuick ? 'Quick apply' : 'Apply'} · {current.title}</h1>
      <p className="mb-4 text-sm text-muted">{current.company.name}</p>
      <form onSubmit={submit} noValidate className="card space-y-5 p-6">
        <FormAlert message={serverError} />
        {resumeList.length === 0 ? (
          <p className="rounded-lg bg-warning/10 p-3 text-sm">
            You have no resume yet.{' '}
            <Link to="/seeker/profile" className="font-semibold text-primary">Upload one in your profile</Link>.
          </p>
        ) : (
          <SelectField
            label="Choose resume"
            required
            value={selectedResume}
            error={attempted ? errors.resume : ''}
            options={resumeList.map((resume) => ({ value: resume.id, label: resume.isDefault ? `${resume.name} (default)` : resume.name }))}
            onChange={(event) => setResumeChoice(event.target.value)}
          />
        )}
        <TextAreaField label="Cover note (optional)" value={coverNote} maxLength={1000} onChange={(event) => setCoverNote(event.target.value)} />

        {questions.map((question) => (
          <div key={question.id}>
            {question.type === 'text' && (
              <TextAreaField label={question.text} required={question.required} rows={3} value={answers[question.id] ?? ''} error={attempted ? errors[question.id] : ''} onChange={(event) => setAnswers({ ...answers, [question.id]: event.target.value })} />
            )}
            {question.type === 'yesno' && (
              <SelectField label={question.text} required={question.required} placeholder="Select" options={['Yes', 'No']} value={answers[question.id] ?? ''} error={attempted ? errors[question.id] : ''} onChange={(event) => setAnswers({ ...answers, [question.id]: event.target.value })} />
            )}
            {question.type === 'choice' && (
              <SelectField label={question.text} required={question.required} placeholder="Select" options={question.options ?? []} value={answers[question.id] ?? ''} error={attempted ? errors[question.id] : ''} onChange={(event) => setAnswers({ ...answers, [question.id]: event.target.value })} />
            )}
          </div>
        ))}

        {!isQuick && (
          <>
            <TextField label="Expected CTC (Lacs PA)" type="number" min={0} required value={expectedCtc} error={attempted ? errors.ctc : ''} onChange={(event) => setExpectedCtc(event.target.value)} />
            <SelectField label="Notice period" required placeholder="Select" options={NOTICE_PERIODS} value={noticePeriod} error={attempted ? errors.notice : ''} onChange={(event) => setNoticePeriod(event.target.value)} />
          </>
        )}

        <div className="flex justify-end gap-3">
          <button type="button" className="btn-outline" onClick={() => navigate(-1)}>Cancel</button>
          <button type="submit" className="btn-primary" disabled={submitting || (attempted && !isValid)}>
            {submitting ? 'Submitting…' : isQuick ? 'Quick apply' : 'Submit application'}
          </button>
        </div>
      </form>
    </div>
  )
}
