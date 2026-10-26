import { useState } from 'react'
import { Download, MessageSquare } from 'lucide-react'
import toast from 'react-hot-toast'
import { useNavigate } from 'react-router-dom'
import { addApplicationNote, scheduleInterview, setApplicationRating, setApplicationStatus } from '../data/store'
import { ALL_APPLICATION_STATUSES, STATUS_LABELS } from '../constants'
import type { Application, ApplicationStatus } from '../types'
import { formatCtc, formatDate } from '../utils/format'
import { SelectField, TextAreaField, TextField } from './fields'
import { Timeline } from './StatusTracker'
import { Drawer, Stars, StatusBadge } from './ui'

export function CandidateDrawer({
  application,
  onClose,
  onChanged,
}: {
  application: Application | null
  onClose: () => void
  onChanged: () => void
}) {
  const navigate = useNavigate()
  const [note, setNote] = useState('')
  const [statusMessage, setStatusMessage] = useState('')
  const [pendingStatus, setPendingStatus] = useState<ApplicationStatus | ''>('')
  const [interview, setInterview] = useState({ date: '', time: '', mode: 'Video call', linkOrAddress: '' })
  const [attempted, setAttempted] = useState(false)

  if (!application) return null

  const interviewErrors = {
    date: interview.date ? '' : 'Pick a date',
    time: interview.time ? '' : 'Pick a time',
    linkOrAddress: interview.linkOrAddress.trim() ? '' : 'Enter a meeting link or address',
  }
  const interviewValid = !interviewErrors.date && !interviewErrors.time && !interviewErrors.linkOrAddress

  const run = async (action: () => Promise<unknown>, message: string) => {
    try {
      await action()
      toast.success(message)
      onChanged()
    } catch {
      // API client shows the error toast
    }
  }

  return (
    <Drawer open title={application.candidateName} onClose={onClose}>
      <div className="space-y-6">
        <section>
          <p className="text-sm text-muted">{application.headline}</p>
          <div className="mt-2 flex flex-wrap items-center gap-3 text-sm">
            <StatusBadge status={application.status} />
            <span>{application.experience} yrs</span>
            <span>{application.location}</span>
            <span className="font-semibold text-success">{application.matchPercentage}% match</span>
          </div>
          <dl className="mt-3 grid grid-cols-2 gap-3 text-sm">
            <div><dt className="text-muted">Current CTC</dt><dd>{formatCtc(application.currentCtc)}</dd></div>
            <div><dt className="text-muted">Expected CTC</dt><dd>{formatCtc(application.expectedCtc)}</dd></div>
            <div><dt className="text-muted">Notice period</dt><dd>{application.noticePeriod || '—'}</dd></div>
            <div><dt className="text-muted">Education</dt><dd>{application.education || '—'}</dd></div>
          </dl>
          <div className="mt-3 flex flex-wrap gap-2">
            {application.skills.map((skill) => <span key={skill} className="chip">{skill}</span>)}
          </div>
          <div className="mt-4 flex flex-wrap gap-2">
            {/* MOCK: resume download hands back a placeholder file; the real file comes from the candidate's resume endpoint. */}
            <button
              type="button"
              className="btn-outline"
              onClick={() => {
                const url = URL.createObjectURL(new Blob([`Resume placeholder for ${application.candidateName}`], { type: 'text/plain' }))
                const anchor = document.createElement('a')
                anchor.href = url
                anchor.download = application.resumeName
                anchor.click()
                URL.revokeObjectURL(url)
              }}
            >
              <Download className="h-4 w-4" />
              Resume ({application.resumeName})
            </button>
            <button type="button" className="btn-outline" onClick={() => navigate('/messages')}>
              <MessageSquare className="h-4 w-4" />
              Message
            </button>
          </div>
        </section>

        {application.coverNote && (
          <section>
            <h3 className="mb-1 font-bold">Cover note</h3>
            <p className="text-sm text-muted">{application.coverNote}</p>
          </section>
        )}

        <section>
          <h3 className="mb-2 font-bold">Screening answers</h3>
          {application.answers.length === 0 && <p className="text-sm text-muted">No screening questions for this job.</p>}
          <ul className="space-y-2">
            {application.answers.map((entry) => (
              <li key={entry.questionId} className="rounded-lg bg-canvas p-3 text-sm">
                <p className="font-semibold">{entry.question}</p>
                <p className="text-muted">{entry.answer}</p>
              </li>
            ))}
          </ul>
        </section>

        <section>
          <h3 className="mb-2 font-bold">Rating</h3>
          <Stars value={application.rating} size="h-6 w-6" onChange={(value) => run(() => setApplicationRating(application.id, value), 'Rating saved')} />
        </section>

        <section className="space-y-2">
          <h3 className="font-bold">Change status</h3>
          <SelectField
            label="Status"
            value={pendingStatus || application.status}
            options={ALL_APPLICATION_STATUSES.map((status) => ({ value: status, label: STATUS_LABELS[status] }))}
            onChange={(event) => setPendingStatus(event.target.value as ApplicationStatus)}
          />
          {pendingStatus && pendingStatus !== application.status && (
            <>
              <TextAreaField label="Message to candidate (optional)" rows={2} value={statusMessage} onChange={(event) => setStatusMessage(event.target.value)} />
              <button
                type="button"
                className="btn-primary"
                onClick={async () => {
                  await run(() => setApplicationStatus([application.id], pendingStatus, statusMessage), `Moved to ${STATUS_LABELS[pendingStatus]}`)
                  setPendingStatus('')
                  setStatusMessage('')
                }}
              >
                Update status
              </button>
            </>
          )}
        </section>

        <section className="space-y-3">
          <h3 className="font-bold">Schedule interview</h3>
          <div className="grid grid-cols-2 gap-3">
            <TextField label="Date" type="date" value={interview.date} error={attempted ? interviewErrors.date : ''} onChange={(event) => setInterview({ ...interview, date: event.target.value })} />
            <TextField label="Time" type="time" value={interview.time} error={attempted ? interviewErrors.time : ''} onChange={(event) => setInterview({ ...interview, time: event.target.value })} />
          </div>
          <SelectField label="Mode" value={interview.mode} options={['Video call', 'Phone', 'On-site']} onChange={(event) => setInterview({ ...interview, mode: event.target.value })} />
          <TextField label="Link or address" value={interview.linkOrAddress} error={attempted ? interviewErrors.linkOrAddress : ''} onChange={(event) => setInterview({ ...interview, linkOrAddress: event.target.value })} />
          <button
            type="button"
            className="btn-primary"
            onClick={async () => {
              setAttempted(true)
              if (!interviewValid) return
              await run(
                () => scheduleInterview(application.id, { dateTime: new Date(`${interview.date}T${interview.time}`).toISOString(), mode: interview.mode, linkOrAddress: interview.linkOrAddress.trim(), notes: '' }),
                'Interview scheduled',
              )
              setAttempted(false)
            }}
          >
            Schedule interview
          </button>
        </section>

        <section className="space-y-2">
          <h3 className="font-bold">Notes</h3>
          <ul className="space-y-2">
            {application.notes.map((entry) => (
              <li key={entry.id} className="rounded-lg bg-canvas p-3 text-sm">
                {entry.text}
                <span className="block text-xs text-muted">{formatDate(entry.at)}</span>
              </li>
            ))}
          </ul>
          <TextAreaField label="Add a note" rows={2} value={note} onChange={(event) => setNote(event.target.value)} />
          <button
            type="button"
            className="btn-outline"
            disabled={!note.trim()}
            onClick={async () => {
              await run(() => addApplicationNote(application.id, note.trim()), 'Note added')
              setNote('')
            }}
          >
            Save note
          </button>
        </section>

        <section>
          <h3 className="mb-2 font-bold">Status history</h3>
          <Timeline history={application.history} />
        </section>
      </div>
    </Drawer>
  )
}
