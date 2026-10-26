import type { PostJobDraft } from '../types'

export const POST_JOB_STEPS = ['Basics', 'Requirements', 'Compensation', 'Description', 'Screening', 'Review'] as const

export const EMPTY_DRAFT: PostJobDraft = {
  title: '',
  locations: [],
  workMode: 'On-site',
  jobType: 'Full Time',
  employmentType: 'Permanent',
  openings: 1,
  experienceMin: 0,
  experienceMax: 3,
  skills: [],
  education: 'Any Graduate',
  salaryMin: 0,
  salaryMax: 0,
  currency: 'INR',
  salaryDisclosed: true,
  description: '',
  screeningQuestions: [],
}

function plainText(html: string): string {
  return html.replace(/<[^>]+>/g, ' ').replace(/&nbsp;/g, ' ').replace(/\s+/g, ' ').trim()
}

/** Returns field -> error message for a single step (empty object when valid). */
export function validatePostJobStep(draft: PostJobDraft, step: number): Record<string, string> {
  const errors: Record<string, string> = {}
  if (step === 0) {
    if (draft.title.trim().length < 3) errors.title = 'Job title must be at least 3 characters'
    if (draft.locations.length === 0) errors.locations = 'Add at least one location'
    if (!(draft.openings >= 1)) errors.openings = 'Openings must be at least 1'
  }
  if (step === 1) {
    if (draft.experienceMin < 0) errors.experienceMin = 'Minimum experience cannot be negative'
    if (draft.experienceMax < draft.experienceMin) errors.experienceMax = 'Maximum experience must be at least the minimum'
    if (draft.skills.length === 0) errors.skills = 'Add at least one skill'
  }
  if (step === 2 && draft.salaryDisclosed) {
    if (!(draft.salaryMin > 0)) errors.salaryMin = 'Enter a minimum salary'
    if (draft.salaryMax < draft.salaryMin) errors.salaryMax = 'Maximum salary must be at least the minimum'
  }
  if (step === 3 && plainText(draft.description).length < 30) {
    errors.description = 'Description must be at least 30 characters'
  }
  if (step === 4) {
    draft.screeningQuestions.forEach((question) => {
      if (!question.text.trim()) errors[`question-${question.id}`] = 'Question text is required'
      if (question.type === 'choice' && (question.options ?? []).filter((option) => option.trim()).length < 2) {
        errors[`options-${question.id}`] = 'Add at least two options'
      }
    })
  }
  return errors
}

export function validateAllSteps(draft: PostJobDraft): { step: number; errors: Record<string, string> } | null {
  for (let step = 0; step < 5; step += 1) {
    const errors = validatePostJobStep(draft, step)
    if (Object.keys(errors).length) return { step, errors }
  }
  return null
}
