import { Navigate, Outlet, useLocation } from 'react-router-dom'
import { useAuth } from '../auth/auth'
import type { Role } from '../types'

/** Route guard: redirects to /login (with return-to URL) or /not-authorized. */
export function RequireAuth({ roles }: { roles?: Role[] }) {
  const { isLoggedIn, role } = useAuth()
  const location = useLocation()

  if (!isLoggedIn) {
    const returnTo = encodeURIComponent(location.pathname + location.search)
    return <Navigate to={`/login?returnTo=${returnTo}`} replace />
  }
  if (roles && role && !roles.includes(role)) {
    return <Navigate to="/not-authorized" replace />
  }
  return <Outlet />
}
