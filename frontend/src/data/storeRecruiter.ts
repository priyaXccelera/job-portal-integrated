import { apiClient, unwrap, unwrapList } from '../api/client'
import { mockCandidates } from './mockData'
import {
  USE_MOCK,
  decorateJob,
  gate,
  loadApplications,
  loadCompanies,
  loadJobs,
  newId,
  paginate,
  read,
  saveApplications,
  saveCompanies,
  saveJobs,
  userCompanyId,
  userId,
  write,
} from './storeCore'
import { BOARD_COLUMNS, PAGE_SIZE } from '../constants'
import { downloadCsv } from '../utils/format'
import { matchesBoolean } from '../utils/booleanSearch'
import type {
  Application,
  ApplicationStatus,
  Candidate,
  Company,
  Folder,
  Interview,
  Invitation,
  Job,
  JobStatus,
  ListResult,
  PostJobDraft,
  SavedSearch,
  TeamMember,
} from '../types'

export const UNLOCK_COST = 5

/* ---------- Company & team ---------- */

function loadOwnCompany(): Company {
  const id = userCompanyId()
  const companies = loadCompanies()
  const existing = companies.find((company) => company.id === id)
  if (existing) return existing
  const created: Company = {
    id,
    name: localStorage.getItem(`company_name_${id}`) ?? 'My Company',
    logoUrl: '',
    bannerUrl: '',
    rating: 0,
    reviewsCount: 0,
    industry: 'IT Services',
    companyType: 'Startup',
    size: '1-50',
    headquarters: '',
    website: '',
    about: '',
    benefits: [],
    gallery: [],
    status: 'PENDING',
    credits: 20,
    quota: 5,
    followers: 0,
  }
  saveCompanies([...companies, created])
  return created
}

export async function getRecruiterCompany(): Promise<Company> {
  return gate(
    // MOCK: stands in for GET /recruiter/company
    () => loadOwnCompany(),
    async () => unwrap<Company>(await apiClient.get('/recruiter/company')),
  )
}

export async function updateRecruiterCompany(patch: Partial<Company>): Promise<Company> {
  return gate(
    // MOCK: stands in for PUT /recruiter/company (logo/banner/gallery stored as data URLs)
    () => {
      const own = loadOwnCompany()
      const updated = { ...own, ...patch }
      saveCompanies(loadCompanies().map((company) => (company.id === own.id ? updated : company)))
      return updated
    },
    async () => unwrap<Company>(await apiClient.put('/recruiter/company', patch)),
  )
}

const seedMembers: TeamMember[] = [
  { id: 'tm1', name: 'Riya Recruiter', email: 'recruiter1@company.com', role: 'Owner' },
  { id: 'tm2', name: 'Sameer Khan', email: 'sameer@company.com', role: 'Recruiter' },
]
const seedInvites: Invitation[] = [{ id: 'inv1', email: 'newhire@company.com', sentAt: new Date().toISOString() }]

export async function getTeam(): Promise<{ members: TeamMember[]; invitations: Invitation[] }> {
  return gate(
    // MOCK: stands in for GET /recruiter/team
    () => ({
      members: read<TeamMember[]>(`team_${userCompanyId()}`, () => seedMembers),
      invitations: read<Invitation[]>(`invites_${userCompanyId()}`, () => seedInvites),
    }),
    async () => {
      const [team, invites] = await Promise.all([
        apiClient.get('/recruiter/company/recruiters'),
        apiClient.get('/recruiter/company/invitations', { params: { status: 'PENDING' } }),
      ])
      return {
        members: unwrap<Array<{ id: string; name: string; email: string; isCompanyAdmin?: boolean }>>(team).map((m) => ({
          id: m.id,
          name: m.name,
          email: m.email,
          role: m.isCompanyAdmin ? 'Owner' : 'Recruiter',
        })),
        invitations: unwrap<Array<{ id: string; email: string; createdAt: string }>>(invites).map((i) => ({
          id: i.id,
          email: i.email,
          sentAt: i.createdAt,
        })),
      }
    },
  )
}

export async function inviteTeamMember(email: string): Promise<void> {
  return gate(
    // MOCK: stands in for POST /recruiter/invitations
    () => {
      const invites = read<Invitation[]>(`invites_${userCompanyId()}`, () => seedInvites)
      if (invites.some((invite) => invite.email === email)) throw new Error('This email has already been invited')
      write(`invites_${userCompanyId()}`, [{ id: newId('inv'), email, sentAt: new Date().toISOString() }, ...invites])
    },
    async () => {
      await apiClient.post('/recruiter/company/invitations', { email })
    },
  )
}

export async function cancelInvitation(id: string): Promise<void> {
  return gate(
    // MOCK: removes a pending invitation
    () => {
      write(`invites_${userCompanyId()}`, read<Invitation[]>(`invites_${userCompanyId()}`, () => seedInvites).filter((invite) => invite.id !== id))
    },
    async () => {
      await apiClient.delete(`/recruiter/company/invitations/${id}`)
    },
  )
}

export async function resendInvitation(id: string): Promise<void> {
  return gate(
    // MOCK: refreshes the sent timestamp of an invitation
    () => {
      write(
        `invites_${userCompanyId()}`,
        read<Invitation[]>(`invites_${userCompanyId()}`, () => seedInvites).map((invite) => (invite.id === id ? { ...invite, sentAt: new Date().toISOString() } : invite)),
      )
    },
    async () => {
      await apiClient.post(`/recruiter/invitations/${id}/resend`)
    },
  )
}

export async function removeTeamMember(id: string): Promise<void> {
  return gate(
    // MOCK: removes a team member
    () => {
      write(`team_${userCompanyId()}`, read<TeamMember[]>(`team_${userCompanyId()}`, () => seedMembers).filter((member) => member.id !== id))
    },
    async () => {
      await apiClient.delete(`/recruiter/team/${id}`)
    },
  )
}

/* ---------- Jobs ---------- */

export async function getRecruiterJobs(status?: JobStatus): Promise<Job[]> {
  return gate(
    // MOCK: stands in for GET /recruiter/jobs
    () =>
      loadJobs()
        .filter((job) => job.companyId === userCompanyId() && (!status || job.status === status))
        .map((job) => decorateJob(job)),
    async () => unwrap<Job[]>(await apiClient.get('/recruiter/jobs', { params: { status } })),
  )
}

export async function getRecruiterJob(id: string): Promise<Job | undefined> {
  return gate(
    // MOCK: stands in for loading one of the recruiter's jobs for editing
    () => loadJobs().find((job) => job.id === id && job.companyId === userCompanyId()),
    async () => unwrap<Job>(await apiClient.get(`/jobs/${id}`)),
  )
}

export function jobToDraft(job: Job): PostJobDraft {
  return {
    id: job.id,
    title: job.title,
    locations: job.locations,
    workMode: job.workMode,
    jobType: job.jobType,
    employmentType: job.employmentType,
    openings: job.openings,
    experienceMin: job.experienceMin,
    experienceMax: job.experienceMax,
    skills: job.skills,
    education: job.education,
    salaryMin: job.salaryMin,
    salaryMax: job.salaryMax,
    currency: job.currency,
    salaryDisclosed: job.salaryDisclosed,
    description: job.description,
    screeningQuestions: job.screeningQuestions,
  }
}

export async function saveRecruiterJob(draft: PostJobDraft, publish: boolean): Promise<Job> {
  return gate(
    // MOCK: stands in for POST/PUT /recruiter/jobs (publish goes to review when company is pending)
    () => {
      const company = loadOwnCompany()
      if (publish && company.status !== 'APPROVED') throw new Error('Your company is awaiting admin approval. Posting is restricted.')
      const existing = draft.id ? loadJobs().find((job) => job.id === draft.id) : undefined
      const plain = draft.description.replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').trim()
      const job: Job = {
        responsibilities: [],
        preferredSkills: [],
        department: 'Engineering',
        roleCategory: 'Software Development',
        industry: company.industry,
        applicantsCount: 0,
        views: 0,
        ...existing,
        id: draft.id ?? newId('j'),
        title: draft.title,
        companyId: company.id,
        company: { id: company.id, name: company.name, logoUrl: company.logoUrl, rating: company.rating },
        experienceMin: draft.experienceMin,
        experienceMax: draft.experienceMax,
        salaryMin: draft.salaryMin,
        salaryMax: draft.salaryMax,
        salaryDisclosed: draft.salaryDisclosed,
        currency: draft.currency,
        locations: draft.locations,
        skills: draft.skills,
        jobType: draft.jobType,
        employmentType: draft.employmentType,
        workMode: draft.workMode,
        postedAt: existing?.postedAt ?? new Date().toISOString(),
        expiresAt: existing?.expiresAt ?? new Date(Date.now() + 30 * 86400000).toISOString(),
        snippet: plain.slice(0, 140),
        description: draft.description,
        education: draft.education,
        openings: draft.openings,
        screeningQuestions: draft.screeningQuestions,
        status: publish ? 'ACTIVE' : 'DRAFT',
        postedBy: company.id,
      }
      const all = loadJobs()
      saveJobs(existing ? all.map((entry) => (entry.id === job.id ? job : entry)) : [job, ...all])
      return job
    },
    async () => unwrap<Job>(draft.id ? await apiClient.put(`/recruiter/jobs/${draft.id}`, { ...draft, publish }) : await apiClient.post('/recruiter/jobs', { ...draft, publish })),
  )
}

export async function setRecruiterJobStatus(id: string, status: JobStatus): Promise<void> {
  return gate(
    // MOCK: stands in for PATCH /recruiter/jobs/:id/status
    () => {
      saveJobs(loadJobs().map((job) => (job.id === id ? { ...job, status } : job)))
    },
    async () => {
      await apiClient.patch(`/recruiter/jobs/${id}/status`, { status })
    },
  )
}

export async function duplicateJob(id: string): Promise<Job> {
  return gate(
    // MOCK: stands in for POST /recruiter/jobs/:id/duplicate
    () => {
      const source = loadJobs().find((job) => job.id === id)
      if (!source) throw new Error('Job not found')
      const copy: Job = { ...source, id: newId('j'), title: `${source.title} (Copy)`, status: 'DRAFT', applicantsCount: 0, views: 0, postedAt: new Date().toISOString() }
      saveJobs([copy, ...loadJobs()])
      return copy
    },
    async () => unwrap<Job>(await apiClient.post(`/recruiter/jobs/${id}/duplicate`)),
  )
}

export async function refreshJob(id: string): Promise<void> {
  return gate(
    // MOCK: stands in for POST /recruiter/jobs/:id/refresh (repost: new date, reactivate)
    () => {
      saveJobs(
        loadJobs().map((job) =>
          job.id === id
            ? { ...job, status: 'ACTIVE' as const, postedAt: new Date().toISOString(), expiresAt: new Date(Date.now() + 30 * 86400000).toISOString() }
            : job,
        ),
      )
    },
    async () => {
      await apiClient.post(`/recruiter/jobs/${id}/refresh`)
    },
  )
}

const DRAFT_KEY = 'post_job_draft'

/** Client-side autosave of the in-progress post-a-job form (browser only, never sent to the API). */
export function loadAutosavedDraft(): PostJobDraft | null {
  const raw = localStorage.getItem(`${DRAFT_KEY}_${userId()}`)
  return raw ? (JSON.parse(raw) as PostJobDraft) : null
}

export function autosaveDraft(draft: PostJobDraft): void {
  localStorage.setItem(`${DRAFT_KEY}_${userId()}`, JSON.stringify(draft))
}

export function clearAutosavedDraft(): void {
  localStorage.removeItem(`${DRAFT_KEY}_${userId()}`)
}

/* ---------- Dashboard ---------- */

export interface RecruiterDashboard {
  activeJobs: number
  newApplicantsToday: number
  credits: number
  companyStatus: string
  upcomingInterviews: { applicationId: string; candidateName: string; jobTitle: string; dateTime: string; mode: string }[]
  funnel: { stage: string; count: number }[]
  performance: { jobId: string; title: string; views: number; applications: number }[]
}

export async function getRecruiterDashboard(): Promise<RecruiterDashboard> {
  return gate(
    // MOCK: stands in for GET /recruiter/dashboard (computed from local data)
    () => {
      const company = loadOwnCompany()
      const jobs = loadJobs().filter((job) => job.companyId === company.id)
      const jobIds = jobs.map((job) => job.id)
      const applications = loadApplications().filter((application) => jobIds.includes(application.jobId))
      const startOfDay = new Date()
      startOfDay.setHours(0, 0, 0, 0)
      return {
        activeJobs: jobs.filter((job) => job.status === 'ACTIVE').length,
        newApplicantsToday: applications.filter((application) => new Date(application.appliedAt) >= startOfDay).length,
        credits: company.credits,
        companyStatus: company.status,
        upcomingInterviews: applications
          .filter((application) => application.interview && application.status === 'INTERVIEW_SCHEDULED')
          .map((application) => ({
            applicationId: application.id,
            candidateName: application.candidateName,
            jobTitle: application.jobTitle,
            dateTime: application.interview!.dateTime,
            mode: application.interview!.mode,
          })),
        funnel: BOARD_COLUMNS.map((column) => ({ stage: column.label, count: applications.filter((application) => application.status === column.status).length })),
        performance: jobs.filter((job) => job.status === 'ACTIVE' || job.applicantsCount > 0).map((job) => ({ jobId: job.id, title: job.title, views: job.views, applications: job.applicantsCount })),
      }
    },
    async () => unwrap<RecruiterDashboard>(await apiClient.get('/recruiter/dashboard')),
  )
}

export async function getCredits(): Promise<{ balance: number; unlockCost: number }> {
  return gate(
    // MOCK: stands in for GET /recruiter/credits
    () => ({ balance: loadOwnCompany().credits, unlockCost: UNLOCK_COST }),
    async () => unwrap(await apiClient.get('/recruiter/credits')),
  )
}

/* ---------- Applicants ---------- */

export type ApplicantFilters = Record<string, string>

// MOCK: client-side version of the applicants filter query
export function filterApplicants(all: Application[], filters: ApplicantFilters): Application[] {
  const skills = (filters.skills ?? '').split(',').map((skill) => skill.trim().toLowerCase()).filter(Boolean)
  const filtered = all.filter((application) => {
    if (filters.status && application.status !== filters.status) return false
    if (filters.experienceMin && application.experience < Number(filters.experienceMin)) return false
    if (filters.experienceMax && application.experience > Number(filters.experienceMax)) return false
    if (filters.location && !application.location.toLowerCase().includes(filters.location.toLowerCase())) return false
    if (filters.ctcMin && application.expectedCtc < Number(filters.ctcMin)) return false
    if (filters.ctcMax && application.expectedCtc > Number(filters.ctcMax)) return false
    if (skills.length && !skills.every((skill) => application.skills.some((owned) => owned.toLowerCase().includes(skill)))) return false
    if (filters.noticePeriod && application.noticePeriod !== filters.noticePeriod) return false
    if (filters.education && application.education !== filters.education) return false
    if (filters.appliedAfter && new Date(application.appliedAt) < new Date(filters.appliedAfter)) return false
    if (filters.screening && application.screening !== filters.screening) return false
    return true
  })
  return filtered.sort((first, second) => {
    if (filters.sort === 'experience') return second.experience - first.experience
    if (filters.sort === 'rating') return second.rating - first.rating
    if (filters.sort === 'date') return new Date(second.appliedAt).getTime() - new Date(first.appliedAt).getTime()
    return second.matchPercentage - first.matchPercentage
  })
}

export async function getApplicants(jobId: string, filters: ApplicantFilters): Promise<ListResult<Application>> {
  return gate(
    // MOCK: stands in for GET /recruiter/jobs/:id/applicants
    () => {
      const filtered = filterApplicants(loadApplications().filter((application) => application.jobId === jobId), filters)
      const page = Number(filters.page || 1)
      const pageSize = Number(filters.pageSize || 100)
      return { data: paginate(filtered, page, pageSize), meta: { page, pageSize, total: filtered.length } }
    },
    async () => unwrapList<Application>(await apiClient.get(`/recruiter/jobs/${jobId}/applicants`, { params: filters })),
  )
}

export async function setApplicationStatus(ids: string[], status: ApplicationStatus, message = ''): Promise<void> {
  return gate(
    // MOCK: stands in for PATCH /recruiter/applications/:id/status and /bulk-status
    () => {
      const at = new Date().toISOString()
      saveApplications(
        loadApplications().map((application) =>
          ids.includes(application.id)
            ? { ...application, status, history: [...application.history, { status, at, note: message || undefined }] }
            : application,
        ),
      )
    },
    async () => {
      if (ids.length === 1) await apiClient.patch(`/recruiter/applications/${ids[0]}/status`, { status, message })
      else await apiClient.post('/recruiter/applications/bulk-status', { applicationIds: ids, status, message })
    },
  )
}

export async function addApplicationNote(id: string, text: string): Promise<void> {
  return gate(
    // MOCK: stands in for POST /recruiter/applications/:id/notes
    () => {
      saveApplications(
        loadApplications().map((application) =>
          application.id === id ? { ...application, notes: [...application.notes, { id: newId('note'), text, at: new Date().toISOString() }] } : application,
        ),
      )
    },
    async () => {
      await apiClient.post(`/recruiter/applications/${id}/notes`, { text })
    },
  )
}

export async function setApplicationRating(id: string, rating: number): Promise<void> {
  return gate(
    // MOCK: stands in for PUT /recruiter/applications/:id/rating
    () => {
      saveApplications(loadApplications().map((application) => (application.id === id ? { ...application, rating } : application)))
    },
    async () => {
      await apiClient.put(`/recruiter/applications/${id}/rating`, { rating })
    },
  )
}

export async function scheduleInterview(id: string, interview: Interview): Promise<void> {
  return gate(
    // MOCK: stands in for POST /recruiter/applications/:id/interview
    () => {
      const at = new Date().toISOString()
      saveApplications(
        loadApplications().map((application) =>
          application.id === id
            ? { ...application, interview, status: 'INTERVIEW_SCHEDULED' as const, history: [...application.history, { status: 'INTERVIEW_SCHEDULED' as const, at }] }
            : application,
        ),
      )
    },
    async () => {
      await apiClient.post(`/recruiter/applications/${id}/interview`, interview)
    },
  )
}

export async function exportApplicantsCsv(jobId: string, filters: ApplicantFilters): Promise<void> {
  if (!USE_MOCK) {
    const res = await apiClient.get(`/recruiter/jobs/${jobId}/applicants/export`, { responseType: 'blob' })
    const url = URL.createObjectURL(res.data as Blob)
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = 'applicants.csv'
    anchor.click()
    URL.revokeObjectURL(url)
    return
  }
  // MOCK: builds the CSV in the browser instead of GET /recruiter/jobs/:id/applicants/export
  const { data } = await getApplicants(jobId, filters)
  downloadCsv('applicants.csv', [
    ['Name', 'Headline', 'Experience', 'Location', 'Current CTC', 'Expected CTC', 'Notice period', 'Match %', 'Status'],
    ...data.map((a) => [a.candidateName, a.headline, a.experience, a.location, a.currentCtc, a.expectedCtc, a.noticePeriod, a.matchPercentage, a.status]),
  ])
}

/* ---------- Candidate database ---------- */

export type CandidateResult = Candidate & { unlocked: boolean }

function maskCandidate(candidate: Candidate, unlockedIds: string[]): CandidateResult {
  const unlocked = unlockedIds.includes(candidate.id)
  if (unlocked) return { ...candidate, unlocked }
  const [local, domain] = candidate.email.split('@')
  return {
    ...candidate,
    unlocked,
    email: `${local.slice(0, 1)}*****@${domain}`,
    mobile: `${candidate.mobile.slice(0, 2)}******${candidate.mobile.slice(-2)}`,
  }
}

export async function searchCandidates(filters: Record<string, string>): Promise<ListResult<CandidateResult>> {
  return gate(
    // MOCK: stands in for GET /recruiter/candidates/search (AND/OR/NOT keyword query)
    () => {
      const unlockedIds = read<string[]>(`unlocked_${userCompanyId()}`, () => [])
      const skills = (filters.skills ?? '').split(',').map((skill) => skill.trim().toLowerCase()).filter(Boolean)
      const matched = mockCandidates.filter((candidate) => {
        const haystack = [candidate.name, candidate.headline, candidate.industry, ...candidate.skills].join(' ')
        if (!matchesBoolean(haystack, filters.q ?? '')) return false
        if (skills.length && !skills.every((skill) => candidate.skills.some((owned) => owned.toLowerCase().includes(skill)))) return false
        if (filters.experienceMin && candidate.experience < Number(filters.experienceMin)) return false
        if (filters.experienceMax && candidate.experience > Number(filters.experienceMax)) return false
        if (filters.location && !candidate.location.toLowerCase().includes(filters.location.toLowerCase())) return false
        if (filters.ctcMax && candidate.expectedCtc > Number(filters.ctcMax)) return false
        if (filters.ctcMin && candidate.expectedCtc < Number(filters.ctcMin)) return false
        if (filters.noticePeriod && candidate.noticePeriod !== filters.noticePeriod) return false
        if (filters.education && candidate.education !== filters.education) return false
        if (filters.industry && candidate.industry !== filters.industry) return false
        if (filters.lastActive) {
          const ageDays = (Date.now() - new Date(candidate.lastActive).getTime()) / 86400000
          if (ageDays > Number(filters.lastActive)) return false
        }
        return true
      })
      const page = Number(filters.page || 1)
      return { data: paginate(matched, page, PAGE_SIZE).map((candidate) => maskCandidate(candidate, unlockedIds)), meta: { page, pageSize: PAGE_SIZE, total: matched.length } }
    },
    async () => unwrapList<CandidateResult>(await apiClient.get('/recruiter/candidates/search', { params: filters })),
  )
}

export async function unlockCandidate(candidateId: string): Promise<void> {
  return gate(
    // MOCK: stands in for POST /recruiter/candidates/:id/unlock (spends credits)
    () => {
      const company = loadOwnCompany()
      const unlocked = read<string[]>(`unlocked_${company.id}`, () => [])
      if (unlocked.includes(candidateId)) return
      if (company.credits < UNLOCK_COST) throw new Error('Not enough credits to view this contact')
      write(`unlocked_${company.id}`, [...unlocked, candidateId])
      saveCompanies(loadCompanies().map((entry) => (entry.id === company.id ? { ...entry, credits: entry.credits - UNLOCK_COST } : entry)))
    },
    async () => {
      await apiClient.post(`/recruiter/candidates/${candidateId}/unlock`)
    },
  )
}

export async function inviteCandidate(candidateId: string, jobId: string, message: string): Promise<void> {
  return gate(
    // MOCK: stands in for POST /recruiter/candidates/:id/invite
    () => {
      write('invitations_sent', [{ candidateId, jobId, message, at: new Date().toISOString() }, ...read<unknown[]>('invitations_sent', () => [])])
    },
    async () => {
      await apiClient.post(`/recruiter/candidates/${candidateId}/invite`, { jobId, message })
    },
  )
}

/* ---------- Folders & saved searches ---------- */

function foldersKey(): string {
  return `folders_${userCompanyId()}`
}

const seedFolders: Folder[] = [{ id: 'f1', name: 'Frontend talent pool', candidateIds: ['u-s1', 'cand6'] }]

export async function getFolders(): Promise<Folder[]> {
  return gate(
    // MOCK: stands in for GET /recruiter/folders
    () => read<Folder[]>(foldersKey(), () => seedFolders),
    async () => unwrap<Folder[]>(await apiClient.get('/recruiter/folders')),
  )
}

export async function saveFolder(name: string, id?: string): Promise<Folder> {
  return gate(
    // MOCK: stands in for POST /recruiter/folders (and rename)
    () => {
      const all = read<Folder[]>(foldersKey(), () => seedFolders)
      if (id) {
        write(foldersKey(), all.map((folder) => (folder.id === id ? { ...folder, name } : folder)))
        return { ...all.find((folder) => folder.id === id)!, name }
      }
      const created: Folder = { id: newId('f'), name, candidateIds: [] }
      write(foldersKey(), [...all, created])
      return created
    },
    async () => unwrap<Folder>(id ? await apiClient.put(`/recruiter/folders/${id}`, { name }) : await apiClient.post('/recruiter/folders', { name })),
  )
}

export async function deleteFolder(id: string): Promise<void> {
  return gate(
    // MOCK: removes a folder
    () => {
      write(foldersKey(), read<Folder[]>(foldersKey(), () => seedFolders).filter((folder) => folder.id !== id))
    },
    async () => {
      await apiClient.delete(`/recruiter/folders/${id}`)
    },
  )
}

export async function addCandidateToFolder(folderId: string, candidateId: string): Promise<void> {
  return gate(
    // MOCK: stands in for POST /recruiter/folders/:id/candidates
    () => {
      write(
        foldersKey(),
        read<Folder[]>(foldersKey(), () => seedFolders).map((folder) =>
          folder.id === folderId && !folder.candidateIds.includes(candidateId) ? { ...folder, candidateIds: [...folder.candidateIds, candidateId] } : folder,
        ),
      )
    },
    async () => {
      await apiClient.post(`/recruiter/folders/${folderId}/candidates`, { candidateId })
    },
  )
}

export async function getFolderCandidates(folderId: string): Promise<CandidateResult[]> {
  return gate(
    // MOCK: candidates inside a folder
    () => {
      const folder = read<Folder[]>(foldersKey(), () => seedFolders).find((entry) => entry.id === folderId)
      const unlockedIds = read<string[]>(`unlocked_${userCompanyId()}`, () => [])
      return mockCandidates.filter((candidate) => folder?.candidateIds.includes(candidate.id)).map((candidate) => maskCandidate(candidate, unlockedIds))
    },
    async () => unwrap<CandidateResult[]>(await apiClient.get(`/recruiter/folders/${folderId}/candidates`)),
  )
}

const seedSearches: SavedSearch[] = [{ id: 'ss1', name: 'React seniors in Bengaluru', criteria: 'q=React&location=Bengaluru&experienceMin=4', updatedAt: new Date().toISOString() }]

export async function getSavedSearches(): Promise<SavedSearch[]> {
  return gate(
    // MOCK: saved candidate searches
    () => read<SavedSearch[]>(`searches_${userCompanyId()}`, () => seedSearches),
    async () => unwrap<SavedSearch[]>(await apiClient.get('/recruiter/folders')),
  )
}

export async function saveSearch(name: string, criteria: string): Promise<void> {
  return gate(
    // MOCK: stores a candidate search
    () => {
      write(`searches_${userCompanyId()}`, [{ id: newId('ss'), name, criteria, updatedAt: new Date().toISOString() }, ...read<SavedSearch[]>(`searches_${userCompanyId()}`, () => seedSearches)])
    },
    async () => {
      await apiClient.post('/recruiter/folders', { name })
    },
  )
}

export async function deleteSavedSearch(id: string): Promise<void> {
  return gate(
    // MOCK: removes a saved search
    () => {
      write(`searches_${userCompanyId()}`, read<SavedSearch[]>(`searches_${userCompanyId()}`, () => seedSearches).filter((entry) => entry.id !== id))
    },
    async () => {
      await apiClient.delete(`/recruiter/folders/${id}`)
    },
  )
}
