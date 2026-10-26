import { useState } from 'react'
import type { FormEvent } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import toast from 'react-hot-toast'
import { currentRole, homeFor, login } from '../auth/auth'
import { AuthCard, FormAlert } from '../components/AuthCard'
import { CheckboxField, TextField } from '../components/fields'
import { useSeo } from '../hooks'
import { validateIdentifier, validateRequired } from '../validation'

export function Login() {
  const navigate = useNavigate()
  const [params] = useSearchParams()
  const [identifier, setIdentifier] = useState('')
  const [password, setPassword] = useState('')
  const [remember, setRemember] = useState(true)
  const [attempted, setAttempted] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  useSeo('Login', 'Log in to your JobHub account.')

  const errors = { identifier: validateIdentifier(identifier), password: validateRequired(password, 'Password') }
  const isValid = !errors.identifier && !errors.password

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    setAttempted(true)
    if (!isValid || loading) return
    setLoading(true)
    setError('')
    try {
      const ok = await login(identifier.trim(), password)
      if (!ok) {
        setError('Invalid email/mobile or password')
        return
      }
      toast.success('Welcome back!')
      const returnTo = params.get('returnTo')
      navigate(returnTo && returnTo.startsWith('/') ? returnTo : homeFor(currentRole()), { replace: true })
    } catch (caught) {
      setError((caught as Error).message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <AuthCard title="Login" subtitle="Welcome back! Log in to continue.">
      <FormAlert message={error} />
      <form onSubmit={submit} noValidate className="space-y-4">
        <TextField label="Email ID / Mobile number" required autoComplete="username" value={identifier} error={attempted ? errors.identifier : ''} onChange={(event) => setIdentifier(event.target.value)} />
        <TextField label="Password" type="password" required autoComplete="current-password" value={password} error={attempted ? errors.password : ''} onChange={(event) => setPassword(event.target.value)} />
        <div className="flex items-center justify-between">
          <CheckboxField label="Remember me" checked={remember} onChange={setRemember} />
          <Link to="/forgot-password" className="text-sm font-semibold text-primary">
            Forgot password?
          </Link>
        </div>
        <button type="submit" className="btn-primary w-full py-2.5" disabled={loading || (attempted && !isValid)}>
          {loading ? 'Logging in…' : 'Login'}
        </button>
      </form>
      <div className="my-5 flex items-center gap-3 text-xs text-muted">
        <span className="h-px flex-1 bg-line" />
        OR
        <span className="h-px flex-1 bg-line" />
      </div>
      <Link to="/login-otp" className="btn-outline w-full py-2.5">
        Login with OTP
      </Link>
      <p className="mt-4 text-center text-sm text-muted">
        New to JobHub?{' '}
        <Link to="/register" className="font-semibold text-primary">
          Sign up
        </Link>
      </p>
    </AuthCard>
  )
}
