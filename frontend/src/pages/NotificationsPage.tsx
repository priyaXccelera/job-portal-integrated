import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { BellRing, Briefcase, CheckCheck, MessageSquare, Settings } from 'lucide-react'
import toast from 'react-hot-toast'
import { EmptyState, ErrorState, PageHeader, Pagination, Skeleton, Tabs } from '../components/ui'
import { getNotifications, markAllNotificationsRead, setNotificationRead } from '../data/store'
import { PAGE_SIZE } from '../constants'
import { useAsync, useSeo } from '../hooks'
import type { NotificationItem } from '../types'
import { timeAgo } from '../utils/format'

type Filter = 'ALL' | NotificationItem['type']

const ICONS = { APPLICATION: BellRing, JOB: Briefcase, MESSAGE: MessageSquare, SYSTEM: Settings }

export function NotificationsPage() {
  const navigate = useNavigate()
  const { data, loading, error, reload } = useAsync(() => getNotifications(), [])
  const [filter, setFilter] = useState<Filter>('ALL')
  const [page, setPage] = useState(1)
  useSeo('Notifications', 'All your notifications.')

  const items = (data ?? []).filter((item) => filter === 'ALL' || item.type === filter)
  const unread = (data ?? []).filter((item) => !item.read).length

  return (
    <div>
      <PageHeader
        title="Notifications"
        subtitle={`${unread} unread`}
        actions={
          <button
            type="button"
            className="btn-outline"
            disabled={unread === 0}
            onClick={async () => {
              await markAllNotificationsRead()
              toast.success('All notifications marked as read')
              reload()
            }}
          >
            <CheckCheck className="h-4 w-4" />
            Mark all as read
          </button>
        }
      />
      <Tabs
        active={filter}
        onChange={(next) => {
          setFilter(next)
          setPage(1)
        }}
        tabs={[
          { value: 'ALL', label: 'All' },
          { value: 'APPLICATION', label: 'Applications' },
          { value: 'JOB', label: 'Jobs' },
          { value: 'MESSAGE', label: 'Messages' },
          { value: 'SYSTEM', label: 'System' },
        ]}
      />
      <div className="mt-4 space-y-2">
        {loading && <Skeleton className="h-16 w-full" />}
        {error && <ErrorState message={error} onRetry={reload} />}
        {!loading && !error && items.length === 0 && <EmptyState title="No notifications" message="You're all caught up." />}
        {items.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE).map((item) => {
          const Icon = ICONS[item.type]
          return (
            <div key={item.id} className={`card flex items-start gap-3 p-4 ${item.read ? '' : 'border-primary/40 bg-soft/50'}`}>
              <Icon className="mt-0.5 h-5 w-5 text-primary" />
              <button
                type="button"
                className="min-w-0 flex-1 text-left"
                onClick={async () => {
                  if (!item.read) await setNotificationRead(item.id, true)
                  if (item.link) navigate(item.link)
                  else reload()
                }}
              >
                <p className="text-sm font-semibold">{item.title}</p>
                <p className="text-sm text-muted">{item.body}</p>
                <p className="mt-1 text-xs text-muted">{timeAgo(item.createdAt)}</p>
              </button>
              <button
                type="button"
                className="text-xs font-semibold text-primary"
                onClick={async () => {
                  await setNotificationRead(item.id, !item.read)
                  reload()
                }}
              >
                Mark as {item.read ? 'unread' : 'read'}
              </button>
            </div>
          )
        })}
      </div>
      <Pagination page={page} pageSize={PAGE_SIZE} total={items.length} onChange={setPage} />
    </div>
  )
}
