import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { Bookmark, BriefcaseBusiness, IndianRupee, MapPin, Star } from 'lucide-react'
import toast from 'react-hot-toast'
import { useAuth } from '../auth/auth'
import { saveJob, unsaveJob } from '../data/store'
import type { Company, Job } from '../types'
import { formatExperience, formatSalary, slugWithId, timeAgo } from '../utils/format'
import { CompanyLogo, StatusBadge } from './ui'

export function jobPath(job: Pick<Job, 'id' | 'title'>): string {
  return `/jobs/${slugWithId(job.title, job.id)}`
}

export function companyPath(company: { id: string; name: string }): string {
  return `/companies/${slugWithId(company.name, company.id)}`
}

export function JobCard({
  job,
  onOpen,
  selected = false,
  onSavedChange,
}: {
  job: Job
  onOpen?: (job: Job) => void
  selected?: boolean
  onSavedChange?: (job: Job, saved: boolean) => void
}) {
  const navigate = useNavigate()
  const { role } = useAuth()
  const [saved, setSaved] = useState(Boolean(job.isSaved))

  const toggleSave = async () => {
    if (!role) {
      navigate(`/login?returnTo=${encodeURIComponent(window.location.pathname + window.location.search)}`)
      return
    }
    if (role !== 'JOB_SEEKER') {
      toast.error('Only job seekers can save jobs')
      return
    }
    try {
      if (saved) await unsaveJob(job.id)
      else await saveJob(job.id)
      setSaved(!saved)
      onSavedChange?.(job, !saved)
      toast.success(saved ? 'Removed from saved jobs' : 'Job saved')
    } catch {
      // error toast is shown by the API client interceptor
    }
  }

  return (
    <article
      className={`card cursor-pointer p-5 transition hover:border-primary hover:shadow-md ${selected ? 'border-primary ring-2 ring-primary/30' : ''}`}
      onClick={() => (onOpen ? onOpen(job) : navigate(jobPath(job)))}
    >
      <div className="flex gap-4">
        <CompanyLogo src={job.company.logoUrl} name={job.company.name} />
        <div className="min-w-0 flex-1">
          <div className="flex items-start justify-between gap-2">
            <div className="min-w-0">
              <h3 className="truncate text-base font-bold">
                <Link to={jobPath(job)} className="hover:text-primary" onClick={(event) => event.stopPropagation()}>
                  {job.title}
                </Link>
              </h3>
              <p className="mt-0.5 flex items-center gap-2 text-sm text-muted">
                <Link to={companyPath(job.company)} className="hover:text-primary hover:underline" onClick={(event) => event.stopPropagation()}>
                  {job.company.name}
                </Link>
                <span className="inline-flex items-center gap-0.5 text-xs font-semibold text-ink">
                  <Star className="h-3 w-3 fill-warning text-warning" />
                  {job.company.rating}
                </span>
              </p>
            </div>
            <button
              type="button"
              aria-label={saved ? 'Remove from saved jobs' : 'Save job'}
              aria-pressed={saved}
              className="rounded-full p-2 hover:bg-soft"
              onClick={(event) => {
                event.stopPropagation()
                toggleSave()
              }}
            >
              <Bookmark className={`h-5 w-5 ${saved ? 'fill-primary text-primary' : 'text-muted'}`} />
            </button>
          </div>
          <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-sm text-muted">
            <span className="inline-flex items-center gap-1">
              <BriefcaseBusiness className="h-4 w-4" />
              {formatExperience(job.experienceMin, job.experienceMax)}
            </span>
            <span className="inline-flex items-center gap-1">
              <IndianRupee className="h-4 w-4" />
              {formatSalary(job.salaryMin, job.salaryMax, job.salaryDisclosed)}
            </span>
            <span className="inline-flex items-center gap-1">
              <MapPin className="h-4 w-4" />
              {job.locations.join(', ')}
            </span>
          </div>
          <p className="mt-2 line-clamp-2 text-sm text-muted">{job.snippet}</p>
          <div className="mt-3 flex flex-wrap gap-2">
            {job.skills.slice(0, 5).map((skill) => (
              <span key={skill} className="rounded-md bg-canvas px-2 py-1 text-xs text-muted">
                {skill}
              </span>
            ))}
          </div>
          <div className="mt-3 flex items-center gap-3 text-xs text-muted">
            <span>{timeAgo(job.postedAt)}</span>
            {job.isApplied && job.applicationStatus && <StatusBadge status={job.applicationStatus} />}
            {job.isApplied && !job.applicationStatus && <span className="font-semibold text-success">Applied</span>}
          </div>
        </div>
      </div>
    </article>
  )
}

export function CompanyCard({ company }: { company: Company }) {
  const navigate = useNavigate()
  return (
    <article className="card flex cursor-pointer items-center gap-4 p-5 hover:border-primary" onClick={() => navigate(companyPath(company))}>
      <CompanyLogo src={company.logoUrl} name={company.name} size="h-14 w-14" />
      <div className="min-w-0 flex-1">
        <h3 className="truncate font-bold">
          <Link to={companyPath(company)} className="hover:text-primary" onClick={(event) => event.stopPropagation()}>
            {company.name}
          </Link>
        </h3>
        <p className="flex items-center gap-1 text-sm text-muted">
          <Star className="h-3.5 w-3.5 fill-warning text-warning" />
          {company.rating} · {company.reviewsCount} reviews
        </p>
        <p className="truncate text-xs text-muted">
          {company.industry} · {company.companyType} · {company.headquarters}
        </p>
      </div>
    </article>
  )
}
