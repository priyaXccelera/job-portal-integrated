import { useState } from 'react'
import type { FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { forgotPassword } from '../auth/auth'
import { AuthCard, FormAlert } from '../components/AuthCard'
import { TextField } from '../components/fields'
import { DEMO_OTP } from '../constants'
import { useSeo } from '../hooks'
import { validateIdentifier } from '../validation'

export function ForgotPassword() {
  const navigate = useNavigate()
  const [identifier, setIdentifier] = useState('')
  const [attempted, setAttempted] = useState(false)
  const [loading, setLoading] = useState(false)
  const [sent, setSent] = useState(false)
  const [error, setError] = useState('')
  useSeo('Forgot password', 'Reset your JobHub password.')
  const validation = validateIdentifier(identifier)

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    setAttempted(true)
    if (validation || loading) return
    setLoading(true)
    setError('')
    try {
      await forgotPassword(identifier.trim())
      setSent(true)
    } catch (caught) {
      setError((caught as Error).message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <AuthCard title="Forgot password?" subtitle="Enter your email or mobile and we'll send a reset link or OTP.">
      {sent ? (
        <div className="space-y-4">
          <FormAlert tone="success" message="If an account exists, we've sent reset instructions." />
          {/* MOCK: in demo mode the reset code is fixed instead of being delivered by email/SMS. */}
          <p className="text-sm text-muted">Demo reset code: {DEMO_OTP}</p>
          <button type="button" className="btn-primary w-full" onClick={() => navigate(`/reset-password?identifier=${encodeURIComponent(identifier.trim())}`)}>
            Enter reset code
          </button>
        </div>
      ) : (
        <form onSubmit={submit} noValidate className="space-y-4">
          <FormAlert message={error} />
          <TextField label="Email or mobile" required value={identifier} error={attempted ? validation : ''} onChange={(event) => setIdentifier(event.target.value)} />
          <button type="submit" className="btn-primary w-full" disabled={loading || (attempted && Boolean(validation))}>
            {loading ? 'Sending…' : 'Send reset link / OTP'}
          </button>
        </form>
      )}
      <p className="mt-4 text-center text-sm">
        <Link to="/login" className="font-semibold text-primary">
          Back to login
        </Link>
      </p>
    </AuthCard>
  )
}
