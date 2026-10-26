// MOCK DATA — placeholder records for local development only.
// Replace with real API data before production use.
import type {
  Application,
  ApplicationStatus,
  Candidate,
  ChatMessage,
  Company,
  Job,
  JobAlert,
  JobReport,
  MasterItem,
  MasterType,
  MockUser,
  NotificationItem,
  Profile,
  Review,
  ScreeningQuestion,
  Thread,
} from '../types'
import { DEMO_PASSWORD } from '../constants'

const DAY_MS = 86400000

function daysAgo(days: number): string {
  return new Date(Date.now() - days * DAY_MS).toISOString()
}

function daysAhead(days: number): string {
  return new Date(Date.now() + days * DAY_MS).toISOString()
}

function svgUrl(svg: string): string {
  return `data:image/svg+xml;utf8,${encodeURIComponent(svg)}`
}

function makeLogo(name: string, hue: number): string {
  const initials = name
    .split(' ')
    .map((word) => word[0])
    .join('')
    .slice(0, 2)
    .toUpperCase()
  return svgUrl(
    `<svg xmlns="http://www.w3.org/2000/svg" width="96" height="96"><rect width="96" height="96" rx="16" fill="hsl(${hue},65%,45%)"/><text x="48" y="60" font-size="34" font-family="Arial" font-weight="700" fill="#fff" text-anchor="middle">${initials}</text></svg>`,
  )
}

function makeBanner(hue: number): string {
  return svgUrl(
    `<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="240"><defs><linearGradient id="g" x1="0" x2="1"><stop offset="0" stop-color="hsl(${hue},65%,40%)"/><stop offset="1" stop-color="hsl(${hue + 40},70%,55%)"/></linearGradient></defs><rect width="1200" height="240" fill="url(#g)"/></svg>`,
  )
}

function makeGallery(hue: number, index: number): string {
  return svgUrl(
    `<svg xmlns="http://www.w3.org/2000/svg" width="400" height="260"><rect width="400" height="260" fill="hsl(${hue + index * 25},55%,${60 + index * 4}%)"/></svg>`,
  )
}

export const mockUsers: MockUser[] = [
  { id: 'u-admin', name: 'Aarav Admin', email: 'admin@jobportal.com', mobile: '9000000001', role: 'ADMIN', password: DEMO_PASSWORD, emailVerified: true, mobileVerified: true },
  { id: 'u-r1', name: 'Riya Recruiter', email: 'recruiter1@company.com', mobile: '9000000002', role: 'RECRUITER', companyId: 'c1', password: DEMO_PASSWORD, emailVerified: true, mobileVerified: true },
  { id: 'u-r2', name: 'Rohan Hiring', email: 'recruiter2@company.com', mobile: '9000000003', role: 'RECRUITER', companyId: 'c12', password: DEMO_PASSWORD, emailVerified: true, mobileVerified: true },
  { id: 'u-s1', name: 'Priya Sharma', email: 'seeker1@mail.com', mobile: '9100000001', role: 'JOB_SEEKER', password: DEMO_PASSWORD, emailVerified: true, mobileVerified: true },
  { id: 'u-s2', name: 'Arjun Mehta', email: 'seeker2@mail.com', mobile: '9100000002', role: 'JOB_SEEKER', password: DEMO_PASSWORD, emailVerified: true, mobileVerified: true },
  { id: 'u-s3', name: 'Sneha Iyer', email: 'seeker3@mail.com', mobile: '9100000003', role: 'JOB_SEEKER', password: DEMO_PASSWORD, emailVerified: true, mobileVerified: true },
  { id: 'u-s4', name: 'Vikram Singh', email: 'seeker4@mail.com', mobile: '9100000004', role: 'JOB_SEEKER', password: DEMO_PASSWORD, emailVerified: true, mobileVerified: true },
  { id: 'u-s5', name: 'Neha Gupta', email: 'seeker5@mail.com', mobile: '9100000005', role: 'JOB_SEEKER', password: DEMO_PASSWORD, emailVerified: true, mobileVerified: true },
]

const companySeeds: [string, string, string, string, string][] = [
  ['TechNova Solutions', 'IT Services', 'Corporate', 'Bengaluru', '10,000+'],
  ['FinSpark Bank', 'Banking & Finance', 'Corporate', 'Mumbai', '5,000+'],
  ['MediCare Plus', 'Healthcare', 'Corporate', 'Delhi NCR', '1,000-5,000'],
  ['ShopEase', 'E-commerce', 'Startup', 'Bengaluru', '500-1,000'],
  ['EduBright', 'Education', 'Startup', 'Pune', '200-500'],
  ['BuildRight Engineering', 'Manufacturing', 'MNC', 'Chennai', '10,000+'],
  ['CloudPeak', 'Software Product', 'MNC', 'Hyderabad', '5,000+'],
  ['GreenGrid Energy', 'Energy', 'Corporate', 'Kolkata', '1,000-5,000'],
  ['AdVantage Media', 'Marketing', 'Startup', 'Mumbai', '50-200'],
  ['RetailHub', 'Retail', 'Corporate', 'Delhi NCR', '5,000+'],
  ['DataWave Analytics', 'Software Product', 'Startup', 'Pune', '200-500'],
  ['Zenith Logistics', 'Logistics', 'Startup', 'Hyderabad', '50-200'],
]

export const mockCompanies: Company[] = companySeeds.map(([name, industry, companyType, headquarters, size], index) => {
  const hue = (index * 37) % 360
  return {
    id: `c${index + 1}`,
    name,
    logoUrl: makeLogo(name, hue),
    bannerUrl: makeBanner(hue),
    rating: Number((3.4 + ((index * 7) % 15) / 10).toFixed(1)),
    reviewsCount: 40 + index * 13,
    industry,
    companyType,
    size,
    headquarters,
    website: `https://www.${name.toLowerCase().replace(/[^a-z]/g, '')}.example.com`,
    about: `${name} is a leading ${industry.toLowerCase()} organisation headquartered in ${headquarters}. We build products people love, invest in learning and believe in a transparent, collaborative culture.`,
    benefits: ['Health insurance', 'Flexible working hours', 'Learning budget', 'Paid parental leave'],
    gallery: [0, 1, 2, 3].map((galleryIndex) => makeGallery(hue, galleryIndex)),
    status: index === 11 ? 'PENDING' : 'APPROVED',
    credits: 120 - index * 5,
    quota: 25,
    followers: 1200 + index * 310,
  }
})

interface JobTemplate {
  title: string
  department: string
  roleCategory: string
  industry: string
  skills: string[]
  preferred: string[]
  education: string
}

const templates: JobTemplate[] = [
  { title: 'Senior React Developer', department: 'Engineering', roleCategory: 'Software Development', industry: 'Software Product', skills: ['React', 'TypeScript', 'JavaScript', 'Redux', 'CSS'], preferred: ['Next.js', 'Testing'], education: 'B.Tech/B.E.' },
  { title: 'Java Backend Engineer', department: 'Engineering', roleCategory: 'Software Development', industry: 'IT Services', skills: ['Java', 'Spring Boot', 'SQL', 'Microservices', 'AWS'], preferred: ['Kafka', 'Docker'], education: 'B.Tech/B.E.' },
  { title: 'Data Analyst', department: 'Data Science', roleCategory: 'Analytics', industry: 'Banking & Finance', skills: ['SQL', 'Python', 'Excel', 'Tableau', 'Statistics'], preferred: ['Power BI'], education: 'Any Graduate' },
  { title: 'Digital Marketing Manager', department: 'Marketing', roleCategory: 'Digital Marketing', industry: 'Marketing', skills: ['SEO', 'Google Ads', 'Content Strategy', 'Analytics', 'Social Media'], preferred: ['HubSpot'], education: 'MBA/PGDM' },
  { title: 'Sales Executive', department: 'Sales', roleCategory: 'Business Development', industry: 'Retail', skills: ['Lead Generation', 'CRM', 'Negotiation', 'B2B Sales', 'Communication'], preferred: ['Salesforce'], education: 'Any Graduate' },
  { title: 'HR Business Partner', department: 'Human Resources', roleCategory: 'HR Operations', industry: 'IT Services', skills: ['Recruitment', 'Employee Relations', 'Payroll', 'HRIS', 'Communication'], preferred: ['Labour Law'], education: 'MBA/PGDM' },
  { title: 'Financial Analyst', department: 'Finance', roleCategory: 'Accounting', industry: 'Banking & Finance', skills: ['Financial Modeling', 'Excel', 'Budgeting', 'SAP', 'Forecasting'], preferred: ['CFA'], education: 'B.Com' },
  { title: 'UI/UX Designer', department: 'Design', roleCategory: 'Product Design', industry: 'E-commerce', skills: ['Figma', 'Prototyping', 'User Research', 'Wireframing', 'Design Systems'], preferred: ['Motion Design'], education: 'Any Graduate' },
  { title: 'DevOps Engineer', department: 'Engineering', roleCategory: 'DevOps', industry: 'Software Product', skills: ['AWS', 'Docker', 'Kubernetes', 'CI/CD', 'Terraform'], preferred: ['Prometheus'], education: 'B.Tech/B.E.' },
  { title: 'Staff Nurse', department: 'Healthcare', roleCategory: 'Nursing', industry: 'Healthcare', skills: ['Patient Care', 'Clinical Skills', 'ICU', 'Communication', 'EMR'], preferred: ['BLS Certified'], education: 'Diploma' },
  { title: 'Mechanical Design Engineer', department: 'Engineering', roleCategory: 'Mechanical', industry: 'Manufacturing', skills: ['AutoCAD', 'SolidWorks', 'GD&T', 'CAD', 'Manufacturing'], preferred: ['ANSYS'], education: 'B.Tech/B.E.' },
  { title: 'Product Manager', department: 'Product', roleCategory: 'Product Management', industry: 'Software Product', skills: ['Roadmapping', 'Agile', 'Analytics', 'Stakeholder Management', 'SQL'], preferred: ['A/B Testing'], education: 'MBA/PGDM' },
  { title: 'QA Automation Engineer', department: 'Engineering', roleCategory: 'Quality Assurance', industry: 'IT Services', skills: ['Selenium', 'Java', 'Testing', 'Cypress', 'API Testing'], preferred: ['Playwright'], education: 'B.Tech/B.E.' },
  { title: 'Customer Support Lead', department: 'Operations', roleCategory: 'Customer Success', industry: 'E-commerce', skills: ['Customer Service', 'Zendesk', 'Communication', 'Escalation', 'SLA'], preferred: ['Coaching'], education: 'Any Graduate' },
]

const locationPool = ['Bengaluru', 'Mumbai', 'Delhi NCR', 'Hyderabad', 'Pune', 'Chennai', 'Kolkata', 'Remote']
const jobTypes = ['Full Time', 'Full Time', 'Contract', 'Part Time', 'Internship']
const workModes = ['Hybrid', 'On-site', 'Remote']

const specialStatuses: Record<number, Job['status']> = {
  11: 'CLOSED',
  19: 'EXPIRED',
  21: 'PENDING_REVIEW',
  24: 'PAUSED',
  30: 'DRAFT',
  31: 'EXPIRED',
  32: 'CLOSED',
  33: 'REJECTED',
}

function buildQuestions(index: number): ScreeningQuestion[] {
  if (index % 3 !== 0) return []
  return [
    { id: `q1-${index}`, text: 'Briefly describe your most relevant project.', type: 'text', required: true },
    { id: `q2-${index}`, text: 'Are you comfortable working from the office location?', type: 'yesno', required: true },
    { id: `q3-${index}`, text: 'Which best describes your experience level?', type: 'choice', options: ['Beginner', 'Intermediate', 'Expert'], required: false },
  ]
}

export const mockJobs: Job[] = Array.from({ length: 34 }, (_, index) => {
  const template = templates[index % templates.length]
  const companyIndex = index >= 30 ? 0 : index % 12
  const company = mockCompanies[companyIndex]
  const experienceMin = index % 6
  const salaryMin = 3 + (index % 9) * 2
  const primaryLocation = locationPool[index % locationPool.length]
  const secondLocation = locationPool[(index + 3) % locationPool.length]
  const workMode = workModes[index % 3]
  const openings = 1 + (index % 5)
  return {
    id: `j${index + 1}`,
    title: template.title,
    companyId: company.id,
    company: { id: company.id, name: company.name, logoUrl: company.logoUrl, rating: company.rating },
    experienceMin,
    experienceMax: experienceMin + 3 + (index % 3),
    salaryMin,
    salaryMax: salaryMin + 4 + (index % 4),
    salaryDisclosed: index % 7 !== 3,
    currency: 'INR',
    locations: index % 2 === 0 ? [primaryLocation, secondLocation] : [primaryLocation],
    skills: template.skills,
    preferredSkills: template.preferred,
    jobType: jobTypes[index % jobTypes.length],
    employmentType: index % 8 === 5 ? 'Temporary' : 'Permanent',
    workMode,
    postedAt: daysAgo(index % 20),
    expiresAt: daysAhead(30 - (index % 20)),
    snippet: `${company.name} is hiring a ${template.title} to join the ${template.department} team. Work on impactful problems with a collaborative team.`,
    description: `${company.name} is looking for a motivated ${template.title} for our ${primaryLocation} team. You will own deliverables end to end, collaborate with cross-functional partners and help us raise the bar on quality.`,
    responsibilities: [
      `Own day-to-day ${template.department.toLowerCase()} deliverables with high quality`,
      'Collaborate with cross-functional teams to plan and ship work',
      'Mentor junior team members and share knowledge',
      'Continuously improve processes and tooling',
    ],
    education: template.education,
    openings,
    department: template.department,
    roleCategory: template.roleCategory,
    industry: template.industry,
    screeningQuestions: buildQuestions(index),
    applicantsCount: 12 + ((index * 17) % 120),
    views: 150 + ((index * 53) % 900),
    status: specialStatuses[index] ?? 'ACTIVE',
    postedBy: company.id,
  }
})

export const mockReviews: Review[] = mockCompanies.flatMap((company, index) => [
  { id: `r${index}-1`, companyId: company.id, author: 'Current Employee', rating: 4, title: 'Great learning culture', body: 'Supportive managers and good work-life balance. Growth depends on the team you join.', createdAt: daysAgo(10 + index) },
  { id: `r${index}-2`, companyId: company.id, author: 'Former Employee', rating: 3, title: 'Decent place to start a career', body: 'Good brand name and exposure. Compensation reviews could be more frequent.', createdAt: daysAgo(40 + index) },
])

const personNames = [
  'Priya Sharma', 'Arjun Mehta', 'Sneha Iyer', 'Vikram Singh', 'Neha Gupta', 'Rahul Verma', 'Anjali Nair',
  'Karan Malhotra', 'Divya Reddy', 'Amit Patel', 'Pooja Joshi', 'Sanjay Kulkarni', 'Meera Das', 'Rohit Bansal',
]
const candidateIds = ['u-s1', 'u-s2', 'u-s3', 'u-s4', 'u-s5']

export const mockCandidates: Candidate[] = personNames.map((name, index) => {
  const template = templates[index % templates.length]
  return {
    id: candidateIds[index] ?? `cand${index + 1}`,
    name,
    headline: `${template.title} with ${index % 8 + 1} years of experience`,
    experience: (index % 8) + 1,
    location: locationPool[index % 7],
    currentCtc: 4 + index,
    expectedCtc: 6 + index * 1.5,
    noticePeriod: ['Immediate', '15 days', '30 days', '60 days', '90 days'][index % 5],
    education: template.education,
    industry: template.industry,
    skills: template.skills,
    lastActive: daysAgo(index % 12),
    email: `${name.toLowerCase().replace(' ', '.')}@mail.com`,
    mobile: `98${String(10000000 + index * 1111111).slice(0, 8)}`,
  }
})

const stageOrder: ApplicationStatus[] = ['APPLIED', 'VIEWED', 'SHORTLISTED', 'INTERVIEW_SCHEDULED', 'OFFERED', 'HIRED']

function buildHistory(status: ApplicationStatus, appliedDaysAgo: number) {
  const reached = stageOrder.indexOf(status)
  const stages: ApplicationStatus[] = reached >= 0 ? stageOrder.slice(0, reached + 1) : ['APPLIED', status]
  return stages.map((stage, stageIndex) => ({
    status: stage,
    at: daysAgo(Math.max(appliedDaysAgo - stageIndex * 2, 0)),
  }))
}

function buildApplication(
  id: string,
  job: Job,
  candidate: Candidate,
  status: ApplicationStatus,
  appliedDaysAgo: number,
): Application {
  return {
    id,
    jobId: job.id,
    jobTitle: job.title,
    company: { id: job.company.id, name: job.company.name, logoUrl: job.company.logoUrl },
    candidateId: candidate.id,
    candidateName: candidate.name,
    headline: candidate.headline,
    experience: candidate.experience,
    location: candidate.location,
    currentCtc: candidate.currentCtc,
    expectedCtc: candidate.expectedCtc,
    noticePeriod: candidate.noticePeriod,
    education: candidate.education,
    skills: candidate.skills,
    matchPercentage: 55 + ((candidate.experience * 7 + job.experienceMin * 3) % 45),
    rating: (candidate.experience % 5) + 1,
    status,
    appliedAt: daysAgo(appliedDaysAgo),
    coverNote: 'I am excited about this opportunity and believe my background is a strong fit.',
    resumeName: `${candidate.name.replace(' ', '_')}_Resume.pdf`,
    answers: job.screeningQuestions.map((question) => ({
      questionId: question.id,
      question: question.text,
      answer: question.type === 'yesno' ? 'Yes' : question.type === 'choice' ? 'Intermediate' : 'Built a dashboard used by 200+ people.',
    })),
    notes: [],
    history: buildHistory(status, appliedDaysAgo),
    interview:
      status === 'INTERVIEW_SCHEDULED'
        ? { dateTime: daysAhead(3), mode: 'Video call', linkOrAddress: 'https://meet.example.com/interview', notes: 'Technical round, 45 minutes' }
        : undefined,
    screening: candidate.experience % 4 === 0 ? 'out' : 'in',
  }
}

const seekerOneStatuses: ApplicationStatus[] = ['APPLIED', 'VIEWED', 'SHORTLISTED', 'INTERVIEW_SCHEDULED', 'OFFERED', 'REJECTED', 'WITHDRAWN']
const applicantStatuses: ApplicationStatus[] = ['APPLIED', 'VIEWED', 'SHORTLISTED', 'INTERVIEW_SCHEDULED', 'OFFERED', 'HIRED', 'REJECTED', 'APPLIED', 'VIEWED', 'APPLIED']

const seekerOneApplications = seekerOneStatuses.map((status, index) =>
  buildApplication(`a-s1-${index}`, mockJobs[index + 1], mockCandidates[0], status, 12 - index),
)

const recruiterJobIndexes = [0, 12, 24, 31]
const recruiterApplications = recruiterJobIndexes.flatMap((jobIndex) =>
  applicantStatuses.map((status, offset) =>
    buildApplication(`a-${jobIndex}-${offset}`, mockJobs[jobIndex], mockCandidates[offset + 1], status, 9 - (offset % 8)),
  ),
)

export const mockApplications: Application[] = [...seekerOneApplications, ...recruiterApplications]

const blankItems = { employments: [], educations: [], projects: [], certifications: [], languages: [], onlineProfiles: [] }

export const mockProfiles: Profile[] = candidateIds.map((userId, index) => ({
  userId,
  name: mockCandidates[index].name,
  photoUrl: '',
  headline: index === 0 ? 'Frontend Engineer | React, TypeScript' : '',
  skills: index === 0 ? ['React', 'JavaScript', 'CSS', 'Node.js'] : [],
  ...blankItems,
  employments:
    index === 0
      ? [{ id: 'emp1', title: 'Frontend Engineer', subtitle: 'WebWorks Pvt Ltd', period: '2021 - Present', description: 'Building customer facing web apps.' }]
      : [],
  educations:
    index === 0
      ? [{ id: 'edu1', title: 'B.Tech Computer Science', subtitle: 'NIT Trichy', period: '2017 - 2021', description: '' }]
      : [],
  personal: { dob: '1998-05-14', gender: 'Female', location: 'Bengaluru', maritalStatus: 'Single' },
  career: { preferredLocations: 'Bengaluru, Remote', expectedSalary: '12-18 Lacs PA', jobType: 'Full Time', employmentType: 'Permanent', industry: 'Software Product', noticePeriod: '30 days' },
  visibility: 'PUBLIC',
  hideFromCompanies: '',
  views: 38 + index * 7,
  viewers: [
    { id: 'v1', name: 'Riya Recruiter', company: 'TechNova Solutions', at: daysAgo(1) },
    { id: 'v2', name: 'Manish Rao', company: 'CloudPeak', at: daysAgo(3) },
    { id: 'v3', name: 'Tara Bose', company: 'ShopEase', at: daysAgo(5) },
  ],
}))

export const mockAlerts: JobAlert[] = [
  { id: 'al1', keywords: 'React Developer', locations: 'Bengaluru, Remote', experience: '2-5', salary: '10+', frequency: 'DAILY', active: true },
  { id: 'al2', keywords: 'Frontend Engineer', locations: 'Hyderabad', experience: '3-6', salary: '12+', frequency: 'WEEKLY', active: false },
]

function seedMessages(texts: [ChatMessage['from'], string][]): ChatMessage[] {
  return texts.map(([from, text], index) => ({ id: `m${index}`, from, text, at: daysAgo(3 - index * 0.5) }))
}

export function mockThreadsFor(role: string): Thread[] {
  if (role === 'RECRUITER') {
    return [
      { id: 't1', participant: 'Priya Sharma', subtitle: 'Senior React Developer applicant', userIds: [], unread: 1, messages: seedMessages([['me', 'Hi Priya, are you available for a call this week?'], ['them', 'Yes, Thursday afternoon works for me.']]) },
      { id: 't2', participant: 'Arjun Mehta', subtitle: 'Candidate database invite', userIds: [], unread: 0, messages: seedMessages([['me', 'We would love to discuss an opening with you.']]) },
    ]
  }
  return [
    { id: 't1', participant: 'Riya Recruiter', subtitle: 'TechNova Solutions', userIds: [], unread: 2, messages: seedMessages([['them', 'Hi! We reviewed your profile and liked your React experience.'], ['them', 'Can we schedule a quick call?']]) },
    { id: 't2', participant: 'Manish Rao', subtitle: 'CloudPeak', userIds: [], unread: 0, messages: seedMessages([['them', 'Thanks for applying to the DevOps role.'], ['me', 'Thank you, looking forward to hearing back.']]) },
  ]
}

export function mockNotificationsFor(role: string): NotificationItem[] {
  if (role === 'RECRUITER') {
    return [
      { id: 'n1', type: 'APPLICATION', title: 'New applicants', body: '5 new candidates applied to Senior React Developer.', createdAt: daysAgo(0.1), read: false, link: '/recruiter/jobs/j1/applicants' },
      { id: 'n2', type: 'JOB', title: 'Job expiring soon', body: 'Your job posting expires in 3 days.', createdAt: daysAgo(1), read: false, link: '/recruiter/jobs' },
      { id: 'n3', type: 'SYSTEM', title: 'Credits updated', body: 'Your credit balance has been refreshed.', createdAt: daysAgo(6), read: true },
    ]
  }
  if (role === 'ADMIN') {
    return [
      { id: 'n1', type: 'SYSTEM', title: 'Company awaiting approval', body: 'Zenith Logistics submitted a profile for review.', createdAt: daysAgo(0.2), read: false, link: '/admin/companies' },
      { id: 'n2', type: 'JOB', title: 'Job reported', body: 'A job has been reported by a user.', createdAt: daysAgo(2), read: false, link: '/admin/moderation' },
    ]
  }
  return [
    { id: 'n1', type: 'APPLICATION', title: 'Application viewed', body: 'CloudPeak viewed your application for Data Analyst.', createdAt: daysAgo(0.1), read: false, link: '/seeker/applied' },
    { id: 'n2', type: 'JOB', title: '12 new jobs match your alert', body: 'React Developer in Bengaluru', createdAt: daysAgo(1), read: false, link: '/seeker/alerts' },
    { id: 'n3', type: 'MESSAGE', title: 'New message', body: 'Riya Recruiter sent you a message.', createdAt: daysAgo(2), read: true, link: '/messages' },
    { id: 'n4', type: 'SYSTEM', title: 'Complete your profile', body: 'Add your skills to get better recommendations.', createdAt: daysAgo(8), read: true, link: '/seeker/profile' },
  ]
}

export const mockJobReports: JobReport[] = [
  { id: 'rep1', jobId: 'j5', jobTitle: 'Sales Executive', reason: 'Asking for money', note: 'Recruiter asked for registration fee.', reportedBy: 'seeker2@mail.com', createdAt: daysAgo(2), resolved: false },
  { id: 'rep2', jobId: 'j9', jobTitle: 'DevOps Engineer', reason: 'Duplicate posting', note: 'Same job posted twice.', reportedBy: 'seeker3@mail.com', createdAt: daysAgo(4), resolved: false },
]

const masterSeeds: Record<MasterType, string[]> = {
  skills: ['React', 'TypeScript', 'JavaScript', 'Java', 'Python', 'SQL', 'AWS', 'Docker', 'Kubernetes', 'Node.js', 'Figma', 'Excel', 'SEO', 'Tableau', 'Agile', 'Selenium', 'Spring Boot', 'Redux', 'CSS', 'HTML', 'Communication', 'Salesforce', 'SAP', 'AutoCAD', 'Terraform', 'Next.js', 'GraphQL', 'MongoDB'],
  industries: ['IT Services', 'Software Product', 'Banking & Finance', 'Healthcare', 'E-commerce', 'Education', 'Manufacturing', 'Retail', 'Marketing', 'Energy', 'Logistics'],
  departments: ['Engineering', 'Data Science', 'Marketing', 'Sales', 'Human Resources', 'Finance', 'Design', 'Healthcare', 'Operations', 'Product'],
  'role-categories': ['Software Development', 'Analytics', 'Digital Marketing', 'Business Development', 'HR Operations', 'Accounting', 'Product Design', 'DevOps', 'Nursing', 'Mechanical', 'Product Management', 'Quality Assurance', 'Customer Success'],
  locations: locationPool.concat(['Ahmedabad', 'Jaipur']),
  degrees: ['B.Tech/B.E.', 'M.Tech', 'MBA/PGDM', 'B.Com', 'Any Graduate', 'MBBS', 'Diploma'],
}

export const mockMaster: Record<MasterType, MasterItem[]> = Object.fromEntries(
  Object.entries(masterSeeds).map(([type, names]) => [
    type,
    names.map((name, index) => ({
      id: `${type}-${index}`,
      name,
      synonyms: type === 'skills' && name === 'JavaScript' ? 'JS, ECMAScript' : type === 'skills' && name === 'Kubernetes' ? 'K8s' : '',
    })),
  ]),
) as Record<MasterType, MasterItem[]>

export const mockLocationTiles = ['Bengaluru', 'Mumbai', 'Delhi NCR', 'Hyderabad', 'Pune', 'Chennai', 'Kolkata', 'Remote']
export const mockSkillTiles = ['React', 'Java', 'Python', 'SQL', 'AWS', 'Figma', 'SEO', 'Excel']

// MOCK: platform statistics shown on the home page
export const mockPlatformStats = { jobs: 125430, companies: 8640, candidates: 2450000 }

// MOCK: admin analytics series (registrations / jobs posted / applications over time)
export const mockAnalyticsSeries = Array.from({ length: 12 }, (_, index) => ({
  date: new Date(Date.now() - (11 - index) * 7 * DAY_MS).toISOString().slice(0, 10),
  registrations: 120 + ((index * 37) % 90),
  jobs: 60 + ((index * 23) % 50),
  applications: 400 + ((index * 91) % 300),
}))

export const mockTopKeywords = [
  { keyword: 'react developer', count: 5400 },
  { keyword: 'data analyst', count: 4300 },
  { keyword: 'java', count: 3900 },
  { keyword: 'sales', count: 3100 },
  { keyword: 'work from home', count: 2800 },
]
