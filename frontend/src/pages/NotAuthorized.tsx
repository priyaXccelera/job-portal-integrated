import { Link } from 'react-router-dom'
import { ShieldX } from 'lucide-react'
import { homeFor, useAuth } from '../auth/auth'

export function NotAuthorized() {
  const { role, isLoggedIn } = useAuth()
  return (
    <div className="mx-auto flex max-w-lg flex-col items-center px-4 py-24 text-center">
      <ShieldX className="h-14 w-14 text-danger" aria-hidden="true" />
      <h1 className="mt-4 text-3xl font-extrabold">Not authorized</h1>
      <p className="mt-2 text-muted">You don't have permission to view this page with your current account.</p>
      <div className="mt-6 flex gap-3">
        {isLoggedIn ? (
          <Link to={homeFor(role)} className="btn-primary">
            Go to my dashboard
          </Link>
        ) : (
          <Link to="/login" className="btn-primary">
            Log in
          </Link>
        )}
        <Link to="/" className="btn-outline">
          Go Home
        </Link>
      </div>
    </div>
  )
}
