import { useEffect } from 'react'
import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { AlertTriangle, ChevronLeft, ChevronRight, Inbox, Star, X } from 'lucide-react'
import { STATUS_LABELS } from '../constants'

export function Skeleton({ className = '' }: { className?: string }) {
  return <div className={`animate-pulse rounded-md bg-line ${className}`} aria-hidden="true" />
}

export function JobCardSkeleton() {
  return (
    <div className="card flex gap-4 p-5" aria-busy="true">
      <Skeleton className="h-12 w-12 shrink-0" />
      <div className="flex-1 space-y-3">
        <Skeleton className="h-5 w-2/3" />
        <Skeleton className="h-4 w-1/3" />
        <Skeleton className="h-4 w-full" />
        <div className="flex gap-2">
          <Skeleton className="h-6 w-16" />
          <Skeleton className="h-6 w-16" />
          <Skeleton className="h-6 w-16" />
        </div>
      </div>
    </div>
  )
}

export function ListSkeleton({ count = 4 }: { count?: number }) {
  return (
    <div className="space-y-4">
      {Array.from({ length: count }, (_, index) => (
        <JobCardSkeleton key={index} />
      ))}
    </div>
  )
}

export function EmptyState({
  title,
  message,
  action,
}: {
  title: string
  message?: string
  action?: ReactNode
}) {
  return (
    <div className="card flex flex-col items-center px-6 py-14 text-center">
      <Inbox className="mb-3 h-10 w-10 text-muted" aria-hidden="true" />
      <h3 className="text-lg font-semibold">{title}</h3>
      {message && <p className="mt-1 max-w-md text-sm text-muted">{message}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  )
}

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="card flex flex-col items-center px-6 py-12 text-center" role="alert">
      <AlertTriangle className="mb-3 h-10 w-10 text-danger" aria-hidden="true" />
      <h3 className="text-lg font-semibold">Something went wrong</h3>
      <p className="mt-1 text-sm text-muted">{message}</p>
      {onRetry && (
        <button type="button" className="btn-primary mt-4" onClick={onRetry}>
          Retry
        </button>
      )}
    </div>
  )
}

export function Modal({
  open,
  title,
  onClose,
  children,
  wide = false,
}: {
  open: boolean
  title: string
  onClose: () => void
  children: ReactNode
  wide?: boolean
}) {
  useEffect(() => {
    if (!open) return undefined
    const handler = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [open, onClose])

  if (!open) return null
  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/50 p-0 sm:items-center sm:p-4">
      <div
        role="dialog"
        aria-modal="true"
        aria-label={title}
        className={`card max-h-[92vh] w-full overflow-y-auto rounded-b-none p-6 sm:rounded-b-card ${wide ? 'sm:max-w-2xl' : 'sm:max-w-md'}`}
      >
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-lg font-bold">{title}</h2>
          <button type="button" aria-label="Close dialog" onClick={onClose} className="rounded p-1 hover:bg-soft">
            <X className="h-5 w-5" />
          </button>
        </div>
        {children}
      </div>
    </div>
  )
}

export function ConfirmDialog({
  open,
  title,
  message,
  confirmLabel = 'Confirm',
  danger = false,
  onConfirm,
  onCancel,
}: {
  open: boolean
  title: string
  message: string
  confirmLabel?: string
  danger?: boolean
  onConfirm: () => void
  onCancel: () => void
}) {
  return (
    <Modal open={open} title={title} onClose={onCancel}>
      <p className="text-sm text-muted">{message}</p>
      <div className="mt-6 flex justify-end gap-3">
        <button type="button" className="btn-outline" onClick={onCancel}>
          Cancel
        </button>
        <button type="button" className={danger ? 'btn-danger' : 'btn-primary'} onClick={onConfirm}>
          {confirmLabel}
        </button>
      </div>
    </Modal>
  )
}

export function Drawer({
  open,
  title,
  onClose,
  children,
}: {
  open: boolean
  title: string
  onClose: () => void
  children: ReactNode
}) {
  useEffect(() => {
    if (!open) return undefined
    const handler = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [open, onClose])

  if (!open) return null
  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-black/50">
      <aside role="dialog" aria-modal="true" aria-label={title} className="h-full w-full max-w-xl overflow-y-auto bg-surface p-6 shadow-2xl">
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-lg font-bold">{title}</h2>
          <button type="button" aria-label="Close panel" onClick={onClose} className="rounded p-1 hover:bg-soft">
            <X className="h-5 w-5" />
          </button>
        </div>
        {children}
      </aside>
    </div>
  )
}

export function Tabs<T extends string>({
  tabs,
  active,
  onChange,
}: {
  tabs: { value: T; label: string; count?: number }[]
  active: T
  onChange: (value: T) => void
}) {
  return (
    <div className="flex gap-1 overflow-x-auto border-b border-line" role="tablist">
      {tabs.map((tab) => (
        <button
          key={tab.value}
          type="button"
          role="tab"
          aria-selected={active === tab.value}
          onClick={() => onChange(tab.value)}
          className={`whitespace-nowrap border-b-2 px-4 py-2.5 text-sm font-semibold ${
            active === tab.value ? 'border-primary text-primary' : 'border-transparent text-muted hover:text-ink'
          }`}
        >
          {tab.label}
          {tab.count !== undefined && <span className="ml-1.5 rounded-full bg-soft px-2 py-0.5 text-xs">{tab.count}</span>}
        </button>
      ))}
    </div>
  )
}

export function Toggle({
  checked,
  onChange,
  label,
}: {
  checked: boolean
  onChange: (value: boolean) => void
  label: string
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      onClick={() => onChange(!checked)}
      className={`relative h-6 w-11 shrink-0 rounded-full transition ${checked ? 'bg-primary' : 'bg-line'}`}
    >
      <span className={`absolute top-0.5 h-5 w-5 rounded-full bg-white shadow transition-all ${checked ? 'left-[22px]' : 'left-0.5'}`} />
    </button>
  )
}

export function Stars({
  value,
  onChange,
  size = 'h-4 w-4',
}: {
  value: number
  onChange?: (value: number) => void
  size?: string
}) {
  return (
    <div className="flex items-center" aria-label={`${value} out of 5 stars`}>
      {[1, 2, 3, 4, 5].map((star) => (
        <button
          key={star}
          type="button"
          disabled={!onChange}
          aria-label={`${star} star`}
          onClick={() => onChange?.(star)}
          className="disabled:cursor-default"
        >
          <Star className={`${size} ${star <= Math.round(value) ? 'fill-warning text-warning' : 'text-line'}`} />
        </button>
      ))}
    </div>
  )
}

const BADGE_TONES: Record<string, string> = {
  APPLIED: 'bg-soft text-primary',
  VIEWED: 'bg-soft text-primary',
  SHORTLISTED: 'bg-success/15 text-success',
  INTERVIEW_SCHEDULED: 'bg-warning/15 text-warning',
  ON_HOLD: 'bg-line text-muted',
  OFFERED: 'bg-success/15 text-success',
  HIRED: 'bg-success/15 text-success',
  REJECTED: 'bg-danger/15 text-danger',
  WITHDRAWN: 'bg-line text-muted',
  ACTIVE: 'bg-success/15 text-success',
  APPROVED: 'bg-success/15 text-success',
  DRAFT: 'bg-line text-muted',
  PAUSED: 'bg-warning/15 text-warning',
  PENDING: 'bg-warning/15 text-warning',
  PENDING_REVIEW: 'bg-warning/15 text-warning',
  CLOSED: 'bg-line text-muted',
  EXPIRED: 'bg-danger/15 text-danger',
  BLOCKED: 'bg-danger/15 text-danger',
}

export function StatusBadge({ status }: { status: string }) {
  return (
    <span className={`inline-block rounded-full px-2.5 py-0.5 text-xs font-semibold ${BADGE_TONES[status] ?? 'bg-line text-muted'}`}>
      {STATUS_LABELS[status] ?? status}
    </span>
  )
}

export function Pagination({
  page,
  pageSize,
  total,
  onChange,
}: {
  page: number
  pageSize: number
  total: number
  onChange: (page: number) => void
}) {
  const totalPages = Math.max(1, Math.ceil(total / pageSize))
  if (totalPages <= 1) return null
  const pages = Array.from({ length: totalPages }, (_, index) => index + 1).filter(
    (value) => value === 1 || value === totalPages || Math.abs(value - page) <= 1,
  )
  return (
    <nav className="mt-6 flex items-center justify-center gap-1" aria-label="Pagination">
      <button type="button" className="btn-outline px-2" disabled={page <= 1} onClick={() => onChange(page - 1)} aria-label="Previous page">
        <ChevronLeft className="h-4 w-4" />
      </button>
      {pages.map((value, index) => (
        <span key={value} className="flex items-center gap-1">
          {index > 0 && value - pages[index - 1] > 1 && <span className="px-1 text-muted">…</span>}
          <button
            type="button"
            aria-current={value === page ? 'page' : undefined}
            onClick={() => onChange(value)}
            className={`h-9 min-w-9 rounded-lg px-2 text-sm font-semibold ${value === page ? 'bg-primary text-white' : 'hover:bg-soft'}`}
          >
            {value}
          </button>
        </span>
      ))}
      <button type="button" className="btn-outline px-2" disabled={page >= totalPages} onClick={() => onChange(page + 1)} aria-label="Next page">
        <ChevronRight className="h-4 w-4" />
      </button>
    </nav>
  )
}

export function Breadcrumbs({ items }: { items: { label: string; to?: string }[] }) {
  return (
    <nav aria-label="Breadcrumb" className="mb-4 flex flex-wrap items-center gap-1 text-sm text-muted">
      {items.map((item, index) => (
        <span key={item.label} className="flex items-center gap-1">
          {index > 0 && <ChevronRight className="h-3 w-3" />}
          {item.to ? (
            <Link to={item.to} className="hover:text-primary hover:underline">
              {item.label}
            </Link>
          ) : (
            <span className="text-ink">{item.label}</span>
          )}
        </span>
      ))}
    </nav>
  )
}

export function PageHeader({ title, subtitle, actions }: { title: string; subtitle?: string; actions?: ReactNode }) {
  return (
    <div className="mb-6 flex flex-wrap items-start justify-between gap-3">
      <div>
        <h1 className="text-2xl font-bold">{title}</h1>
        {subtitle && <p className="mt-1 text-sm text-muted">{subtitle}</p>}
      </div>
      {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
    </div>
  )
}

export function CompanyLogo({ src, name, size = 'h-12 w-12' }: { src: string; name: string; size?: string }) {
  if (!src) {
    return (
      <div className={`${size} flex shrink-0 items-center justify-center rounded-lg bg-soft font-bold text-primary`} aria-hidden="true">
        {name.slice(0, 1)}
      </div>
    )
  }
  return <img src={src} alt={`${name} logo`} className={`${size} shrink-0 rounded-lg object-cover`} />
}
