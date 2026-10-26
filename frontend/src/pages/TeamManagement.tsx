import { useState } from 'react'
import type { FormEvent } from 'react'
import toast from 'react-hot-toast'
import { FormAlert } from '../components/AuthCard'
import { TextField } from '../components/fields'
import { ConfirmDialog, ErrorState, PageHeader, Skeleton } from '../components/ui'
import { cancelInvitation, getTeam, inviteTeamMember, removeTeamMember, resendInvitation } from '../data/store'
import { useAsync, useSeo } from '../hooks'
import type { NormalizedError } from '../api/client'
import type { TeamMember } from '../types'
import { formatDate } from '../utils/format'
import { validateEmail } from '../validation'

export function TeamManagement() {
  const { data, loading, error, reload } = useAsync(() => getTeam(), [])
  const [email, setEmail] = useState('')
  const [attempted, setAttempted] = useState(false)
  const [sending, setSending] = useState(false)
  const [serverError, setServerError] = useState('')
  const [removing, setRemoving] = useState<TeamMember | null>(null)
  useSeo('Team management', 'Manage your hiring team.')
  const emailError = validateEmail(email)

  const invite = async (event: FormEvent) => {
    event.preventDefault()
    setAttempted(true)
    if (emailError || sending) return
    setSending(true)
    setServerError('')
    try {
      await inviteTeamMember(email.trim())
      toast.success(`Invitation sent to ${email.trim()}`)
      setEmail('')
      setAttempted(false)
      reload()
    } catch (caught) {
      setServerError((caught as NormalizedError).message)
    } finally {
      setSending(false)
    }
  }

  if (error) return <ErrorState message={error} onRetry={reload} />

  return (
    <div className="space-y-6">
      <PageHeader title="Team management" subtitle="Invite colleagues to help with hiring." />
      <form onSubmit={invite} noValidate className="card space-y-3 p-5">
        <h2 className="font-bold">Invite a team member</h2>
        <FormAlert message={serverError} />
        <div className="flex flex-col gap-3 sm:flex-row sm:items-start">
          <div className="flex-1">
            <TextField label="Work email" type="email" value={email} error={attempted ? emailError : ''} onChange={(event) => setEmail(event.target.value)} />
          </div>
          <button type="submit" className="btn-primary sm:mt-6" disabled={sending || (attempted && Boolean(emailError))}>
            {sending ? 'Sending…' : 'Send invite'}
          </button>
        </div>
      </form>

      <section className="card p-5" aria-label="Team members">
        <h2 className="mb-3 font-bold">Team members</h2>
        {loading && <Skeleton className="h-16 w-full" />}
        <ul className="divide-y divide-line">
          {data?.members.map((member) => (
            <li key={member.id} className="flex items-center gap-3 py-3">
              <span className="flex h-9 w-9 items-center justify-center rounded-full bg-primary font-bold text-white">{member.name.slice(0, 1)}</span>
              <div className="min-w-0 flex-1">
                <p className="font-semibold">{member.name}</p>
                <p className="text-xs text-muted">{member.email}</p>
              </div>
              <span className="chip">{member.role}</span>
              {member.role !== 'Owner' && (
                <button type="button" className="text-sm font-semibold text-danger" onClick={() => setRemoving(member)}>
                  Remove
                </button>
              )}
            </li>
          ))}
        </ul>
      </section>

      <section className="card p-5" aria-label="Pending invitations">
        <h2 className="mb-3 font-bold">Pending invitations</h2>
        <ul className="divide-y divide-line">
          {data?.invitations.map((invitation) => (
            <li key={invitation.id} className="flex flex-wrap items-center gap-3 py-3 text-sm">
              <span className="flex-1">
                {invitation.email} <span className="text-xs text-muted">· sent {formatDate(invitation.sentAt)}</span>
              </span>
              <button
                type="button"
                className="font-semibold text-primary"
                onClick={async () => {
                  await resendInvitation(invitation.id)
                  toast.success('Invitation resent')
                  reload()
                }}
              >
                Resend
              </button>
              <button
                type="button"
                className="font-semibold text-danger"
                onClick={async () => {
                  await cancelInvitation(invitation.id)
                  toast.success('Invitation cancelled')
                  reload()
                }}
              >
                Cancel
              </button>
            </li>
          ))}
          {data?.invitations.length === 0 && <li className="py-4 text-sm text-muted">No pending invitations.</li>}
        </ul>
      </section>

      <ConfirmDialog
        open={Boolean(removing)}
        danger
        title="Remove team member?"
        message={`${removing?.name ?? 'This member'} will lose access to your company's jobs.`}
        confirmLabel="Remove"
        onCancel={() => setRemoving(null)}
        onConfirm={async () => {
          if (removing) await removeTeamMember(removing.id)
          setRemoving(null)
          toast.success('Team member removed')
          reload()
        }}
      />
    </div>
  )
}
