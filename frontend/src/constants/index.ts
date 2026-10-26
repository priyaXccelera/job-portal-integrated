import type { ApplicationStatus, JobStatus } from '../types'

export const PAGE_SIZE = 8
export const OTP_LENGTH = 6
export const OTP_RESEND_SECONDS = 30
export const MAX_RESUME_BYTES = 2 * 1024 * 1024
export const ALLOWED_RESUME_EXTENSIONS = ['pdf', 'doc', 'docx']
export const DEMO_PASSWORD = 'Password@123'
export const DEMO_OTP = '123456'

export const JOB_TYPES = ['Full Time', 'Part Time', 'Contract', 'Internship']
export const EMPLOYMENT_TYPES = ['Permanent', 'Temporary', 'Freelance']
export const WORK_MODES = ['On-site', 'Hybrid', 'Remote']
export const EDUCATION_LEVELS = ['Any Graduate', 'B.Tech/B.E.', 'MBA/PGDM', 'M.Tech', 'B.Com', 'MBBS', 'Diploma']
export const NOTICE_PERIODS = ['Immediate', '15 days', '30 days', '60 days', '90 days']
export const FRESHNESS_OPTIONS = [
  { value: '1', label: 'Last 24 hours' },
  { value: '3', label: 'Last 3 days' },
  { value: '7', label: 'Last 7 days' },
  { value: '15', label: 'Last 15 days' },
  { value: '30', label: 'Last 30 days' },
]
export const POPULAR_CATEGORIES = ['IT', 'Sales', 'Marketing', 'Finance', 'HR', 'Engineering', 'Healthcare', 'Design', 'Operations']

export const APPLICATION_STAGES: ApplicationStatus[] = [
  'APPLIED',
  'VIEWED',
  'SHORTLISTED',
  'INTERVIEW_SCHEDULED',
  'OFFERED',
]

export const ALL_APPLICATION_STATUSES: ApplicationStatus[] = [
  'APPLIED',
  'VIEWED',
  'SHORTLISTED',
  'INTERVIEW_SCHEDULED',
  'ON_HOLD',
  'OFFERED',
  'HIRED',
  'REJECTED',
  'WITHDRAWN',
]

export const BOARD_COLUMNS: { status: ApplicationStatus; label: string }[] = [
  { status: 'APPLIED', label: 'Applied' },
  { status: 'VIEWED', label: 'Viewed' },
  { status: 'SHORTLISTED', label: 'Shortlisted' },
  { status: 'INTERVIEW_SCHEDULED', label: 'Interview' },
  { status: 'OFFERED', label: 'Offered' },
  { status: 'HIRED', label: 'Hired' },
  { status: 'REJECTED', label: 'Rejected' },
]

export const RECRUITER_JOB_TABS: JobStatus[] = ['ACTIVE', 'DRAFT', 'PAUSED', 'CLOSED', 'EXPIRED', 'REJECTED']

export const STATUS_LABELS: Record<string, string> = {
  APPLIED: 'Applied',
  VIEWED: 'Viewed',
  SHORTLISTED: 'Shortlisted',
  INTERVIEW_SCHEDULED: 'Interview',
  ON_HOLD: 'On hold',
  OFFERED: 'Offered',
  HIRED: 'Hired',
  REJECTED: 'Rejected',
  WITHDRAWN: 'Withdrawn',
  DRAFT: 'Draft',
  PENDING_REVIEW: 'Pending review',
  ACTIVE: 'Active',
  PAUSED: 'Paused',
  CLOSED: 'Closed',
  EXPIRED: 'Expired',
  PENDING: 'Pending',
  APPROVED: 'Approved',
  BLOCKED: 'Blocked',
}

export const REPORT_REASONS = ['Fake or misleading job', 'Asking for money', 'Discriminatory content', 'Duplicate posting', 'Other']
export const POPULAR_LOCATIONS = ['Bengaluru', 'Mumbai', 'Delhi NCR', 'Hyderabad', 'Pune', 'Chennai', 'Kolkata', 'Remote']
export const POPULAR_SKILLS = ['React', 'Java', 'Python', 'SQL', 'AWS', 'Figma', 'SEO', 'Excel']
