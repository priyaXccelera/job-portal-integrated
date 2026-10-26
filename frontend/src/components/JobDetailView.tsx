import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import {
  Bookmark,
  BriefcaseBusiness,
  CheckCircle2,
  Copy,
  Flag,
  IndianRupee,
  MapPin,
  Star,
  Users,
  XCircle,
} from 'lucide-react'
import toast from 'react-hot-toast'
import { useAuth } from '../auth/auth'
import { Facebook, Linkedin, Twitter } from './SocialIcons'
import { getCompany, getCompanyJobs, getJob, getMyApplications, getSimilarJobs, reportJob, saveJob, unsaveJob } from '../data/store'
import { REPORT_REASONS } from '../constants'
import { useAsync, useSeo } from '../hooks'
import type { Job } from '../types'
import { sanitizeHtml } from '../utils/sanitize'
import { formatDate, formatExperience, formatSalary, timeAgo } from '../utils/format'
import { companyPath, JobCard, jobPath } from './JobCard'
import { SelectField, TextAreaField } from './fields'
import { StatusTracker, Timeline } from './StatusTracker'
import { CompanyLogo, EmptyState, ErrorState, Modal, Skeleton, StatusBadge } from './ui'

function SkillTags({ skills, matching, missing }: { skills: string[]; matching: string[]; missing: string[] }) {
  return (
    <div className="flex flex-wrap gap-2">
      {skills.map((skill) => {
        const tone = matching.includes(skill)
          ? 'border-success bg-success/10 text-success'
          : missing.includes(skill)
            ? 'border-danger/50 bg-danger/5 text-danger'
            : 'border-line bg-canvas text-muted'
        return (
          <span key={skill} className={`rounded-md border px-2.5 py-1 text-xs font-medium ${tone}`}>
            {skill}
          </span>
        )
      })}
    </div>
  )
}

function JsonLd(job: Job) {
  return {
    '@context': 'https://schema.org',
    '@type': 'JobPosting',
    title: job.title,
    description: job.description,
    datePosted: job.postedAt.slice(0, 10),
    validThrough: job.expiresAt.slice(0, 10),
    employmentType: job.jobType.toUpperCase().replace(' ', '_'),
    hiringOrganization: { '@type': 'Organization', name: job.company.name },
    jobLocation: { '@type': 'Place', address: { '@type': 'PostalAddress', addressLocality: job.locations[0], addressCountry: 'IN' } },
    baseSalary: job.salaryDisclosed
      ? { '@type': 'MonetaryAmount', currency: 'INR', value: { '@type': 'QuantitativeValue', minValue: job.salaryMin * 100000, maxValue: job.salaryMax * 100000, unitText: 'YEAR' } }
      : undefined,
  }
}

export function JobDetailView({ jobId, compact = false }: { jobId: string; compact?: boolean }) {
  const navigate = useNavigate()
  const { role, isLoggedIn } = useAuth()
  const job = useAsync(() => getJob(jobId), [jobId])
  const similar = useAsync(() => getSimilarJobs(jobId), [jobId])
  const companyId = job.data?.companyId ?? ''
  const company = useAsync(() => (companyId ? getCompany(companyId) : Promise.resolve(undefined)), [companyId])
  const moreFromCompany = useAsync(() => (companyId ? getCompanyJobs(companyId) : Promise.resolve([])), [companyId])
  const applications = useAsync(() => (role === 'JOB_SEEKER' ? getMyApplications() : Promise.resolve([])), [role, jobId])
  const [reportOpen, setReportOpen] = useState(false)
  const [reason, setReason] = useState('')
  const [note, setNote] = useState('')
  const [reasonError, setReasonError] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [savedOverride, setSavedOverride] = useState<boolean | null>(null)

  const current = job.data
  useSeo(
    compact || !current ? '' : `${current.title} at ${current.company.name}`,
    current?.snippet ?? 'Job details on JobHub',
    compact || !current ? undefined : JsonLd(current),
  )

  if (job.loading) {
    return (
      <div className="space-y-4" aria-busy="true">
        <Skeleton className="h-8 w-2/3" />
        <Skeleton className="h-5 w-1/3" />
        <Skeleton className="h-40 w-full" />
      </div>
    )
  }
  if (job.error) return <ErrorState message={job.error} onRetry={job.reload} />
  if (!current) {
    return (
      <EmptyState
        title="Job not found"
        message="This job may have been removed."
        action={
          <Link to="/jobs" className="btn-primary">
            Browse jobs
          </Link>
        }
      />
    )
  }

  const application = applications.data?.find((entry) => entry.jobId === current.id && entry.status !== 'WITHDRAWN')
  const isOpen = current.status === 'ACTIVE'
  const saved = savedOverride ?? Boolean(current.isSaved)
  const returnTo = encodeURIComponent(`${jobPath(current)}`)
  const shareUrl = encodeURIComponent(window.location.origin + jobPath(current))

  const onApply = () => {
    if (!isLoggedIn) navigate(`/login?returnTo=${encodeURIComponent(`${jobPath(current)}/apply`)}`)
    else navigate(`${jobPath(current)}/apply`)
  }

  const onSave = async () => {
    if (!isLoggedIn) {
      navigate(`/login?returnTo=${returnTo}`)
      return
    }
    if (role !== 'JOB_SEEKER') {
      toast.error('Only job seekers can save jobs')
      return
    }
    try {
      if (saved) await unsaveJob(current.id)
      else await saveJob(current.id)
      setSavedOverride(!saved)
      toast.success(saved ? 'Removed from saved jobs' : 'Job saved')
    } catch {
      // API client shows the error toast
    }
  }

  const submitReport = async () => {
    if (!reason) {
      setReasonError('Select a reason')
      return
    }
    setSubmitting(true)
    try {
      await reportJob(current.id, reason, note)
      toast.success('Thanks, our team will review this job')
      setReportOpen(false)
      setReason('')
      setNote('')
    } catch {
      // API client shows the error toast
    } finally {
      setSubmitting(false)
    }
  }

  const match = current.matchScore
  const sections = (
    <>
      {match && role === 'JOB_SEEKER' && (
        <section className="card p-5" aria-label="Skill match">
          <h2 className="font-bold">
            You match {match.matchingSkills.length} of {match.matchingSkills.length + match.missingSkills.length} skills
          </h2>
          <div className="mt-2 h-2 overflow-hidden rounded-full bg-line">
            <div className="h-full bg-success" style={{ width: `${match.percentage}%` }} />
          </div>
          <p className="mt-3 text-xs font-semibold text-success">Matching skills</p>
          <SkillTags skills={match.matchingSkills} matching={match.matchingSkills} missing={[]} />
          {match.missingSkills.length > 0 && (
            <>
              <p className="mt-3 text-xs font-semibold text-danger">Missing skills</p>
              <SkillTags skills={match.missingSkills} matching={[]} missing={match.missingSkills} />
              <Link to="/seeker/profile" className="mt-3 inline-block text-sm font-semibold text-primary hover:underline">
                Add skills to your profile
              </Link>
            </>
          )}
        </section>
      )}

      <section className="card space-y-4 p-5">
        <div>
          <h2 className="font-bold">Job description</h2>
          <div className="mt-2 text-sm text-muted" dangerouslySetInnerHTML={{ __html: sanitizeHtml(current.description) }} />
        </div>
        {current.responsibilities.length > 0 && (
          <div>
            <h3 className="font-semibold">Responsibilities</h3>
            <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-muted">
              {current.responsibilities.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          </div>
        )}
        <div>
          <h3 className="mb-2 font-semibold">Required skills</h3>
          <SkillTags skills={current.skills} matching={match?.matchingSkills ?? []} missing={match?.missingSkills ?? []} />
        </div>
        {current.preferredSkills.length > 0 && (
          <div>
            <h3 className="mb-2 font-semibold">Preferred skills</h3>
            <SkillTags skills={current.preferredSkills} matching={match?.matchingSkills ?? []} missing={match?.missingSkills ?? []} />
          </div>
        )}
        <div>
          <h3 className="font-semibold">Education</h3>
          <p className="text-sm text-muted">{current.education}</p>
        </div>
        <div>
          <h3 className="mb-2 font-semibold">Role details</h3>
          <dl className="grid grid-cols-2 gap-3 text-sm">
            {[
              ['Department', current.department],
              ['Role category', current.roleCategory],
              ['Employment type', current.employmentType],
              ['Job type', current.jobType],
              ['Work mode', current.workMode],
              ['Industry', current.industry],
            ].map(([term, value]) => (
              <div key={term}>
                <dt className="text-muted">{term}</dt>
                <dd className="font-medium">{value}</dd>
              </div>
            ))}
          </dl>
        </div>
      </section>

      <section className="card p-5">
        <h2 className="mb-3 font-bold">About the company</h2>
        <div className="flex items-start gap-3">
          <CompanyLogo src={current.company.logoUrl} name={current.company.name} />
          <div>
            <Link to={companyPath(current.company)} className="font-semibold text-primary hover:underline">
              {current.company.name}
            </Link>
            <p className="mt-1 text-sm text-muted">{company.data?.about}</p>
          </div>
        </div>
      </section>

      {!compact && (
        <>
          <section>
            <h2 className="mb-3 font-bold">Similar jobs</h2>
            <div className="space-y-3">
              {similar.data?.map((entry) => <JobCard key={entry.id} job={entry} />)}
              {similar.data?.length === 0 && <p className="text-sm text-muted">No similar jobs right now.</p>}
            </div>
          </section>
          <section>
            <h2 className="mb-3 font-bold">More jobs from {current.company.name}</h2>
            <div className="space-y-3">
              {moreFromCompany.data?.filter((entry) => entry.id !== current.id).slice(0, 3).map((entry) => <JobCard key={entry.id} job={entry} />)}
              {moreFromCompany.data?.filter((entry) => entry.id !== current.id).length === 0 && <p className="text-sm text-muted">No other openings.</p>}
            </div>
          </section>
        </>
      )}
    </>
  )

  return (
    <div className="space-y-4">
      {!isOpen && (
        <div role="alert" className="flex items-center gap-2 rounded-lg border border-danger/40 bg-danger/10 px-4 py-3 text-sm font-semibold text-danger">
          <XCircle className="h-5 w-5" />
          This job is {current.status === 'EXPIRED' ? 'expired' : 'no longer accepting applications'}.
        </div>
      )}
      <section className="card p-5">
        <div className="flex items-start gap-4">
          <CompanyLogo src={current.company.logoUrl} name={current.company.name} size="h-16 w-16" />
          <div className="min-w-0 flex-1">
            <h1 className={`font-bold ${compact ? 'text-lg' : 'text-2xl'}`}>{current.title}</h1>
            <p className="mt-1 flex items-center gap-2 text-sm">
              <Link to={companyPath(current.company)} className="font-semibold text-primary hover:underline">
                {current.company.name}
              </Link>
              <span className="inline-flex items-center gap-0.5 text-xs font-semibold">
                <Star className="h-3 w-3 fill-warning text-warning" />
                {current.company.rating}
              </span>
            </p>
          </div>
        </div>
        <div className="mt-4 flex flex-wrap gap-x-5 gap-y-2 text-sm text-muted">
          <span className="inline-flex items-center gap-1">
            <BriefcaseBusiness className="h-4 w-4" />
            {formatExperience(current.experienceMin, current.experienceMax)}
          </span>
          <span className="inline-flex items-center gap-1">
            <IndianRupee className="h-4 w-4" />
            {formatSalary(current.salaryMin, current.salaryMax, current.salaryDisclosed)}
          </span>
          <span className="inline-flex items-center gap-1">
            <MapPin className="h-4 w-4" />
            {current.locations.join(', ')}
          </span>
          <span className="inline-flex items-center gap-1">
            <Users className="h-4 w-4" />
            {current.openings} openings
          </span>
        </div>
        <p className="mt-3 text-xs text-muted">
          Posted {timeAgo(current.postedAt)} ({formatDate(current.postedAt)}) · {current.applicantsCount} applicants
        </p>

        <div className="mt-4 flex flex-wrap items-center gap-3">
          {application ? (
            <div className="flex items-center gap-2 text-sm font-semibold text-success">
              <CheckCircle2 className="h-5 w-5" />
              Applied · <StatusBadge status={application.status} />
            </div>
          ) : role === 'RECRUITER' || role === 'ADMIN' ? (
            <p className="text-sm text-muted">Log in as a job seeker to apply.</p>
          ) : (
            <button type="button" className="btn-primary px-8" disabled={!isOpen} onClick={onApply}>
              {isOpen ? (current.screeningQuestions.length === 0 ? 'Quick apply' : 'Apply now') : 'Closed'}
            </button>
          )}
          <button type="button" className="btn-outline" aria-pressed={saved} onClick={onSave}>
            <Bookmark className={`h-4 w-4 ${saved ? 'fill-primary text-primary' : ''}`} />
            {saved ? 'Saved' : 'Save'}
          </button>
          <button
            type="button"
            className="btn-outline"
            onClick={() => (isLoggedIn ? setReportOpen(true) : navigate(`/login?returnTo=${returnTo}`))}
          >
            <Flag className="h-4 w-4" />
            Report job
          </button>
          <span className="ml-auto flex items-center gap-1" aria-label="Share">
            <button
              type="button"
              aria-label="Copy link"
              className="rounded-full p-2 hover:bg-soft"
              onClick={() => {
                navigator.clipboard?.writeText(window.location.origin + jobPath(current))
                toast.success('Link copied')
              }}
            >
              <Copy className="h-4 w-4" />
            </button>
            <a aria-label="Share on LinkedIn" target="_blank" rel="noreferrer" className="rounded-full p-2 hover:bg-soft" href={`https://www.linkedin.com/sharing/share-offsite/?url=${shareUrl}`}>
              <Linkedin className="h-4 w-4" />
            </a>
            <a aria-label="Share on Twitter" target="_blank" rel="noreferrer" className="rounded-full p-2 hover:bg-soft" href={`https://twitter.com/intent/tweet?url=${shareUrl}`}>
              <Twitter className="h-4 w-4" />
            </a>
            <a aria-label="Share on Facebook" target="_blank" rel="noreferrer" className="rounded-full p-2 hover:bg-soft" href={`https://www.facebook.com/sharer/sharer.php?u=${shareUrl}`}>
              <Facebook className="h-4 w-4" />
            </a>
          </span>
        </div>
        {compact && (
          <Link to={jobPath(current)} className="mt-3 inline-block text-sm font-semibold text-primary hover:underline">
            Open full page
          </Link>
        )}
      </section>

      {application && (
        <section className="card space-y-4 p-5" aria-label="Application status">
          <h2 className="font-bold">Your application</h2>
          <StatusTracker status={application.status} history={application.history} />
          <Timeline history={application.history} />
          {application.interview && (
            <p className="rounded-lg bg-soft p-3 text-sm">
              Interview on <strong>{formatDate(application.interview.dateTime)}</strong> ({application.interview.mode}). Manage it from{' '}
              <Link to="/seeker/applied" className="font-semibold text-primary hover:underline">
                Applied jobs
              </Link>
              .
            </p>
          )}
        </section>
      )}

      {sections}

      <Modal open={reportOpen} title="Report this job" onClose={() => setReportOpen(false)}>
        <div className="space-y-4">
          <SelectField
            label="Reason"
            required
            value={reason}
            error={reasonError}
            placeholder="Select a reason"
            options={REPORT_REASONS}
            onChange={(event) => {
              setReason(event.target.value)
              setReasonError('')
            }}
          />
          <TextAreaField label="Additional details" value={note} onChange={(event) => setNote(event.target.value)} />
          <div className="flex justify-end gap-3">
            <button type="button" className="btn-outline" onClick={() => setReportOpen(false)}>
              Cancel
            </button>
            <button type="button" className="btn-danger" disabled={submitting} onClick={submitReport}>
              {submitting ? 'Submitting…' : 'Submit report'}
            </button>
          </div>
        </div>
      </Modal>
    </div>
  )
}
