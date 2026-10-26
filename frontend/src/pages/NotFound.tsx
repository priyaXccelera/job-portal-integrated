import { Link, useNavigate } from 'react-router-dom'
import { SearchX } from 'lucide-react'

export function NotFound() {
  const navigate = useNavigate()
  return (
    <div className="flex min-h-screen flex-col items-center justify-center px-4 text-center">
      <SearchX className="h-14 w-14 text-primary" aria-hidden="true" />
      <h1 className="mt-4 text-4xl font-extrabold">404</h1>
      <p className="mt-2 text-muted">We couldn't find the page you're looking for.</p>
      <div className="mt-6 flex gap-3">
        <button type="button" className="btn-outline" onClick={() => navigate(-1)}>
          Go back
        </button>
        <Link to="/" className="btn-primary">
          Go Home
        </Link>
      </div>
    </div>
  )
}
