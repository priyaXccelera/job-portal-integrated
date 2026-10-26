import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, useLocation } from 'react-router-dom'
import { JobSearch } from '../pages/JobSearch'
import { applyToJob, getMyApplications, searchJobs, setApplicationStatus, getApplicants } from '../data/store'
import { KanbanBoard } from '../components/KanbanBoard'
import { fireEvent } from '@testing-library/react'
import type { Application } from '../types'

function LocationProbe() {
  const location = useLocation()
  return <p data-testid="url">{location.pathname + location.search}</p>
}

function loginAs(id: string, role: string) {
  localStorage.setItem(
    'auth_token',
    JSON.stringify({ token: 't', refreshToken: 'r', user: { id, name: 'Test', email: 't@t.com', mobile: '9000000000', role } }),
  )
}

describe('job search filters and URL syncing', () => {
  beforeEach(() => localStorage.clear())

  test('filters results by the URL parameters and exposes facets', async () => {
    const all = await searchJobs({})
    const filtered = await searchJobs({ location: 'Pune' })
    expect(filtered.meta.total).toBeLessThan(all.meta.total)
    expect(filtered.data.every((job) => job.locations.includes('Pune'))).toBe(true)
    expect(all.meta.facets?.location?.Pune).toBeGreaterThan(0)
  })

  test('renders the filtered count from the URL and keeps the URL in sync', async () => {
    render(
      <MemoryRouter initialEntries={['/jobs?q=react&workMode=Hybrid']}>
        <JobSearch />
        <LocationProbe />
      </MemoryRouter>,
    )
    await waitFor(() => expect(screen.getByText(/jobs found/)).toBeTruthy())
    expect(screen.getByTestId('url').textContent).toContain('q=react')
    fireEvent.click(screen.getAllByText('Clear all')[0])
    await waitFor(() => expect(screen.getByTestId('url').textContent).not.toContain('workMode'))
  })
})

describe('apply flow', () => {
  beforeEach(() => {
    localStorage.clear()
    loginAs('u-s2', 'JOB_SEEKER')
  })

  test('applying creates an application and blocks duplicates', async () => {
    const before = (await getMyApplications()).length
    await applyToJob('j5', { resumeId: 'r', coverNote: '', answers: [] })
    expect((await getMyApplications()).length).toBe(before + 1)
    await expect(applyToJob('j5', { resumeId: 'r', coverNote: '', answers: [] })).rejects.toThrow()
  })
})

describe('kanban status change', () => {
  beforeEach(() => localStorage.clear())

  test('dropping a card on another column triggers onMove', () => {
    const application = { id: 'a1', candidateName: 'Asha', headline: 'Dev', rating: 3, matchPercentage: 80, status: 'APPLIED' } as Application
    const onMove = vi.fn()
    render(<KanbanBoard applications={[application]} onMove={onMove} onOpen={() => undefined} />)
    const card = screen.getByLabelText('Asha, Applied')
    fireEvent.dragStart(card, { dataTransfer: { setData: () => undefined, getData: () => 'a1' } })
    fireEvent.drop(screen.getByTestId('column-SHORTLISTED'), { dataTransfer: { getData: () => 'a1' } })
    expect(onMove).toHaveBeenCalledWith(application, 'SHORTLISTED')
  })

  test('store persists the new status and history', async () => {
    loginAs('u-r1', 'RECRUITER')
    const { data } = await getApplicants('j1', {})
    const target = data[0]
    await setApplicationStatus([target.id], 'OFFERED', 'Congrats')
    const after = (await getApplicants('j1', {})).data.find((entry) => entry.id === target.id)
    expect(after?.status).toBe('OFFERED')
    expect(after?.history[after.history.length - 1].note).toBe('Congrats')
  })
})
