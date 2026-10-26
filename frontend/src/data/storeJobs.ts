import { apiClient, unwrap, unwrapList } from '../api/client'
import { mockAlerts, mockMaster, mockNotificationsFor, mockPlatformStats, mockReviews, mockThreadsFor } from './mockData'
import {
  computeMatch,
  decorateJob,
  gate,
  loadApplications,
  loadCompanies,
  loadJobs,
  loadProfile,
  newId,
  paginate,
  read,
  saveApplications,
  saveJobs,
  USE_MOCK,
  userId,
  write,
} from './storeCore'
import { currentUser } from '../auth/auth'
import { PAGE_SIZE } from '../constants'
import type {
  Application,
  ApplicationStatus,
  Company,
  Facets,
  Job,
  JobAlert,
  ListResult,
  MasterItem,
  MasterType,
  NotificationItem,
  NotificationPrefs,
  Profile,
  Resume,
  Review,
  Thread,
} from '../types'

export type SearchParams = Record<string, string>

const FILTER_GROUPS = [
  'location', 'department', 'roleCategory', 'industry', 'companyType', 'company',
  'jobType', 'employmentType', 'workMode', 'education', 'freshness',
] as const

function listParam(params: SearchParams, key: string): string[] {
  return (params[key] ?? '').split(',').map((value) => value.trim()).filter(Boolean)
}

function companyTypeOf(job: Job, companies: Company[]): string {
  return companies.find((company) => company.id === job.companyId)?.companyType ?? ''
}

function groupValues(job: Job, group: string, companies: Company[]): string[] {
  switch (group) {
    case 'location': return job.locations
    case 'company': return [job.company.name]
    case 'companyType': return [companyTypeOf(job, companies)]
    case 'freshness': {
      const ageDays = (Date.now() - new Date(job.postedAt).getTime()) / 86400000
      return ['1', '3', '7', '15', '30'].filter((limit) => ageDays <= Number(limit))
    }
    default: return [String((job as unknown as Record<string, unknown>)[group] ?? '')]
  }
}

function matchesFilters(job: Job, params: SearchParams, companies: Company[], skipGroup?: string): boolean {
  const query = (params.q ?? '').trim().toLowerCase()
  if (query) {
    const haystack = [job.title, job.company.name, job.department, job.roleCategory, ...job.skills].join(' ').toLowerCase()
    if (!query.split(/\s+/).every((token) => haystack.includes(token))) return false
  }
  for (const group of FILTER_GROUPS) {
    if (group === skipGroup) continue
    const wanted = group === 'freshness' ? listParam(params, group).slice(0, 1) : listParam(params, group)
    if (wanted.length) {
      const values = groupValues(job, group, companies)
      const hit =
        group === 'location'
          ? values.some((value) => wanted.some((entry) => value.toLowerCase().includes(entry.toLowerCase())))
          : values.some((value) => wanted.includes(value))
      if (!hit) return false
    }
  }
  if (params.experience !== undefined && params.experience !== '') {
    const years = Number(params.experience)
    if (years < job.experienceMin || years > job.experienceMax) return false
  }
  const salaryMin = Number(params.salaryMin || 0)
  const salaryMax = Number(params.salaryMax || 0)
  if (salaryMin || salaryMax) {
    if (!job.salaryDisclosed) return false
    if (salaryMin && job.salaryMax < salaryMin) return false
    if (salaryMax && job.salaryMin > salaryMax) return false
  }
  return true
}

function relevance(job: Job, query: string): number {
  const text = query.toLowerCase()
  if (!text) return 0
  let score = 0
  if (job.title.toLowerCase().includes(text)) score += 3
  if (job.skills.some((skill) => skill.toLowerCase().includes(text))) score += 2
  if (job.company.name.toLowerCase().includes(text)) score += 1
  return score
}

// MOCK: stands in for GET /jobs/search (filters, facets, sorting, pagination)
function localSearchJobs(params: SearchParams): ListResult<Job> {
  const companies = loadCompanies()
  const active = loadJobs().filter((job) => job.status === 'ACTIVE')
  const matched = active.filter((job) => matchesFilters(job, params, companies))
  const sorted = [...matched].sort((first, second) =>
    params.sort === 'date'
      ? new Date(second.postedAt).getTime() - new Date(first.postedAt).getTime()
      : relevance(second, params.q ?? '') - relevance(first, params.q ?? '') ||
        new Date(second.postedAt).getTime() - new Date(first.postedAt).getTime(),
  )
  const facets: Facets = {}
  for (const group of FILTER_GROUPS) {
    const counts: Record<string, number> = {}
    active
      .filter((job) => matchesFilters(job, params, companies, group))
      .forEach((job) => {
        groupValues(job, group, companies).filter(Boolean).forEach((value) => {
          counts[value] = (counts[value] ?? 0) + 1
        })
      })
    facets[group] = counts
  }
  const page = Number(params.page || 1)
  const pageSize = Number(params.pageSize || PAGE_SIZE)
  return {
    data: paginate(sorted, page, pageSize).map((job) => decorateJob(job)),
    meta: { page, pageSize, total: sorted.length, facets },
  }
}

export async function searchJobs(params: SearchParams): Promise<ListResult<Job>> {
  return gate(
    () => {
      const recent = read<string[]>(`recent_${userId()}`, () => [])
      if (params.q && !recent.includes(params.q)) write(`recent_${userId()}`, [params.q, ...recent].slice(0, 6))
      return localSearchJobs(params)
    },
    async () => unwrapList<Job>(await apiClient.get('/jobs/search', { params })),
  )
}

export async function getJob(id: string): Promise<Job | undefined> {
  return gate(
    // MOCK: stands in for GET /jobs/:id (also resolves closed/expired jobs)
    () => {
      const job = loadJobs().find((entry) => entry.id === id)
      return job ? decorateJob(job, true) : undefined
    },
    async () => unwrap<Job>(await apiClient.get(`/jobs/${id}`)),
  )
}

export async function getSimilarJobs(id: string): Promise<Job[]> {
  return gate(
    // MOCK: stands in for GET /jobs/:id/similar
    () => {
      const base = loadJobs().find((entry) => entry.id === id)
      return loadJobs()
        .filter((job) => job.status === 'ACTIVE' && job.id !== id && base && (job.department === base.department || job.roleCategory === base.roleCategory))
        .slice(0, 4)
        .map((job) => decorateJob(job))
    },
    async () => unwrap<Job[]>(await apiClient.get(`/jobs/${id}/similar`)),
  )
}

export async function getCompanyJobs(companyId: string, query = ''): Promise<Job[]> {
  return gate(
    // MOCK: stands in for GET /companies/:id/jobs
    () =>
      loadJobs()
        .filter((job) => job.companyId === companyId && job.status === 'ACTIVE' && job.title.toLowerCase().includes(query.toLowerCase()))
        .map((job) => decorateJob(job)),
    async () => unwrap<Job[]>(await apiClient.get(`/companies/${companyId}/jobs`, { params: { q: query } })),
  )
}

export async function getFeaturedJobs(): Promise<Job[]> {
  return gate(
    // MOCK: featured jobs = the most recent active jobs
    () => loadJobs().filter((job) => job.status === 'ACTIVE').slice(0, 6).map((job) => decorateJob(job)),
    async () => unwrapList<Job>(await apiClient.get('/jobs/search', { params: { sort: 'date', pageSize: 6 } })).data,
  )
}

export async function getRecommendedJobs(): Promise<Job[]> {
  return gate(
    // MOCK: stands in for GET /jobs/recommended — ranks by skill overlap with the profile
    () => {
      const skills = loadProfile().skills
      return loadJobs()
        .filter((job) => job.status === 'ACTIVE')
        .map((job) => ({ job, score: computeMatch(job, skills).percentage }))
        .sort((first, second) => second.score - first.score)
        .slice(0, 12)
        .map(({ job }) => decorateJob(job, true))
    },
    async () => unwrap<Job[]>(await apiClient.get('/jobs/recommended')),
  )
}

export async function getRecentSearches(): Promise<string[]> {
  return gate(
    // MOCK: stands in for GET /searches/recent
    () => read<string[]>(`recent_${userId()}`, () => []),
    async () => unwrap<string[]>(await apiClient.get('/searches/recent')),
  )
}

export async function getSuggestions(type: 'job' | 'skill' | 'company' | 'location', query: string): Promise<string[]> {
  return gate(
    // MOCK: stands in for GET /suggestions
    () => {
      const text = query.toLowerCase()
      let pool: string[] = []
      if (type === 'job') pool = loadJobs().map((job) => job.title)
      if (type === 'skill') pool = mockMaster.skills.map((item) => item.name)
      if (type === 'company') pool = loadCompanies().map((company) => company.name)
      if (type === 'location') pool = mockMaster.locations.map((item) => item.name)
      return Array.from(new Set(pool)).filter((value) => value.toLowerCase().includes(text)).slice(0, 6)
    },
    async () => unwrap<string[]>(await apiClient.get('/suggestions', { params: { type, q: query } })),
  )
}

export async function getMasterList(type: MasterType, query = ''): Promise<MasterItem[]> {
  return gate(
    // MOCK: stands in for GET /master/:type (admin edits are persisted locally)
    () =>
      read<MasterItem[]>(`master_${type}`, () => mockMaster[type]).filter((item) =>
        item.name.toLowerCase().includes(query.toLowerCase()),
      ),
    async () => unwrap<MasterItem[]>(await apiClient.get(`/master/${type}`, { params: { q: query } })),
  )
}

export async function getPlatformStats(): Promise<{ jobs: number; companies: number; candidates: number }> {
  return gate(
    // MOCK: platform statistics
    () => mockPlatformStats,
    async () => unwrap(await apiClient.get('/stats')),
  )
}

export async function getFacetCounts(): Promise<Facets> {
  const result = await searchJobs({ pageSize: '1' })
  return result.meta.facets ?? {}
}

/* ---------- Saved jobs ---------- */

export async function saveJob(jobId: string): Promise<void> {
  return gate(
    // MOCK: stands in for POST /jobs/:id/save
    () => {
      const saved = read<string[]>(`saved_${userId()}`, () => [])
      if (!saved.includes(jobId)) write(`saved_${userId()}`, [jobId, ...saved])
    },
    async () => {
      await apiClient.post(`/jobs/${jobId}/save`)
    },
  )
}

export async function unsaveJob(jobId: string): Promise<void> {
  return gate(
    // MOCK: stands in for DELETE /jobs/:id/save
    () => {
      write(`saved_${userId()}`, read<string[]>(`saved_${userId()}`, () => []).filter((id) => id !== jobId))
    },
    async () => {
      await apiClient.delete(`/jobs/${jobId}/save`)
    },
  )
}

export async function getSavedJobs(): Promise<Job[]> {
  return gate(
    // MOCK: stands in for GET /jobs/saved
    () => {
      const saved = read<string[]>(`saved_${userId()}`, () => [])
      return loadJobs().filter((job) => saved.includes(job.id)).map((job) => decorateJob(job))
    },
    async () => unwrap<Job[]>(await apiClient.get('/jobs/saved')),
  )
}

export async function reportJob(jobId: string, reason: string, note: string): Promise<void> {
  return gate(
    // MOCK: stands in for POST /jobs/:id/report
    () => {
      const job = loadJobs().find((entry) => entry.id === jobId)
      const reports = read<unknown[]>('job_reports', () => [])
      write('job_reports', [
        { id: newId('rep'), jobId, jobTitle: job?.title ?? '', reason, note, reportedBy: currentUser()?.user.email ?? 'guest', createdAt: new Date().toISOString(), resolved: false },
        ...reports,
      ])
    },
    async () => {
      await apiClient.post(`/jobs/${jobId}/report`, { reason, note })
    },
  )
}

/* ---------- Companies ---------- */

export interface CompanyQuery {
  q?: string
  industry?: string
  companyType?: string
  page?: number
}

export async function getCompanies(query: CompanyQuery): Promise<ListResult<Company>> {
  return gate(
    // MOCK: stands in for GET /companies (approved companies only)
    () => {
      const filtered = loadCompanies().filter(
        (company) =>
          company.status === 'APPROVED' &&
          company.name.toLowerCase().includes((query.q ?? '').toLowerCase()) &&
          (!query.industry || company.industry === query.industry) &&
          (!query.companyType || company.companyType === query.companyType),
      )
      const page = query.page ?? 1
      return { data: paginate(filtered, page, 6), meta: { page, pageSize: 6, total: filtered.length } }
    },
    async () => unwrapList<Company>(await apiClient.get('/admin/companies', { params: query })),
  )
}

export async function getCompany(id: string): Promise<Company | undefined> {
  return gate(
    // MOCK: stands in for GET /companies/:id
    () => loadCompanies().find((company) => company.id === id),
    async () => unwrap<Company>(await apiClient.get(`/companies/${id}`)),
  )
}

export async function getCompanyReviews(companyId: string): Promise<Review[]> {
  return gate(
    // MOCK: stands in for GET /companies/:id/reviews
    () => read<Review[]>('reviews', () => mockReviews).filter((review) => review.companyId === companyId),
    async () => unwrap<Review[]>(await apiClient.get(`/companies/${companyId}/reviews`)),
  )
}

export async function addCompanyReview(companyId: string, input: { rating: number; title: string; body: string }): Promise<Review> {
  return gate(
    // MOCK: stands in for POST /companies/:id/reviews
    () => {
      const review: Review = { id: newId('rev'), companyId, author: currentUser()?.user.name ?? 'Anonymous', createdAt: new Date().toISOString(), ...input }
      write('reviews', [review, ...read<Review[]>('reviews', () => mockReviews)])
      return review
    },
    async () => unwrap<Review>(await apiClient.post(`/companies/${companyId}/reviews`, input)),
  )
}

export async function getFollowingIds(): Promise<string[]> {
  return gate(
    // MOCK: ids of followed companies
    () => read<string[]>(`following_${userId()}`, () => ['c1', 'c7']),
    async () => unwrap<string[]>(await apiClient.get('/companies/following')),
  )
}

export async function followCompany(companyId: string): Promise<void> {
  return gate(
    // MOCK: stands in for POST /companies/:id/follow
    () => {
      const ids = read<string[]>(`following_${userId()}`, () => ['c1', 'c7'])
      if (!ids.includes(companyId)) write(`following_${userId()}`, [...ids, companyId])
    },
    async () => {
      await apiClient.post(`/companies/${companyId}/follow`)
    },
  )
}

export async function unfollowCompany(companyId: string): Promise<void> {
  return gate(
    // MOCK: stands in for DELETE /companies/:id/follow
    () => {
      write(`following_${userId()}`, read<string[]>(`following_${userId()}`, () => ['c1', 'c7']).filter((id) => id !== companyId))
    },
    async () => {
      await apiClient.delete(`/companies/${companyId}/follow`)
    },
  )
}

/* ---------- Applications ---------- */

export interface ApplyInput {
  resumeId: string
  coverNote: string
  answers: { questionId: string; answer: string }[]
  expectedCtc?: number
  noticePeriod?: string
}

export async function applyToJob(jobId: string, input: ApplyInput): Promise<Application> {
  return gate(
    // MOCK: stands in for POST /jobs/:id/apply
    () => {
      const job = loadJobs().find((entry) => entry.id === jobId)
      if (!job) throw new Error('Job not found')
      if (job.status !== 'ACTIVE') throw new Error('This job is no longer accepting applications')
      const applications = loadApplications()
      if (applications.some((entry) => entry.jobId === jobId && entry.candidateId === userId() && entry.status !== 'WITHDRAWN')) {
        throw new Error('You have already applied to this job')
      }
      const profile = loadProfile()
      const resume = read<Resume[]>(`resumes_${userId()}`, () => []).find((entry) => entry.id === input.resumeId)
      const now = new Date().toISOString()
      const application: Application = {
        id: newId('a'),
        jobId,
        jobTitle: job.title,
        company: { id: job.company.id, name: job.company.name, logoUrl: job.company.logoUrl },
        candidateId: userId(),
        candidateName: profile.name,
        headline: profile.headline,
        experience: profile.employments.length ? 3 : 0,
        location: profile.personal.location,
        currentCtc: 0,
        expectedCtc: input.expectedCtc ?? 0,
        noticePeriod: input.noticePeriod ?? '',
        education: profile.educations[0]?.title ?? '',
        skills: profile.skills,
        matchPercentage: computeMatch(job, profile.skills).percentage,
        rating: 0,
        status: 'APPLIED',
        appliedAt: now,
        coverNote: input.coverNote,
        resumeName: resume?.name ?? 'Resume',
        answers: input.answers.map((answer) => ({
          ...answer,
          question: job.screeningQuestions.find((question) => question.id === answer.questionId)?.text ?? '',
        })),
        notes: [],
        history: [{ status: 'APPLIED', at: now }],
        screening: 'in',
      }
      saveApplications([application, ...applications])
      saveJobs(loadJobs().map((entry) => (entry.id === jobId ? { ...entry, applicantsCount: entry.applicantsCount + 1 } : entry)))
      return application
    },
    async () => unwrap<Application>(await apiClient.post(`/jobs/${jobId}/apply`, input)),
  )
}

export async function getMyApplications(status?: ApplicationStatus): Promise<Application[]> {
  return gate(
    // MOCK: stands in for GET /applications/me
    () =>
      loadApplications()
        .filter((entry) => entry.candidateId === userId() && (!status || entry.status === status))
        .sort((first, second) => new Date(second.appliedAt).getTime() - new Date(first.appliedAt).getTime()),
    async () => unwrap<Application[]>(await apiClient.get('/applications/me', { params: { status } })),
  )
}

export async function withdrawApplication(id: string): Promise<void> {
  return gate(
    // MOCK: stands in for POST /applications/:id/withdraw
    () => {
      saveApplications(
        loadApplications().map((entry) =>
          entry.id === id
            ? { ...entry, status: 'WITHDRAWN' as const, history: [...entry.history, { status: 'WITHDRAWN' as const, at: new Date().toISOString() }] }
            : entry,
        ),
      )
    },
    async () => {
      await apiClient.post(`/applications/${id}/withdraw`)
    },
  )
}

export async function respondToInterview(id: string, response: 'CONFIRM' | 'RESCHEDULE', note: string): Promise<void> {
  return gate(
    // MOCK: stands in for POST /applications/:id/interview-response
    () => {
      saveApplications(
        loadApplications().map((entry) =>
          entry.id === id && entry.interview ? { ...entry, interview: { ...entry.interview, response, notes: note || entry.interview.notes } } : entry,
        ),
      )
    },
    async () => {
      await apiClient.post(`/applications/${id}/interview-response`, { response, note })
    },
  )
}

/* ---------- Profile & resumes ---------- */

export async function getProfile(): Promise<Profile> {
  return gate(
    // MOCK: stands in for GET /profile/me
    () => loadProfile(),
    async () => unwrap<Profile>(await apiClient.get('/profile/me')),
  )
}

export async function updateProfile(patch: Partial<Profile>): Promise<Profile> {
  return gate(
    // MOCK: stands in for PUT /profile/me (and the section endpoints)
    () => write(`profile_${userId()}`, { ...loadProfile(), ...patch }),
    async () => unwrap<Profile>(await apiClient.put('/profile/me', patch)),
  )
}

export async function getProfileViews(): Promise<{ views: number; viewers: Profile['viewers'] }> {
  return gate(
    // MOCK: stands in for GET /profile/views
    () => {
      const profile = loadProfile()
      return { views: profile.views, viewers: profile.viewers }
    },
    async () => unwrap(await apiClient.get('/profile/views')),
  )
}

export interface CompletenessTask {
  key: string
  label: string
  done: boolean
}

export async function getCompleteness(): Promise<{ percentage: number; tasks: CompletenessTask[] }> {
  return gate(
    // MOCK: stands in for GET /profile/completeness (computed from local profile)
    () => {
      const profile = loadProfile()
      const resumes = read<Resume[]>(`resumes_${userId()}`, () => [])
      const tasks: CompletenessTask[] = [
        { key: 'resume', label: 'Add your resume', done: resumes.length > 0 },
        { key: 'skills', label: 'Add key skills', done: profile.skills.length > 0 },
        { key: 'education', label: 'Add education', done: profile.educations.length > 0 },
        { key: 'employment', label: 'Add employment history', done: profile.employments.length > 0 },
        { key: 'headline', label: 'Add a resume headline', done: Boolean(profile.headline) },
        { key: 'photo', label: 'Upload a profile photo', done: Boolean(profile.photoUrl) },
      ]
      return { percentage: Math.round((tasks.filter((task) => task.done).length / tasks.length) * 100), tasks }
    },
    async () => unwrap(await apiClient.get('/profile/completeness')),
  )
}

export async function uploadProfilePhoto(dataUrl: string): Promise<void> {
  return gate(
    // MOCK: stores the cropped image as a data URL instead of POST /profile/me/photo
    () => {
      write(`profile_${userId()}`, { ...loadProfile(), photoUrl: dataUrl })
    },
    async () => {
      const blob = await (await fetch(dataUrl)).blob()
      const form = new FormData()
      form.append('file', blob, 'photo.png')
      await apiClient.post('/profile/photo', form, { headers: { 'Content-Type': 'multipart/form-data' } })
    },
  )
}

export async function getResumes(): Promise<Resume[]> {
  return gate(
    // MOCK: stands in for GET /resumes
    () => read<Resume[]>(`resumes_${userId()}`, () => (userId() === 'u-s1' ? [{ id: 'res1', name: 'Priya_Sharma_Resume.pdf', size: 184320, uploadedAt: new Date().toISOString(), isDefault: true }] : [])),
    async () => unwrap<Resume[]>(await apiClient.get('/resumes')),
  )
}

export async function uploadResume(file: File, onProgress: (percent: number) => void): Promise<Resume> {
  if (!USE_MOCK) {
    const form = new FormData()
    form.append('file', file)
    const res = await apiClient.post('/resumes', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
      onUploadProgress: (event) => onProgress(Math.round((event.loaded / (event.total || file.size)) * 100)),
    })
    return unwrap<Resume>(res)
  }
  // MOCK: simulates an upload with progress; stands in for POST /resumes
  for (let percent = 20; percent <= 100; percent += 20) {
    await new Promise((resolve) => setTimeout(resolve, 120))
    onProgress(percent)
  }
  const existing = await getResumes()
  const resume: Resume = { id: newId('res'), name: file.name, size: file.size, uploadedAt: new Date().toISOString(), isDefault: existing.length === 0 }
  write(`resumes_${userId()}`, [...existing, resume])
  return resume
}

export async function setDefaultResume(id: string): Promise<void> {
  return gate(
    // MOCK: stands in for PATCH /resumes/:id/default
    () => {
      write(`resumes_${userId()}`, read<Resume[]>(`resumes_${userId()}`, () => []).map((resume) => ({ ...resume, isDefault: resume.id === id })))
    },
    async () => {
      await apiClient.patch(`/resumes/${id}/default`)
    },
  )
}

export async function deleteResume(id: string): Promise<void> {
  return gate(
    // MOCK: stands in for DELETE /resumes/:id
    () => {
      const remaining = read<Resume[]>(`resumes_${userId()}`, () => []).filter((resume) => resume.id !== id)
      if (remaining.length && !remaining.some((resume) => resume.isDefault)) remaining[0].isDefault = true
      write(`resumes_${userId()}`, remaining)
    },
    async () => {
      await apiClient.delete(`/resumes/${id}`)
    },
  )
}

export async function downloadResume(resume: Resume): Promise<void> {
  const blob = USE_MOCK
    ? // MOCK: generates a placeholder file instead of GET /resumes/:id/download
      new Blob([`Placeholder resume content for ${resume.name}`], { type: 'text/plain' })
    : ((await apiClient.get(`/resumes/${resume.id}/download`, { responseType: 'blob' })).data as Blob)
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = resume.name
  anchor.click()
  URL.revokeObjectURL(url)
}

/* ---------- Alerts ---------- */

export async function getAlerts(): Promise<JobAlert[]> {
  return gate(
    // MOCK: stands in for GET /job-alerts
    () => read<JobAlert[]>(`alerts_${userId()}`, () => mockAlerts),
    async () => unwrap<JobAlert[]>(await apiClient.get('/job-alerts')),
  )
}

export async function saveAlert(alert: Omit<JobAlert, 'id'> & { id?: string }): Promise<JobAlert> {
  return gate(
    // MOCK: stands in for POST/PUT /job-alerts
    () => {
      const all = read<JobAlert[]>(`alerts_${userId()}`, () => mockAlerts)
      if (alert.id) {
        const updated = { ...alert, id: alert.id } as JobAlert
        write(`alerts_${userId()}`, all.map((entry) => (entry.id === alert.id ? updated : entry)))
        return updated
      }
      const created: JobAlert = { ...alert, id: newId('al') }
      write(`alerts_${userId()}`, [created, ...all])
      return created
    },
    async () =>
      unwrap<JobAlert>(alert.id ? await apiClient.put(`/job-alerts/${alert.id}`, alert) : await apiClient.post('/job-alerts', alert)),
  )
}

export async function deleteAlert(id: string): Promise<void> {
  return gate(
    // MOCK: stands in for DELETE /job-alerts/:id
    () => {
      write(`alerts_${userId()}`, read<JobAlert[]>(`alerts_${userId()}`, () => mockAlerts).filter((entry) => entry.id !== id))
    },
    async () => {
      await apiClient.delete(`/job-alerts/${id}`)
    },
  )
}

/* ---------- Notifications, preferences, messages (all roles) ---------- */

function notificationsKey(): string {
  return `notifs_${userId()}`
}

function roleOrSeeker(): string {
  return currentUser()?.user.role ?? 'JOB_SEEKER'
}

export async function getNotifications(unreadOnly = false): Promise<NotificationItem[]> {
  return gate(
    // MOCK: stands in for GET /notifications
    () => read<NotificationItem[]>(notificationsKey(), () => mockNotificationsFor(roleOrSeeker())).filter((item) => !unreadOnly || !item.read),
    async () => unwrap<NotificationItem[]>(await apiClient.get('/notifications', { params: { unread: unreadOnly || undefined } })),
  )
}

export async function setNotificationRead(id: string, isRead: boolean): Promise<void> {
  return gate(
    // MOCK: stands in for PATCH /notifications/:id/read
    () => {
      const all = read<NotificationItem[]>(notificationsKey(), () => mockNotificationsFor(roleOrSeeker()))
      write(notificationsKey(), all.map((item) => (item.id === id ? { ...item, read: isRead } : item)))
    },
    async () => {
      await apiClient.patch(`/notifications/${id}/read`, { read: isRead })
    },
  )
}

export async function markAllNotificationsRead(): Promise<void> {
  return gate(
    // MOCK: stands in for PATCH /notifications/read-all
    () => {
      const all = read<NotificationItem[]>(notificationsKey(), () => mockNotificationsFor(roleOrSeeker()))
      write(notificationsKey(), all.map((item) => ({ ...item, read: true })))
    },
    async () => {
      await apiClient.post('/notifications/read-all')
    },
  )
}

const defaultPrefs: NotificationPrefs = {
  email: true, sms: false, inApp: true, jobAlerts: true, applicationUpdates: true, messages: true, frequency: 'INSTANT',
}

export async function getNotificationPrefs(): Promise<NotificationPrefs> {
  return gate(
    // MOCK: stands in for GET /notification-preferences
    () => read<NotificationPrefs>(`prefs_${userId()}`, () => defaultPrefs),
    async () => unwrap<NotificationPrefs>(await apiClient.get('/notification-preferences')),
  )
}

export async function saveNotificationPrefs(prefs: NotificationPrefs): Promise<void> {
  return gate(
    // MOCK: stands in for PUT /notification-preferences
    () => {
      write(`prefs_${userId()}`, prefs)
    },
    async () => {
      await apiClient.put('/notification-preferences', prefs)
    },
  )
}

export async function savePrivacy(visibility: Profile['visibility'], hideFromCompanies: string): Promise<void> {
  return gate(
    // MOCK: stands in for PUT /profile/visibility
    () => {
      write(`profile_${userId()}`, { ...loadProfile(), visibility, hideFromCompanies })
    },
    async () => {
      await apiClient.put('/profile/privacy', { visibility })
    },
  )
}

export async function getThreads(): Promise<Thread[]> {
  return gate(
    // MOCK: stands in for GET /messages/threads
    () => read<Thread[]>(`threads_${userId()}`, () => mockThreadsFor(roleOrSeeker())),
    async () => unwrap<Thread[]>(await apiClient.get('/messages/threads')),
  )
}

export async function markThreadRead(id: string): Promise<void> {
  return gate(
    // MOCK: clears the unread badge for a thread
    () => {
      const all = read<Thread[]>(`threads_${userId()}`, () => mockThreadsFor(roleOrSeeker()))
      write(`threads_${userId()}`, all.map((thread) => (thread.id === id ? { ...thread, unread: 0 } : thread)))
    },
    async () => {
      await apiClient.post(`/messages/threads/${id}/read`)
    },
  )
}

export async function sendMessage(threadId: string, text: string): Promise<Thread[]> {
  return gate(
    // MOCK: stands in for POST /messages/threads/:id
    () => {
      const all = read<Thread[]>(`threads_${userId()}`, () => mockThreadsFor(roleOrSeeker()))
      return write(
        `threads_${userId()}`,
        all.map((thread) =>
          thread.id === threadId
            ? { ...thread, messages: [...thread.messages, { id: newId('m'), from: 'me' as const, text, at: new Date().toISOString() }] }
            : thread,
        ),
      )
    },
    async () => {
      await apiClient.post(`/messages/threads/${threadId}/messages`, { body: text })
      return unwrap<Thread[]>(await apiClient.get('/messages/threads'))
    },
  )
}

export async function getFollowingCompanies(): Promise<Company[]> {
  return gate(
    // MOCK: stands in for GET /companies/following (full company objects)
    () => {
      const ids = read<string[]>(`following_${userId()}`, () => ['c1', 'c7'])
      return loadCompanies().filter((company) => ids.includes(company.id))
    },
    async () => unwrap<Company[]>(await apiClient.get('/companies/following')),
  )
}
