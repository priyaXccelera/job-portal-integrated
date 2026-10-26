export type Role = 'JOB_SEEKER' | 'RECRUITER' | 'ADMIN'

export type ApplicationStatus =
  | 'APPLIED'
  | 'VIEWED'
  | 'SHORTLISTED'
  | 'INTERVIEW_SCHEDULED'
  | 'ON_HOLD'
  | 'OFFERED'
  | 'HIRED'
  | 'REJECTED'
  | 'WITHDRAWN'

export type JobStatus =
  | 'DRAFT'
  | 'PENDING_REVIEW'
  | 'ACTIVE'
  | 'PAUSED'
  | 'CLOSED'
  | 'EXPIRED'
  | 'REJECTED'

export type CompanyStatus = 'PENDING' | 'APPROVED' | 'REJECTED' | 'BLOCKED'

export interface User {
  id: string
  name: string
  email: string
  mobile: string
  role: Role
  companyId?: string
  blocked?: boolean
  emailVerified?: boolean
  mobileVerified?: boolean
}

export interface MockUser extends User {
  password: string
}

export interface Session {
  token: string
  refreshToken: string
  user: User
}

export interface Company {
  id: string
  name: string
  logoUrl: string
  bannerUrl: string
  rating: number
  reviewsCount: number
  industry: string
  companyType: string
  size: string
  headquarters: string
  website: string
  about: string
  benefits: string[]
  gallery: string[]
  status: CompanyStatus
  credits: number
  quota: number
  followers: number
}

export interface ScreeningQuestion {
  id: string
  text: string
  type: 'text' | 'yesno' | 'choice'
  options?: string[]
  required: boolean
}

export interface MatchScore {
  percentage: number
  matchingSkills: string[]
  missingSkills: string[]
}

export interface Job {
  id: string
  title: string
  companyId: string
  company: { id: string; name: string; logoUrl: string; rating: number }
  experienceMin: number
  experienceMax: number
  salaryMin: number
  salaryMax: number
  salaryDisclosed: boolean
  currency: string
  locations: string[]
  skills: string[]
  preferredSkills: string[]
  jobType: string
  employmentType: string
  workMode: string
  postedAt: string
  expiresAt: string
  snippet: string
  description: string
  responsibilities: string[]
  education: string
  openings: number
  department: string
  roleCategory: string
  industry: string
  screeningQuestions: ScreeningQuestion[]
  applicantsCount: number
  views: number
  status: JobStatus
  postedBy: string
  isSaved?: boolean
  isApplied?: boolean
  applicationStatus?: ApplicationStatus
  matchScore?: MatchScore
}

export interface Facets {
  [group: string]: Record<string, number>
}

export interface ListMeta {
  page: number
  pageSize: number
  total: number
  facets?: Facets
}

export interface ListResult<T> {
  data: T[]
  meta: ListMeta
}

export interface Review {
  id: string
  companyId: string
  author: string
  rating: number
  title: string
  body: string
  createdAt: string
}

export interface HistoryEntry {
  status: ApplicationStatus
  at: string
  note?: string
}

export interface Interview {
  dateTime: string
  mode: string
  linkOrAddress: string
  notes: string
  response?: 'CONFIRM' | 'RESCHEDULE'
}

export interface Application {
  id: string
  jobId: string
  jobTitle: string
  company: { id: string; name: string; logoUrl: string }
  candidateId: string
  candidateName: string
  headline: string
  experience: number
  location: string
  currentCtc: number
  expectedCtc: number
  noticePeriod: string
  education: string
  skills: string[]
  matchPercentage: number
  rating: number
  status: ApplicationStatus
  appliedAt: string
  coverNote: string
  resumeName: string
  answers: { questionId: string; question: string; answer: string }[]
  notes: { id: string; text: string; at: string }[]
  history: HistoryEntry[]
  interview?: Interview
  screening: 'in' | 'out'
}

export interface ProfileItem {
  id: string
  title: string
  subtitle: string
  period: string
  description: string
}

export interface Resume {
  id: string
  name: string
  size: number
  uploadedAt: string
  isDefault: boolean
}

export interface Profile {
  userId: string
  name: string
  photoUrl: string
  headline: string
  skills: string[]
  employments: ProfileItem[]
  educations: ProfileItem[]
  projects: ProfileItem[]
  certifications: ProfileItem[]
  languages: ProfileItem[]
  onlineProfiles: ProfileItem[]
  personal: { dob: string; gender: string; location: string; maritalStatus: string }
  career: {
    preferredLocations: string
    expectedSalary: string
    jobType: string
    employmentType: string
    industry: string
    noticePeriod: string
  }
  visibility: 'PUBLIC' | 'RECRUITERS_ONLY' | 'PRIVATE'
  hideFromCompanies: string
  views: number
  viewers: { id: string; name: string; company: string; at: string }[]
}

export interface JobAlert {
  id: string
  keywords: string
  locations: string
  experience: string
  salary: string
  frequency: 'DAILY' | 'WEEKLY' | 'INSTANT'
  active: boolean
}

export interface NotificationItem {
  id: string
  type: 'APPLICATION' | 'JOB' | 'MESSAGE' | 'SYSTEM'
  title: string
  body: string
  createdAt: string
  read: boolean
  link?: string
}

export interface NotificationPrefs {
  email: boolean
  sms: boolean
  inApp: boolean
  jobAlerts: boolean
  applicationUpdates: boolean
  messages: boolean
  frequency: 'INSTANT' | 'DAILY' | 'WEEKLY'
}

export interface ChatMessage {
  id: string
  from: 'me' | 'them'
  text: string
  at: string
}

export interface Thread {
  id: string
  participant: string
  subtitle: string
  userIds: string[]
  unread: number
  messages: ChatMessage[]
}

export interface Candidate {
  id: string
  name: string
  headline: string
  experience: number
  location: string
  currentCtc: number
  expectedCtc: number
  noticePeriod: string
  education: string
  industry: string
  skills: string[]
  lastActive: string
  email: string
  mobile: string
}

export interface Folder {
  id: string
  name: string
  candidateIds: string[]
}

export interface SavedSearch {
  id: string
  name: string
  criteria: string
  updatedAt: string
}

export interface TeamMember {
  id: string
  name: string
  email: string
  role: string
}

export interface Invitation {
  id: string
  email: string
  sentAt: string
}

export interface JobReport {
  id: string
  jobId: string
  jobTitle: string
  reason: string
  note: string
  reportedBy: string
  createdAt: string
  resolved: boolean
}

export interface MasterItem {
  id: string
  name: string
  synonyms?: string
}

export type MasterType =
  | 'skills'
  | 'industries'
  | 'departments'
  | 'role-categories'
  | 'locations'
  | 'degrees'

export interface PostJobDraft {
  id?: string
  title: string
  locations: string[]
  workMode: string
  jobType: string
  employmentType: string
  openings: number
  experienceMin: number
  experienceMax: number
  skills: string[]
  education: string
  salaryMin: number
  salaryMax: number
  currency: string
  salaryDisclosed: boolean
  description: string
  screeningQuestions: ScreeningQuestion[]
}

export interface ApiFieldError {
  field: string
  message: string
}
