import { currentUser } from '../auth/auth'
import { mockApplications, mockCompanies, mockJobs, mockProfiles } from './mockData'
import type { Application, Company, Job, MatchScore, Profile } from '../types'

// Uses the real backend by default; set VITE_DEMO_MODE=true to use local mock data.
export const USE_MOCK = import.meta.env.VITE_DEMO_MODE === 'true'

const MOCK_LATENCY_MS = 200

export function delay(ms = MOCK_LATENCY_MS): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

/** Thin mock/real gate used by every exported store function. */
export async function gate<T>(local: () => T, remote: () => Promise<T>): Promise<T> {
  if (USE_MOCK) {
    await delay()
    return local()
  }
  return remote()
}

export function read<T>(key: string, seed: () => T): T {
  const raw = localStorage.getItem(key)
  if (raw) return JSON.parse(raw) as T
  const value = seed()
  localStorage.setItem(key, JSON.stringify(value))
  return value
}

export function write<T>(key: string, value: T): T {
  localStorage.setItem(key, JSON.stringify(value))
  return value
}

export function newId(prefix: string): string {
  return `${prefix}${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`
}

export function userId(): string {
  return currentUser()?.user.id ?? 'guest'
}

export function userCompanyId(): string {
  return currentUser()?.user.companyId ?? ''
}

export function paginate<T>(items: T[], page: number, pageSize: number): T[] {
  const start = (Math.max(page, 1) - 1) * pageSize
  return items.slice(start, start + pageSize)
}

// MOCK: all jobs (seed + recruiter-created) persisted locally
export function loadJobs(): Job[] {
  return read<Job[]>('jobs', () => mockJobs)
}

export function saveJobs(jobs: Job[]): void {
  write('jobs', jobs)
}

// MOCK: all companies persisted locally
export function loadCompanies(): Company[] {
  return read<Company[]>('companies', () => mockCompanies)
}

export function saveCompanies(companies: Company[]): void {
  write('companies', companies)
}

export function loadApplications(): Application[] {
  return read<Application[]>('applications', () => mockApplications)
}

export function saveApplications(applications: Application[]): void {
  write('applications', applications)
}

export function loadProfile(): Profile {
  const session = currentUser()
  const id = userId()
  return read<Profile>(`profile_${id}`, () => {
    const seeded = mockProfiles.find((profile) => profile.userId === id)
    if (seeded) return seeded
    return {
      userId: id,
      name: session?.user.name ?? '',
      photoUrl: '',
      headline: '',
      skills: [],
      employments: [],
      educations: [],
      projects: [],
      certifications: [],
      languages: [],
      onlineProfiles: [],
      personal: { dob: '', gender: '', location: '', maritalStatus: '' },
      career: { preferredLocations: '', expectedSalary: '', jobType: '', employmentType: '', industry: '', noticePeriod: '' },
      visibility: 'PUBLIC',
      hideFromCompanies: '',
      views: 0,
      viewers: [],
    }
  })
}

export function computeMatch(job: Job, skills: string[]): MatchScore {
  const owned = skills.map((skill) => skill.toLowerCase())
  const required = [...job.skills, ...job.preferredSkills]
  const matchingSkills = required.filter((skill) => owned.includes(skill.toLowerCase()))
  const missingSkills = required.filter((skill) => !owned.includes(skill.toLowerCase()))
  return {
    percentage: required.length ? Math.round((matchingSkills.length / required.length) * 100) : 0,
    matchingSkills,
    missingSkills,
  }
}

/** Adds per-user flags (saved / applied / match) to a raw job */
export function decorateJob(job: Job, withMatch = false): Job {
  const session = currentUser()
  if (!session || session.user.role !== 'JOB_SEEKER') {
    return { ...job, isSaved: false, isApplied: false }
  }
  const saved = read<string[]>(`saved_${session.user.id}`, () => [])
  const application = loadApplications().find(
    (entry) => entry.jobId === job.id && entry.candidateId === session.user.id && entry.status !== 'WITHDRAWN',
  )
  const decorated: Job = {
    ...job,
    isSaved: saved.includes(job.id),
    isApplied: Boolean(application),
    applicationStatus: application?.status,
  }
  if (withMatch) decorated.matchScore = computeMatch(job, loadProfile().skills)
  return decorated
}
