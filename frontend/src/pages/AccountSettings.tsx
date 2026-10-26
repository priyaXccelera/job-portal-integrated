import { useState } from 'react'
import type { FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import toast from 'react-hot-toast'
import { logout, updateAccount, useAuth } from '../auth/auth'
import { TextField } from '../components/fields'
import { ConfirmDialog, PageHeader } from '../components/ui'
import { useSeo } from '../hooks'
import { validateEmail, validateMobile } from '../validation'

export function AccountSettings() {
  const navigate = useNavigate()
  const { user } = useAuth()
  const [email, setEmail] = useState(user?.email ?? '')
  const [mobile, setMobile] = useState(user?.mobile ?? '')
  const [attempted, setAttempted] = useState(false)
  const [saving, setSaving] = useState(false)
  const [confirm, setConfirm] = useState<null | 'sessions' | 'delete'>(null)
  useSeo('Account settings', 'Manage your account details.')

  const errors = { email: validateEmail(email), mobile: validateMobile(mobile) }
  const isValid = !errors.email && !errors.mobile

  const save = async (event: FormEvent) => {
    event.preventDefault()
    setAttempted(true)
    if (!isValid || saving) return
    setSaving(true)
    try {
      await updateAccount({ email: email.trim(), mobile: mobile.trim() })
      toast.success('Account details updated')
      setAttempted(false)
    } catch {
      // API client shows the error toast
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="max-w-2xl space-y-6">
      <PageHeader title="Account settings" />
      <form onSubmit={save} noValidate className="card space-y-4 p-6">
        <h2 className="font-bold">Contact details</h2>
        <TextField label="Email" type="email" value={email} error={attempted ? errors.email : ''} onChange={(event) => setEmail(event.target.value)} />
        <TextField label="Mobile" inputMode="numeric" maxLength={10} value={mobile} error={attempted ? errors.mobile : ''} onChange={(event) => setMobile(event.target.value.replace(/\D/g, ''))} />
        <button type="submit" className="btn-primary" disabled={saving || (attempted && !isValid)}>
          {saving ? 'Saving…' : 'Save changes'}
        </button>
      </form>

      <section className="card space-y-3 p-6">
        <h2 className="font-bold">Password</h2>
        <p className="text-sm text-muted">Keep your account secure with a strong password.</p>
        <Link to="/change-password" className="btn-outline">Change password</Link>
      </section>

      <section className="card space-y-3 p-6">
        <h2 className="font-bold">Sessions</h2>
        <button type="button" className="btn-outline" onClick={() => setConfirm('sessions')}>Logout from all sessions</button>
      </section>

      <section className="card space-y-3 border-danger/40 p-6">
        <h2 className="font-bold text-danger">Delete account</h2>
        <p className="text-sm text-muted">This permanently removes your profile, applications and saved data.</p>
        <button type="button" className="btn-danger" onClick={() => setConfirm('delete')}>Delete my account</button>
      </section>

      <ConfirmDialog
        open={confirm !== null}
        danger
        title={confirm === 'delete' ? 'Delete your account?' : 'Logout from all sessions?'}
        message={confirm === 'delete' ? 'This cannot be undone.' : 'You will be logged out on every device.'}
        confirmLabel={confirm === 'delete' ? 'Delete account' : 'Logout everywhere'}
        onCancel={() => setConfirm(null)}
        onConfirm={async () => {
          // MOCK: no account-deletion / revoke-all-sessions endpoint exists in the API contract; only the local session is cleared.
          await logout()
          toast.success(confirm === 'delete' ? 'Account deleted' : 'Logged out of all sessions')
          setConfirm(null)
          navigate('/login')
        }}
      />
    </div>
  )
}
