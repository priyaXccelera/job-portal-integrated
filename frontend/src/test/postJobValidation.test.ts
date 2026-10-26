import { EMPTY_DRAFT, validateAllSteps, validatePostJobStep } from '../validation/postJob'

describe('post job validation', () => {
  test('basics step requires title and location', () => {
    const errors = validatePostJobStep(EMPTY_DRAFT, 0)
    expect(errors.title).toBeTruthy()
    expect(errors.locations).toBeTruthy()
  })

  test('requirements step checks experience range and skills', () => {
    const errors = validatePostJobStep({ ...EMPTY_DRAFT, experienceMin: 5, experienceMax: 2 }, 1)
    expect(errors.experienceMax).toBeTruthy()
    expect(errors.skills).toBeTruthy()
  })

  test('salary is optional when not disclosed', () => {
    expect(validatePostJobStep({ ...EMPTY_DRAFT, salaryDisclosed: false }, 2)).toEqual({})
    expect(validatePostJobStep({ ...EMPTY_DRAFT, salaryDisclosed: true }, 2).salaryMin).toBeTruthy()
  })

  test('a complete draft passes every step', () => {
    const draft = {
      ...EMPTY_DRAFT,
      title: 'React Developer',
      locations: ['Pune'],
      skills: ['React'],
      salaryMin: 5,
      salaryMax: 8,
      description: '<p>We are looking for an experienced React developer to join our team.</p>',
    }
    expect(validateAllSteps(draft)).toBeNull()
  })
})
