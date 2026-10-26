import { useRef, useState } from 'react'
import { Download, FileText, Star, Trash2, UploadCloud } from 'lucide-react'
import toast from 'react-hot-toast'
import { ALLOWED_RESUME_EXTENSIONS, MAX_RESUME_BYTES } from '../constants'
import { deleteResume, downloadResume, getResumes, setDefaultResume, uploadResume } from '../data/store'
import { useAsync } from '../hooks'
import { formatBytes, formatDate } from '../utils/format'
import { ConfirmDialog, EmptyState, Skeleton } from './ui'

export function ResumeManager({ onChange }: { onChange?: () => void }) {
  const resumes = useAsync(() => getResumes(), [])
  const input = useRef<HTMLInputElement>(null)
  const [dragging, setDragging] = useState(false)
  const [progress, setProgress] = useState<number | null>(null)
  const [error, setError] = useState('')
  const [toDelete, setToDelete] = useState<string | null>(null)

  const handleFile = async (file: File | undefined) => {
    if (!file) return
    const extension = file.name.split('.').pop()?.toLowerCase() ?? ''
    if (!ALLOWED_RESUME_EXTENSIONS.includes(extension)) {
      setError('Only PDF, DOC and DOCX files are allowed')
      return
    }
    if (file.size > MAX_RESUME_BYTES) {
      setError(`File is too large. Maximum size is ${formatBytes(MAX_RESUME_BYTES)}`)
      return
    }
    setError('')
    setProgress(0)
    try {
      await uploadResume(file, setProgress)
      toast.success('Resume uploaded')
      resumes.reload()
      onChange?.()
    } catch {
      // API client shows the error toast
    } finally {
      setProgress(null)
    }
  }

  return (
    <section className="card p-5" aria-label="Resume manager">
      <h2 className="mb-3 text-lg font-bold">Resume</h2>
      <div
        onDragOver={(event) => {
          event.preventDefault()
          setDragging(true)
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(event) => {
          event.preventDefault()
          setDragging(false)
          handleFile(event.dataTransfer.files[0])
        }}
        className={`flex flex-col items-center rounded-xl border-2 border-dashed p-6 text-center ${dragging ? 'border-primary bg-soft' : 'border-line'}`}
      >
        <UploadCloud className="h-8 w-8 text-primary" aria-hidden="true" />
        <p className="mt-2 text-sm">Drag and drop your resume here, or</p>
        <button type="button" className="btn-outline mt-2" onClick={() => input.current?.click()}>
          Browse files
        </button>
        <input ref={input} type="file" accept=".pdf,.doc,.docx" className="sr-only" aria-label="Upload resume" onChange={(event) => handleFile(event.target.files?.[0])} />
        <p className="mt-2 text-xs text-muted">PDF, DOC or DOCX · max {formatBytes(MAX_RESUME_BYTES)}</p>
        {error && <p className="mt-2 text-sm text-danger" role="alert">{error}</p>}
        {progress !== null && (
          <div className="mt-3 w-full max-w-xs" role="progressbar" aria-valuenow={progress} aria-valuemin={0} aria-valuemax={100}>
            <progress className="h-2 w-full" value={progress} max={100} />
            <p className="text-xs text-muted">Uploading… {progress}%</p>
          </div>
        )}
      </div>

      <div className="mt-4 space-y-2">
        {resumes.loading && <Skeleton className="h-14 w-full" />}
        {resumes.data?.length === 0 && <EmptyState title="No resume uploaded" message="Upload a resume so recruiters can see your experience." />}
        {resumes.data?.map((resume) => (
          <div key={resume.id} className="flex flex-wrap items-center gap-3 rounded-lg border border-line p-3">
            <FileText className="h-5 w-5 text-primary" />
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-semibold">{resume.name}</p>
              <p className="text-xs text-muted">
                {formatBytes(resume.size)} · Uploaded {formatDate(resume.uploadedAt)}
              </p>
            </div>
            {resume.isDefault ? (
              <span className="chip">
                <Star className="h-3 w-3 fill-primary" />
                Default
              </span>
            ) : (
              <button
                type="button"
                className="text-xs font-semibold text-primary"
                onClick={async () => {
                  await setDefaultResume(resume.id)
                  toast.success('Default resume updated')
                  resumes.reload()
                }}
              >
                Mark default
              </button>
            )}
            <button type="button" aria-label={`Download ${resume.name}`} className="rounded p-2 hover:bg-soft" onClick={() => downloadResume(resume)}>
              <Download className="h-4 w-4" />
            </button>
            <button type="button" aria-label={`Delete ${resume.name}`} className="rounded p-2 text-danger hover:bg-soft" onClick={() => setToDelete(resume.id)}>
              <Trash2 className="h-4 w-4" />
            </button>
          </div>
        ))}
      </div>

      <ConfirmDialog
        open={Boolean(toDelete)}
        danger
        title="Delete resume?"
        message="This resume will be permanently removed."
        confirmLabel="Delete"
        onCancel={() => setToDelete(null)}
        onConfirm={async () => {
          if (toDelete) await deleteResume(toDelete)
          setToDelete(null)
          toast.success('Resume deleted')
          resumes.reload()
          onChange?.()
        }}
      />
    </section>
  )
}
