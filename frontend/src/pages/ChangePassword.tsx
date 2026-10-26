import { useState } from 'react'
import type { FormEvent } from 'react'
import toast from 'react-hot-toast'
import { changePassword } from '../auth/auth'
import { FormAlert } from '../components/AuthCard'
import { PasswordStrength, TextField } from '../components/fields'
import { PageHeader } from '../components/ui'
import { useSeo, useUnsavedWarning } from '../hooks'
import { PASSWORD_HELP, hasErrors, validateConfirm, validatePassword, validateRequired } from '../validation'

export function ChangePassword() {
  const [current, setCurrent] = useState('')
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [attempted, setAttempted] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  useSeo('Change password', 'Update your JobHub password.')
  useUnsavedWarning(Boolean(current || password || confirm) && !success)

  const errors = {
    current: validateRequired(current, 'Current password'),
    password: validatePassword(password) || (password === current && password ? 'New password must differ from the current one' : ''),
    confirm: validateConfirm(password, confirm),
  }
  const isValid = !hasErrors(errors)

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    setAttempted(true)
    if (!isValid || loading) return
    setLoading(true)
    setError('')
    setSuccess('')
    try {
      await changePassword(current, password)
      setSuccess('Your password has been changed.')
      toast.success('Password changed')
      setCurrent('')
      setPassword('')
      setConfirm('')
      setAttempted(false)
    } catch (caught) {
      setError((caught as Error).message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="max-w-lg">
      <PageHeader title="Change password" subtitle="Use a strong password you don't use elsewhere." />
      <form onSubmit={submit} noValidate className="card space-y-4 p-6">
        <FormAlert message={error} />
        <FormAlert tone="success" message={success} />
        <TextField label="Current password" type="password" required autoComplete="current-password" value={current} error={attempted ? errors.current : ''} onChange={(event) => setCurrent(event.target.value)} />
        <TextField label="New password" type="password" required autoComplete="new-password" value={password} help={PASSWORD_HELP} error={attempted ? errors.password : ''} onChange={(event) => setPassword(event.target.value)} />
        <PasswordStrength value={password} />
        <TextField label="Confirm new password" type="password" required autoComplete="new-password" value={confirm} error={attempted ? errors.confirm : ''} onChange={(event) => setConfirm(event.target.value)} />
        <button type="submit" className="btn-primary" disabled={loading || (attempted && !isValid)}>
          {loading ? 'Saving…' : 'Update password'}
        </button>
      </form>
    </div>
  )
}
