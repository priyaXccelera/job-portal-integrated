import { useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { Briefcase, Building2, ChevronLeft, ChevronRight, MapPin, Search, UserPlus, Users, FileCheck, UserCheck } from 'lucide-react'
import { CompanyLogo, JobCardSkeleton, Skeleton } from '../components/ui'
import { JobCard, companyPath } from '../components/JobCard'
import { SuggestInput } from '../components/fields'
import { getCompanies, getFacetCounts, getFeaturedJobs, getPlatformStats } from '../data/store'
import { useAsync, useSeo } from '../hooks'
import { POPULAR_CATEGORIES, POPULAR_LOCATIONS, POPULAR_SKILLS } from '../constants'
import { formatIndianNumber } from '../utils/format'

const CATEGORY_FILTERS: Record<string, string> = {
  IT: 'department=Engineering',
  Sales: 'department=Sales',
  Marketing: 'department=Marketing',
  Finance: 'department=Finance',
  HR: 'department=Human%20Resources',
  Engineering: 'department=Engineering',
  Healthcare: 'department=Healthcare',
  Design: 'department=Design',
  Operations: 'department=Operations',
}

const SEEKER_STEPS = [
  { icon: UserPlus, title: 'Create your profile', text: 'Sign up and add your skills and resume in minutes.' },
  { icon: Search, title: 'Search & apply', text: 'Find jobs that match you and apply with one click.' },
  { icon: UserCheck, title: 'Get hired', text: 'Track applications and respond to interview invites.' },
]

const RECRUITER_STEPS = [
  { icon: Building2, title: 'Register your company', text: 'Set up a company profile and get approved.' },
  { icon: Briefcase, title: 'Post jobs', text: 'Publish openings with screening questions.' },
  { icon: FileCheck, title: 'Hire the best', text: 'Review applicants on a pipeline and make offers.' },
]

export function Home() {
  const navigate = useNavigate()
  const [keyword, setKeyword] = useState('')
  const [experience, setExperience] = useState('')
  const [location, setLocation] = useState('')
  const carousel = useRef<HTMLDivElement>(null)
  useSeo('Find your dream job', 'Search lakhs of jobs, explore top companies and apply in one click on JobHub.')

  const companies = useAsync(() => getCompanies({}), [])
  const featured = useAsync(() => getFeaturedJobs(), [])
  const stats = useAsync(() => getPlatformStats(), [])
  const facets = useAsync(() => getFacetCounts(), [])

  const submit = (event: FormEvent) => {
    event.preventDefault()
    const params = new URLSearchParams()
    if (keyword.trim()) params.set('q', keyword.trim())
    if (experience) params.set('experience', experience)
    if (location.trim()) params.set('location', location.trim())
    navigate(`/jobs?${params.toString()}`)
  }

  return (
    <div>
      <section className="bg-gradient-to-br from-primary to-primary-dark px-4 py-16 text-white">
        <div className="mx-auto max-w-5xl text-center">
          <h1 className="text-3xl font-extrabold sm:text-5xl">Find your dream job now</h1>
          <p className="mt-3 text-lg text-white/80">Over {formatIndianNumber(125000)} jobs from top companies across India</p>
          <form onSubmit={submit} className="mt-8 flex flex-col gap-2 rounded-2xl bg-surface p-2 text-ink shadow-xl lg:flex-row lg:items-center" role="search">
            <SuggestInput
              className="flex-1 lg:border-r lg:border-line"
              type="job"
              label="Skills, designation or company"
              placeholder="Enter skills / designations / companies"
              value={keyword}
              onChange={setKeyword}
            />
            <select
              aria-label="Experience"
              className="bg-transparent px-3 py-2 text-sm lg:w-44 lg:border-r lg:border-line"
              value={experience}
              onChange={(event) => setExperience(event.target.value)}
            >
              <option value="">Select experience</option>
              {Array.from({ length: 31 }, (_, years) => (
                <option key={years} value={years}>
                  {years} {years === 1 ? 'year' : 'years'}
                </option>
              ))}
            </select>
            <SuggestInput className="flex-1" type="location" label="Location" placeholder="Enter location" value={location} onChange={setLocation} />
            <button type="submit" className="btn-accent px-8 py-3">
              <Search className="h-4 w-4" />
              Search
            </button>
          </form>
          <div className="mt-6 flex flex-wrap justify-center gap-2">
            <span className="text-sm text-white/70">Popular:</span>
            {POPULAR_CATEGORIES.map((category) => (
              <Link key={category} to={`/jobs?${CATEGORY_FILTERS[category]}`} className="rounded-full bg-white/15 px-3 py-1 text-sm hover:bg-white/30">
                {category}
              </Link>
            ))}
          </div>
        </div>
      </section>

      <div className="mx-auto max-w-7xl space-y-14 px-4 py-12">
        <section aria-labelledby="top-companies">
          <div className="mb-4 flex items-center justify-between">
            <h2 id="top-companies" className="text-2xl font-bold">
              Top companies hiring
            </h2>
            <div className="flex gap-2">
              <button type="button" aria-label="Scroll left" className="btn-outline px-2" onClick={() => carousel.current?.scrollBy({ left: -300, behavior: 'smooth' })}>
                <ChevronLeft className="h-4 w-4" />
              </button>
              <button type="button" aria-label="Scroll right" className="btn-outline px-2" onClick={() => carousel.current?.scrollBy({ left: 300, behavior: 'smooth' })}>
                <ChevronRight className="h-4 w-4" />
              </button>
            </div>
          </div>
          <div ref={carousel} className="flex gap-4 overflow-x-auto pb-2">
            {companies.loading
              ? Array.from({ length: 5 }, (_, index) => <Skeleton key={index} className="h-36 w-44 shrink-0" />)
              : companies.data?.data.map((company) => (
                  <Link key={company.id} to={companyPath(company)} className="card flex w-44 shrink-0 flex-col items-center gap-2 p-5 text-center hover:border-primary">
                    <CompanyLogo src={company.logoUrl} name={company.name} size="h-14 w-14" />
                    <span className="text-sm font-semibold">{company.name}</span>
                    <span className="text-xs text-muted">{company.industry}</span>
                  </Link>
                ))}
          </div>
          <Link to="/companies" className="mt-3 inline-block text-sm font-semibold text-primary hover:underline">
            View all companies
          </Link>
        </section>

        <section aria-labelledby="by-location">
          <h2 id="by-location" className="mb-4 text-2xl font-bold">
            Jobs by location
          </h2>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            {POPULAR_LOCATIONS.map((city) => (
              <Link key={city} to={`/jobs?location=${encodeURIComponent(city)}`} className="card flex items-center gap-3 p-4 hover:border-primary">
                <MapPin className="h-5 w-5 text-primary" />
                <span>
                  <span className="block text-sm font-semibold">{city}</span>
                  <span className="text-xs text-muted">{facets.data?.location?.[city] ?? 0} jobs</span>
                </span>
              </Link>
            ))}
          </div>
        </section>

        <section aria-labelledby="by-skill">
          <h2 id="by-skill" className="mb-4 text-2xl font-bold">
            Jobs by skill
          </h2>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            {POPULAR_SKILLS.map((skill) => (
              <Link key={skill} to={`/jobs?q=${encodeURIComponent(skill)}`} className="card p-4 text-sm font-semibold hover:border-primary">
                {skill} jobs
              </Link>
            ))}
          </div>
        </section>

        <section aria-label="Platform statistics" className="card grid gap-6 bg-soft p-8 text-center sm:grid-cols-3">
          {[
            { label: 'Jobs', value: stats.data?.jobs, icon: Briefcase },
            { label: 'Companies', value: stats.data?.companies, icon: Building2 },
            { label: 'Candidates', value: stats.data?.candidates, icon: Users },
          ].map((stat) => (
            <div key={stat.label}>
              <stat.icon className="mx-auto h-8 w-8 text-primary" />
              <p className="mt-2 text-3xl font-extrabold">{stat.value ? formatIndianNumber(stat.value) : '—'}</p>
              <p className="text-sm text-muted">{stat.label}</p>
            </div>
          ))}
        </section>

        <section aria-labelledby="how-it-works" className="grid gap-8 lg:grid-cols-2">
          {[
            { title: 'How it works for job seekers', steps: SEEKER_STEPS, cta: { label: 'Register as job seeker', to: '/register?role=JOB_SEEKER' } },
            { title: 'How it works for recruiters', steps: RECRUITER_STEPS, cta: { label: 'Register as recruiter', to: '/register?role=RECRUITER' } },
          ].map((block, index) => (
            <div key={block.title} className="card p-6">
              <h2 id={index === 0 ? 'how-it-works' : undefined} className="mb-4 text-xl font-bold">
                {block.title}
              </h2>
              <ol className="space-y-4">
                {block.steps.map((step) => (
                  <li key={step.title} className="flex gap-3">
                    <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-soft text-primary">
                      <step.icon className="h-5 w-5" />
                    </span>
                    <span>
                      <span className="block font-semibold">{step.title}</span>
                      <span className="text-sm text-muted">{step.text}</span>
                    </span>
                  </li>
                ))}
              </ol>
              <Link to={block.cta.to} className="btn-primary mt-5">
                {block.cta.label}
              </Link>
            </div>
          ))}
        </section>

        <section aria-labelledby="featured">
          <div className="mb-4 flex items-center justify-between">
            <h2 id="featured" className="text-2xl font-bold">
              Featured jobs
            </h2>
            <Link to="/jobs" className="text-sm font-semibold text-primary hover:underline">
              View all jobs
            </Link>
          </div>
          <div className="grid gap-4 lg:grid-cols-2">
            {featured.loading
              ? Array.from({ length: 4 }, (_, index) => <JobCardSkeleton key={index} />)
              : featured.data?.map((job) => <JobCard key={job.id} job={job} />)}
          </div>
        </section>
      </div>
    </div>
  )
}
