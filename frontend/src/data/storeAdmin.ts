import { apiClient, unwrap } from '../api/client'
import { getUsers, saveUser } from '../auth/auth'
import { mockAnalyticsSeries, mockJobReports, mockMaster, mockReviews, mockTopKeywords } from './mockData'
import { USE_MOCK, gate, loadApplications, loadCompanies, loadJobs, newId, read, saveCompanies, saveJobs, write } from './storeCore'
import { downloadCsv } from '../utils/format'
import type { Company, CompanyStatus, Job, JobReport, JobStatus, MasterItem, MasterType, Review, Role, User } from '../types'

export async function getAdminCompanies(status?: CompanyStatus): Promise<Company[]> {
  return gate(
    // MOCK: stands in for GET /admin/companies
    () => loadCompanies().filter((company) => !status || company.status === status),
    async () => unwrap<Company[]>(await apiClient.get('/admin/companies', { params: { status } })),
  )
}

export async function setCompanyStatus(id: string, status: CompanyStatus, reason = ''): Promise<void> {
  return gate(
    // MOCK: stands in for PATCH /admin/companies/:id/status
    () => {
      saveCompanies(loadCompanies().map((company) => (company.id === id ? { ...company, status } : company)))
    },
    async () => {
      await apiClient.patch(`/admin/companies/${id}/status`, { status, reason })
    },
  )
}

export async function adjustCompanyCredits(id: string, credits: number, quota: number): Promise<void> {
  return gate(
    // MOCK: stands in for PATCH /admin/companies/:id/credits
    () => {
      saveCompanies(loadCompanies().map((company) => (company.id === id ? { ...company, credits, quota } : company)))
    },
    async () => {
      const current = unwrap<Company>(await apiClient.get(`/admin/companies/${id}`))
      const delta = credits - (current.credits ?? 0)
      if (delta !== 0) await apiClient.post(`/admin/companies/${id}/credits`, { amount: delta, reason: 'Adjusted by admin' })
      await apiClient.patch(`/admin/companies/${id}/quota`, { jobQuota: quota })
    },
  )
}

export async function getModerationJobs(): Promise<Job[]> {
  return gate(
    // MOCK: stands in for GET /admin/jobs/moderation
    () => loadJobs().filter((job) => job.status === 'PENDING_REVIEW'),
    async () => unwrap<Job[]>(await apiClient.get('/admin/jobs/moderation')),
  )
}

export async function setJobModeration(id: string, status: JobStatus, reason = ''): Promise<void> {
  return gate(
    // MOCK: stands in for PATCH /admin/jobs/:id/status
    () => {
      saveJobs(loadJobs().map((job) => (job.id === id ? { ...job, status } : job)))
    },
    async () => {
      await apiClient.patch(`/admin/jobs/${id}/status`, { status, reason })
    },
  )
}

export async function getJobReports(): Promise<JobReport[]> {
  return gate(
    // MOCK: stands in for GET /admin/reports/job-reports
    () => read<JobReport[]>('job_reports', () => mockJobReports),
    async () => unwrap<JobReport[]>(await apiClient.get('/admin/job-reports')),
  )
}

export async function resolveReport(id: string, takeDown: boolean): Promise<void> {
  return gate(
    // MOCK: dismisses a report, or takes the job down
    () => {
      const reports = read<JobReport[]>('job_reports', () => mockJobReports)
      const target = reports.find((report) => report.id === id)
      write('job_reports', reports.map((report) => (report.id === id ? { ...report, resolved: true } : report)))
      if (takeDown && target) saveJobs(loadJobs().map((job) => (job.id === target.jobId ? { ...job, status: 'REJECTED' as const } : job)))
    },
    async () => {
      await apiClient.patch(`/admin/job-reports/${id}`, { takeDown })
    },
  )
}

export async function getAllReviews(): Promise<(Review & { companyName: string })[]> {
  return gate(
    // MOCK: review moderation queue
    () =>
      read<Review[]>('reviews', () => mockReviews).map((review) => ({
        ...review,
        companyName: loadCompanies().find((company) => company.id === review.companyId)?.name ?? '',
      })),
    async () => unwrap(await apiClient.get('/admin/reviews')),
  )
}

export async function deleteReview(id: string): Promise<void> {
  return gate(
    // MOCK: removes a review
    () => {
      write('reviews', read<Review[]>('reviews', () => mockReviews).filter((review) => review.id !== id))
    },
    async () => {
      await apiClient.patch(`/admin/reviews/${id}`, { status: 'REJECTED' })
    },
  )
}

/* ---------- Master data ---------- */

export async function saveMasterItem(type: MasterType, item: { id?: string; name: string; synonyms?: string }): Promise<void> {
  return gate(
    // MOCK: stands in for POST/PUT /admin/master/:type
    () => {
      const all = read<MasterItem[]>(`master_${type}`, () => mockMaster[type])
      if (item.id) write(`master_${type}`, all.map((entry) => (entry.id === item.id ? { ...entry, ...item } : entry)))
      else write(`master_${type}`, [...all, { id: newId(type), name: item.name, synonyms: item.synonyms }])
    },
    async () => {
      if (item.id) await apiClient.put(`/admin/master/${type}/${item.id}`, item)
      else await apiClient.post(`/admin/master/${type}`, item)
    },
  )
}

export async function deleteMasterItem(type: MasterType, id: string): Promise<void> {
  return gate(
    // MOCK: stands in for DELETE /admin/master/:type/:id
    () => {
      write(`master_${type}`, read<MasterItem[]>(`master_${type}`, () => mockMaster[type]).filter((entry) => entry.id !== id))
    },
    async () => {
      await apiClient.delete(`/admin/master/${type}/${id}`)
    },
  )
}

export async function importMasterItems(type: MasterType, names: string[]): Promise<number> {
  return gate(
    // MOCK: stands in for a bulk CSV import endpoint (skips duplicates)
    () => {
      const all = read<MasterItem[]>(`master_${type}`, () => mockMaster[type])
      const fresh = names.filter((name) => name && !all.some((entry) => entry.name.toLowerCase() === name.toLowerCase()))
      write(`master_${type}`, [...all, ...fresh.map((name) => ({ id: newId(type), name }))])
      return fresh.length
    },
    async () => {
      let imported = 0
      for (const name of names) {
        try {
          await apiClient.post(`/admin/master/${type}`, { name })
          imported += 1
        } catch {
          // duplicates / invalid names are skipped
        }
      }
      return imported
    },
  )
}

/* ---------- Users & analytics ---------- */

export async function getUserList(role?: Role, query = ''): Promise<User[]> {
  return gate(
    // MOCK: stands in for GET /admin/users
    () => {
      const text = query.toLowerCase()
      return getUsers()
        .filter((user) => (!role || user.role === role) && (user.name.toLowerCase().includes(text) || user.email.toLowerCase().includes(text)))
        .map(({ password: _password, ...user }) => user)
    },
    async () => unwrap<User[]>(await apiClient.get('/admin/users', { params: { role, q: query } })),
  )
}

export async function setUserBlocked(id: string, blocked: boolean): Promise<void> {
  return gate(
    // MOCK: stands in for PATCH /admin/users/:id/status
    () => {
      const user = getUsers().find((entry) => entry.id === id)
      if (user) saveUser({ ...user, blocked })
    },
    async () => {
      if (blocked) await apiClient.patch(`/admin/users/${id}/block`, { reason: 'Blocked by admin' })
      else await apiClient.patch(`/admin/users/${id}/unblock`)
    },
  )
}

export interface Analytics {
  series: { date: string; registrations: number; jobs: number; applications: number }[]
  totals: { registrations: number; jobs: number; applications: number }
  topKeywords: { keyword: string; count: number }[]
  topCompanies: { name: string; applications: number; jobs: number }[]
}

export async function getAnalytics(from: string, to: string): Promise<Analytics> {
  return gate(
    // MOCK: stands in for GET /admin/analytics (series is generated sample data)
    () => {
      const series = mockAnalyticsSeries.filter((point) => (!from || point.date >= from) && (!to || point.date <= to))
      const jobs = loadJobs()
      const applications = loadApplications()
      const topCompanies = loadCompanies()
        .map((company) => ({
          name: company.name,
          jobs: jobs.filter((job) => job.companyId === company.id).length,
          applications: jobs.filter((job) => job.companyId === company.id).reduce((sum, job) => sum + job.applicantsCount, 0),
        }))
        .sort((first, second) => second.applications - first.applications)
        .slice(0, 5)
      return {
        series,
        totals: {
          registrations: series.reduce((sum, point) => sum + point.registrations, 0),
          jobs: series.reduce((sum, point) => sum + point.jobs, 0),
          applications: series.reduce((sum, point) => sum + point.applications, 0) + applications.length * 0,
        },
        topKeywords: mockTopKeywords,
        topCompanies,
      }
    },
    async () => unwrap<Analytics>(await apiClient.get('/admin/analytics', { params: { from, to } })),
  )
}

export async function exportAnalyticsCsv(from: string, to: string): Promise<void> {
  if (!USE_MOCK) {
    const res = await apiClient.get('/admin/analytics/export', { params: { from, to }, responseType: 'blob' })
    const url = URL.createObjectURL(res.data as Blob)
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = 'analytics.csv'
    anchor.click()
    URL.revokeObjectURL(url)
    return
  }
  const analytics = await getAnalytics(from, to)
  downloadCsv('analytics.csv', [
    ['Date', 'Registrations', 'Jobs posted', 'Applications'],
    ...analytics.series.map((point) => [point.date, point.registrations, point.jobs, point.applications]),
  ])
}
