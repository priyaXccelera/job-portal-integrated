import { Check } from 'lucide-react'
import { APPLICATION_STAGES, STATUS_LABELS } from '../constants'
import type { ApplicationStatus, HistoryEntry } from '../types'
import { formatDate } from '../utils/format'
import { StatusBadge } from './ui'

/** Horizontal Applied → Viewed → Shortlisted → Interview → Offered tracker with dated timeline */
export function StatusTracker({ status, history }: { status: ApplicationStatus; history: HistoryEntry[] }) {
  const reachedIndex = APPLICATION_STAGES.indexOf(status === 'HIRED' ? 'OFFERED' : status)
  const terminal = ['REJECTED', 'WITHDRAWN', 'ON_HOLD'].includes(status)
  const furthest = terminal
    ? Math.max(...history.map((entry) => APPLICATION_STAGES.indexOf(entry.status)), 0)
    : reachedIndex

  return (
    <div>
      <ol className="flex items-start" aria-label="Application progress">
        {APPLICATION_STAGES.map((stage, index) => {
          const done = index <= furthest
          const entry = history.find((item) => item.status === stage)
          return (
            <li key={stage} className="flex flex-1 flex-col items-center text-center">
              <div className="flex w-full items-center">
                <div className={`h-0.5 flex-1 ${index === 0 ? 'bg-transparent' : index <= furthest ? 'bg-primary' : 'bg-line'}`} />
                <span className={`flex h-6 w-6 items-center justify-center rounded-full text-xs ${done ? (terminal && index === furthest ? 'bg-muted text-white' : 'bg-primary text-white') : 'bg-line text-muted'}`}>
                  {done ? <Check className="h-3.5 w-3.5" /> : index + 1}
                </span>
                <div className={`h-0.5 flex-1 ${index === APPLICATION_STAGES.length - 1 ? 'bg-transparent' : index < furthest ? 'bg-primary' : 'bg-line'}`} />
              </div>
              <span className="mt-1 text-[11px] font-semibold leading-tight">{STATUS_LABELS[stage]}</span>
              {entry && <span className="text-[10px] text-muted">{formatDate(entry.at)}</span>}
            </li>
          )
        })}
      </ol>
      {terminal && (
        <p className="mt-3 text-sm">
          Current status: <StatusBadge status={status} />
        </p>
      )}
    </div>
  )
}

export function Timeline({ history }: { history: HistoryEntry[] }) {
  return (
    <ul className="space-y-2 border-l-2 border-line pl-4">
      {[...history].reverse().map((entry, index) => (
        <li key={`${entry.status}-${index}`} className="relative text-sm">
          <span className="absolute -left-[22px] top-1.5 h-2.5 w-2.5 rounded-full bg-primary" />
          <span className="font-semibold">{STATUS_LABELS[entry.status]}</span>
          <span className="ml-2 text-xs text-muted">{formatDate(entry.at)}</span>
          {entry.note && <p className="text-xs text-muted">“{entry.note}”</p>}
        </li>
      ))}
    </ul>
  )
}
