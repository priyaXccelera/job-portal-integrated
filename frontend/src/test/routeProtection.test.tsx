import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { RequireAuth } from '../components/RequireAuth'

function setSession(role: string) {
  localStorage.setItem(
    'auth_token',
    JSON.stringify({ token: 't', refreshToken: 'r', user: { id: 'u1', name: 'Test', email: 't@t.com', mobile: '9000000000', role } }),
  )
}

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/login" element={<p>login page</p>} />
        <Route path="/not-authorized" element={<p>not authorized page</p>} />
        <Route element={<RequireAuth roles={['ADMIN']} />}>
          <Route path="/admin" element={<p>admin area</p>} />
        </Route>
      </Routes>
    </MemoryRouter>,
  )
}

describe('role based route protection', () => {
  beforeEach(() => localStorage.clear())

  test('redirects logged out visitors to login', () => {
    renderAt('/admin')
    expect(screen.getByText('login page')).toBeTruthy()
  })

  test('shows not authorized for the wrong role', () => {
    setSession('JOB_SEEKER')
    renderAt('/admin')
    expect(screen.getByText('not authorized page')).toBeTruthy()
  })

  test('allows the right role', () => {
    setSession('ADMIN')
    renderAt('/admin')
    expect(screen.getByText('admin area')).toBeTruthy()
  })
})
