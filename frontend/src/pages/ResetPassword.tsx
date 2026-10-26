import { useState } from 'react'
import type { FormEvent } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import toast from 'react-hot-toast'
import { resetPassword } from '../auth/auth'
import { AuthCard, FormAlert } from '../components/AuthCard'
import { PasswordStrength, TextField } from '../components/fields'
import { useSeo } from '../hooks'
import { PASSWORD_HELP, hasErrors, validateConfirm, validateIdentifier, validateOtp, validatePassword } from '../validation'

export function ResetPassword() {
  const navigate = useNavigate()
  const [params] = useSearchParams()
  const [identifier, setIdentifier] = useState(params.get('identifier') ?? '')
  const [code, setCode] = useState(params.get('token') ?? '')
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [attempted, setAttempted] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  useSeo('Reset password', 'Choose a new password for your JobHub account.')

  const errors = {
    identifier: validateIdentifier(identifier),
    code: validateOtp(code),
    password: validatePassword(password),
    confirm: validateConfirm(password, confirm),
  }
  const isValid = !hasErrors(errors)

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    setAttempted(true)
    if (!isValid || loading) return
    setLoading(true)
    setError('')
    try {
      await resetPassword(identifier.trim(), code, password)
      toast.success('Password updated. Please log in.')
      navigate('/login')
    } catch (caught) {
      setError((caught as Error).message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <AuthCard title="Reset password" subtitle="Enter the code you received and choose a new password.">
      <FormAlert message={error} />
      <form onSubmit={submit} noValidate className="space-y-4">
        <TextField label="Email or mobile" required value={identifier} error={attempted ? errors.identifier : ''} onChange={(event) => setIdentifier(event.target.value)} />
        <TextField label="Reset code" required inputMode="numeric" maxLength={6} value={code} help="6-digit code from your email or SMS" error={attempted ? errors.code : ''} onChange={(event) => setCode(event.target.value.replace(/\D/g, ''))} />
        <TextField label="New password" type="password" required autoComplete="new-password" value={password} help={PASSWORD_HELP} error={attempted ? errors.password : ''} onChange={(event) => setPassword(event.target.value)} />
        <PasswordStrength value={password} />
        <TextField label="Confirm password" type="password" required autoComplete="new-password" value={confirm} error={attempted ? errors.confirm : ''} onChange={(event) => setConfirm(event.target.value)} />
        <button type="submit" className="btn-primary w-full" disabled={loading || (attempted && !isValid)}>
          {loading ? 'Updating…' : 'Reset password'}
        </button>
      </form>
      <p className="mt-4 text-center text-sm">
        <Link to="/login" className="font-semibold text-primary">
          Back to login
        </Link>
      </p>
    </AuthCard>
  )
}
