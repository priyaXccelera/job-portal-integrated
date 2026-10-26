import { useState } from 'react'
import type { FormEvent } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { MailCheck } from 'lucide-react'
import { verifyEmail } from '../auth/auth'
import { AuthCard, FormAlert } from '../components/AuthCard'
import { TextField } from '../components/fields'
import { useSeo } from '../hooks'
import { validateRequired } from '../validation'

export function EmailVerification() {
  const navigate = useNavigate()
  const [params] = useSearchParams()
  const email = params.get('email') ?? ''
  const mobile = params.get('mobile') ?? ''
  const [token, setToken] = useState(params.get('token') ?? '')
  const [attempted, setAttempted] = useState(false)
  const [loading, setLoading] = useState(false)
  const [status, setStatus] = useState<'idle' | 'verified' | 'failed'>('idle')
  useSeo('Verify email', 'Verify your email address to activate your JobHub account.')

  const error = validateRequired(token, 'Verification token')

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    setAttempted(true)
    if (error || loading) return
    setLoading(true)
    try {
      setStatus((await verifyEmail(token.trim(), email)) ? 'verified' : 'failed')
    } catch {
      setStatus('failed')
    } finally {
      setLoading(false)
    }
  }

  return (
    <AuthCard title="Verify your email" subtitle={email ? `We sent a verification link to ${email}.` : 'Enter the token from your verification email.'}>
      <MailCheck className="mx-auto mb-4 h-12 w-12 text-primary" aria-hidden="true" />
      {status === 'verified' ? (
        <div className="space-y-4 text-center">
          <FormAlert tone="success" message="Your email has been verified." />
          <button type="button" className="btn-primary w-full" onClick={() => navigate(`/verify-mobile?mobile=${mobile}`)}>
            Continue to mobile verification
          </button>
        </div>
      ) : (
        <form onSubmit={submit} noValidate className="space-y-4">
          <FormAlert message={status === 'failed' ? 'This verification token is invalid or expired.' : ''} />
          {/* MOCK: any non-empty token verifies the email in demo mode. */}
          <TextField label="Verification token" required value={token} help="Paste the token from the email (demo: any text works)" error={attempted ? error : ''} onChange={(event) => setToken(event.target.value)} />
          <button type="submit" className="btn-primary w-full" disabled={loading || (attempted && Boolean(error))}>
            {loading ? 'Verifying…' : 'Verify email'}
          </button>
        </form>
      )}
      <p className="mt-4 text-center text-sm text-muted">
        <Link to="/login" className="font-semibold text-primary">
          Back to login
        </Link>
      </p>
    </AuthCard>
  )
}
