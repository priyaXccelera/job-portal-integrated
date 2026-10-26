import { Link, useRouteError } from 'react-router-dom'
import { AlertTriangle } from 'lucide-react'

/** Router errorElement: shows a 500-style page with a retry button. */
export function RouteError() {
  const error = useRouteError() as { message?: string } | undefined
  return (
    <div className="flex min-h-screen flex-col items-center justify-center px-4 text-center" role="alert">
      <AlertTriangle className="h-14 w-14 text-danger" aria-hidden="true" />
      <h1 className="mt-4 text-3xl font-extrabold">Something went wrong</h1>
      <p className="mt-2 text-muted">{error?.message ?? 'An unexpected error occurred.'}</p>
      <div className="mt-6 flex gap-3">
        <button type="button" className="btn-primary" onClick={() => window.location.reload()}>
          Retry
        </button>
        <Link to="/" className="btn-outline">
          Go Home
        </Link>
      </div>
    </div>
  )
}
