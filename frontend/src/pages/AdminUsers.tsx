import { useState } from 'react'
import toast from 'react-hot-toast'
import { SelectField, TextField } from '../components/fields'
import { ConfirmDialog, EmptyState, ErrorState, Modal, PageHeader, Pagination, Skeleton, StatusBadge, Tabs } from '../components/ui'
import { adjustCompanyCredits, getAdminCompanies, getUserList, setUserBlocked } from '../data/store'
import { PAGE_SIZE } from '../constants'
import { useAsync, useDebouncedValue, useSeo } from '../hooks'
import type { Company, Role, User } from '../types'

type Tab = 'users' | 'credits'

export function AdminUsers() {
  const [tab, setTab] = useState<Tab>('users')
  const [role, setRole] = useState<Role | ''>('')
  const [search, setSearch] = useState('')
  const debounced = useDebouncedValue(search)
  const [page, setPage] = useState(1)
  const users = useAsync(() => getUserList(role || undefined, debounced), [role, debounced])
  const companies = useAsync(() => getAdminCompanies(), [])
  const [blocking, setBlocking] = useState<User | null>(null)
  const [adjusting, setAdjusting] = useState<{ company: Company; credits: string; quota: string } | null>(null)
  const [attempted, setAttempted] = useState(false)
  useSeo('Users & credits', 'Manage users and company credits.')

  const creditsError = adjusting && !(Number(adjusting.credits) >= 0 && adjusting.credits !== '') ? 'Enter 0 or more credits' : ''
  const quotaError = adjusting && !(Number(adjusting.quota) >= 0 && adjusting.quota !== '') ? 'Enter 0 or more' : ''

  const list = users.data ?? []

  return (
    <div>
      <PageHeader title="Users & credits" />
      <Tabs active={tab} onChange={(value) => setTab(value as typeof tab)} tabs={[{ value: 'users', label: 'Users' }, { value: 'credits', label: 'Company credits & quota' }]} />

      {tab === 'users' && (
        <div className="mt-4">
          <div className="mb-4 flex flex-wrap gap-3">
            <input className="input max-w-xs" type="search" aria-label="Search users" placeholder="Search name or email" value={search} onChange={(event) => { setSearch(event.target.value); setPage(1) }} />
            <select className="input w-auto" aria-label="Filter by role" value={role} onChange={(event) => { setRole(event.target.value as Role | ''); setPage(1) }}>
              <option value="">All roles</option>
              <option value="JOB_SEEKER">Job seekers</option>
              <option value="RECRUITER">Recruiters</option>
              <option value="ADMIN">Admins</option>
            </select>
          </div>
          {users.loading && <Skeleton className="h-48 w-full" />}
          {users.error && <ErrorState message={users.error} onRetry={users.reload} />}
          {!users.loading && list.length === 0 && <EmptyState title="No users found" />}
          {list.length > 0 && (
            <div className="card overflow-x-auto">
              <table className="w-full min-w-[40rem] text-left text-sm">
                <thead className="border-b border-line text-xs uppercase text-muted">
                  <tr><th className="p-3">Name</th><th>Email</th><th>Role</th><th>Status</th><th className="pr-3 text-right">Action</th></tr>
                </thead>
                <tbody className="divide-y divide-line">
                  {list.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE).map((user) => (
                    <tr key={user.id}>
                      <td className="p-3 font-medium">{user.name}</td>
                      <td>{user.email}</td>
                      <td>{user.role.replace('_', ' ').toLowerCase()}</td>
                      <td><StatusBadge status={user.blocked ? 'BLOCKED' : 'ACTIVE'} /></td>
                      <td className="pr-3 text-right">
                        {user.role !== 'ADMIN' && (
                          <button
                            type="button"
                            className={`text-sm font-semibold ${user.blocked ? 'text-primary' : 'text-danger'}`}
                            onClick={() => (user.blocked ? setUserBlocked(user.id, false).then(() => { toast.success('User unblocked'); users.reload() }) : setBlocking(user))}
                          >
                            {user.blocked ? 'Unblock' : 'Block'}
                          </button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <Pagination page={page} pageSize={PAGE_SIZE} total={list.length} onChange={setPage} />
        </div>
      )}

      {tab === 'credits' && (
        <div className="card mt-4 overflow-x-auto">
          {companies.loading && <Skeleton className="h-32 w-full" />}
          <table className="w-full min-w-[36rem] text-left text-sm">
            <thead className="border-b border-line text-xs uppercase text-muted">
              <tr><th className="p-3">Company</th><th>Status</th><th>Credits</th><th>Job quota</th><th className="pr-3 text-right">Action</th></tr>
            </thead>
            <tbody className="divide-y divide-line">
              {companies.data?.map((company) => (
                <tr key={company.id}>
                  <td className="p-3 font-medium">{company.name}</td>
                  <td><StatusBadge status={company.status} /></td>
                  <td>{company.credits}</td>
                  <td>{company.quota}</td>
                  <td className="pr-3 text-right">
                    <button type="button" className="text-sm font-semibold text-primary" onClick={() => setAdjusting({ company, credits: String(company.credits), quota: String(company.quota) })}>
                      Adjust
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <ConfirmDialog
        open={Boolean(blocking)}
        danger
        title="Block this user?"
        message={`${blocking?.name ?? 'This user'} will no longer be able to log in.`}
        confirmLabel="Block"
        onCancel={() => setBlocking(null)}
        onConfirm={async () => {
          if (blocking) await setUserBlocked(blocking.id, true)
          toast.success('User blocked')
          setBlocking(null)
          users.reload()
        }}
      />

      <Modal open={Boolean(adjusting)} title={`Adjust ${adjusting?.company.name ?? ''}`} onClose={() => { setAdjusting(null); setAttempted(false) }}>
        {adjusting && (
          <form
            noValidate
            className="space-y-4"
            onSubmit={async (event) => {
              event.preventDefault()
              setAttempted(true)
              if (creditsError || quotaError) return
              await adjustCompanyCredits(adjusting.company.id, Number(adjusting.credits), Number(adjusting.quota))
              toast.success('Credits and quota updated')
              setAdjusting(null)
              setAttempted(false)
              companies.reload()
            }}
          >
            <TextField label="Credits" type="number" min={0} value={adjusting.credits} error={attempted ? creditsError : ''} onChange={(event) => setAdjusting({ ...adjusting, credits: event.target.value })} />
            <SelectField label="Job posting quota" value={adjusting.quota} options={['5', '10', '25', '50', '100']} onChange={(event) => setAdjusting({ ...adjusting, quota: event.target.value })} />
            <div className="flex justify-end gap-3">
              <button type="button" className="btn-outline" onClick={() => setAdjusting(null)}>Cancel</button>
              <button type="submit" className="btn-primary">Save</button>
            </div>
          </form>
        )}
      </Modal>
    </div>
  )
}
