import { useState } from 'react'
import { BOARD_COLUMNS } from '../constants'
import type { Application, ApplicationStatus } from '../types'
import { Stars } from './ui'

/** Kanban pipeline. Dragging a card onto a column calls onMove(application, newStatus). */
export function KanbanBoard({
  applications,
  onMove,
  onOpen,
}: {
  applications: Application[]
  onMove: (application: Application, status: ApplicationStatus) => void
  onOpen: (application: Application) => void
}) {
  const [draggingId, setDraggingId] = useState<string | null>(null)
  const [overColumn, setOverColumn] = useState<ApplicationStatus | null>(null)

  return (
    <div className="flex gap-3 overflow-x-auto pb-3" aria-label="Applicant pipeline">
      {BOARD_COLUMNS.map((column) => {
        const cards = applications.filter((application) => application.status === column.status)
        return (
          <section
            key={column.status}
            aria-label={`${column.label} column`}
            data-testid={`column-${column.status}`}
            className={`w-64 shrink-0 rounded-card border p-2 ${overColumn === column.status ? 'border-primary bg-soft' : 'border-line bg-canvas'}`}
            onDragOver={(event) => {
              event.preventDefault()
              setOverColumn(column.status)
            }}
            onDragLeave={() => setOverColumn(null)}
            onDrop={(event) => {
              event.preventDefault()
              const dropped = applications.find((application) => application.id === (draggingId ?? event.dataTransfer.getData('text/plain')))
              setOverColumn(null)
              setDraggingId(null)
              if (dropped && dropped.status !== column.status) onMove(dropped, column.status)
            }}
          >
            <h3 className="mb-2 flex items-center justify-between px-1 text-sm font-bold">
              {column.label}
              <span className="rounded-full bg-surface px-2 text-xs">{cards.length}</span>
            </h3>
            <div className="min-h-24 space-y-2">
              {cards.map((application) => (
                <div
                  key={application.id}
                  draggable
                  role="button"
                  tabIndex={0}
                  aria-label={`${application.candidateName}, ${column.label}`}
                  className="card cursor-grab p-3 text-sm active:cursor-grabbing"
                  onDragStart={(event) => {
                    setDraggingId(application.id)
                    event.dataTransfer.setData('text/plain', application.id)
                  }}
                  onDragEnd={() => setDraggingId(null)}
                  onClick={() => onOpen(application)}
                  onKeyDown={(event) => {
                    if (event.key === 'Enter') onOpen(application)
                  }}
                >
                  <p className="font-semibold">{application.candidateName}</p>
                  <p className="truncate text-xs text-muted">{application.headline}</p>
                  <div className="mt-2 flex items-center justify-between">
                    <Stars value={application.rating} size="h-3 w-3" />
                    <span className="text-xs font-semibold text-success">{application.matchPercentage}%</span>
                  </div>
                </div>
              ))}
            </div>
          </section>
        )
      })}
    </div>
  )
}
