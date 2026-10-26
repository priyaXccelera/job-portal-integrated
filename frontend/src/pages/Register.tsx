import { useState } from 'react'
import type { FormEvent } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { Briefcase, UserSearch } from 'lucide-react'
import toast from 'react-hot-toast'
import { signup } from '../auth/auth'
import { AuthCard, FormAlert } from '../components/AuthCard'
import { CheckboxField, PasswordStrength, SelectField, TextField } from '../components/fields'
import { ALLOWED_RESUME_EXTENSIONS, MAX_RESUME_BYTES } from '../constants'
import { useSeo, useUnsavedWarning } from '../hooks'
import type { NormalizedError } from '../api/client'
import type { Role } from '../types'
import { formatBytes } from '../utils/format'
import { PASSWORD_HELP, hasErrors, validateEmail, validateMinLength, validateMobile, validatePassword } from '../validation'

export function Register() {
  const navigate = useNavigate()
  const [params] = useSearchParams()
  const [role, setRole] = useState<Role>(params.get('role') === 'RECRUITER' ? 'RECRUITER' : 'JOB_SEEKER')
  const [form, setForm] = useState({ name: '', email: '', mobile: '', password: '', companyName: '', workStatus: 'fresher' })
  const [resume, setResume] = useState<File | null>(null)
  const [resumeError, setResumeError] = useState('')
  const [terms, setTerms] = useState(false)
  const [attempted, setAttempted] = useState(false)
  const [loading, setLoading] = useState(false)
  const [serverError, setServerError] = useState('')
  const [serverFields, setServerFields] = useState<Record<string, string>>({})
  const isRecruiter = role === 'RECRUITER'
  useSeo('Register', 'Create your JobHub account as a job seeker or recruiter.')
  useUnsavedWarning(Boolean(form.name || form.email || form.mobile) && !loading)

  const errors = {
    name: validateMinLength(form.name, 2, 'Full name'),
    email: validateEmail(form.email),
    mobile: validateMobile(form.mobile),
    password: validatePassword(form.password),
    companyName: isRecruiter ? validateMinLength(form.companyName, 2, 'Company name') : '',
    terms: terms ? '' : 'You must accept the terms to continue',
  }
  const isValid = !hasErrors(errors) && !resumeError
  const set = (key: keyof typeof form) => (value: string) => setForm((current) => ({ ...current, [key]: value }))
  const shown = (key: keyof typeof errors) => (attempted ? errors[key] : '') || serverFields[key] || ''

  const onResume = (file: File | undefined) => {
    if (!file) return
    const extension = file.name.split('.').pop()?.toLowerCase() ?? ''
    if (!ALLOWED_RESUME_EXTENSIONS.includes(extension)) setResumeError('Resume must be a PDF, DOC or DOCX file')
    else if (file.size > MAX_RESUME_BYTES) setResumeError(`Resume must be smaller than ${formatBytes(MAX_RESUME_BYTES)}`)
    else setResumeError('')
    setResume(file)
  }

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    setAttempted(true)
    if (!isValid || loading) return
    setLoading(true)
    setServerError('')
    setServerFields({})
    try {
      await signup({
        name: form.name.trim(),
        email: form.email.trim(),
        mobile: form.mobile.trim(),
        password: form.password,
        role,
        companyName: isRecruiter ? form.companyName.trim() : undefined,
        workStatus: isRecruiter ? undefined : form.workStatus,
      })
      toast.success('Account created. Please verify your email.')
      navigate(`/verify-email?email=${encodeURIComponent(form.email.trim())}&mobile=${form.mobile.trim()}`)
    } catch (caught) {
      const error = caught as NormalizedError
      setServerError(error.message)
      setServerFields(error.fieldErrors ?? {})
    } finally {
      setLoading(false)
    }
  }

  return (
    <AuthCard title="Create your account" subtitle="Join JobHub in a minute" wide>
      <div className="mb-6 grid grid-cols-2 gap-3" role="radiogroup" aria-label="Account type">
        {[
          { value: 'JOB_SEEKER' as Role, label: "I'm looking for a job", icon: UserSearch },
          { value: 'RECRUITER' as Role, label: "I'm hiring", icon: Briefcase },
        ].map((option) => (
          <button
            key={option.value}
            type="button"
            role="radio"
            aria-checked={role === option.value}
            onClick={() => setRole(option.value)}
            className={`flex flex-col items-center gap-2 rounded-xl border-2 p-4 text-sm font-semibold ${role === option.value ? 'border-primary bg-soft text-primary' : 'border-line'}`}
          >
            <option.icon className="h-6 w-6" />
            {option.label}
          </button>
        ))}
      </div>

      <FormAlert message={serverError} />
      <form onSubmit={submit} noValidate className="space-y-4">
        <TextField label="Full name" required value={form.name} error={shown('name')} onChange={(event) => set('name')(event.target.value)} />
        <TextField label={isRecruiter ? 'Work email' : 'Email'} type="email" required value={form.email} error={shown('email')} onChange={(event) => set('email')(event.target.value)} />
        <TextField label="Mobile number" inputMode="numeric" maxLength={10} required value={form.mobile} help="10-digit Indian mobile number" error={shown('mobile')} onChange={(event) => set('mobile')(event.target.value.replace(/\D/g, ''))} />
        {isRecruiter && <TextField label="Company name" required value={form.companyName} error={shown('companyName')} onChange={(event) => set('companyName')(event.target.value)} />}
        <div className="space-y-2">
          <TextField label="Password" type="password" required autoComplete="new-password" value={form.password} help={PASSWORD_HELP} error={shown('password')} onChange={(event) => set('password')(event.target.value)} />
          <PasswordStrength value={form.password} />
        </div>
        {!isRecruiter && (
          <>
            <SelectField label="Work status" value={form.workStatus} options={[{ value: 'fresher', label: "I'm a fresher" }, { value: 'experienced', label: "I'm experienced" }]} onChange={(event) => set('workStatus')(event.target.value)} />
            <div className="space-y-1">
              <label htmlFor="resume-upload" className="block text-sm font-medium">
                Resume (optional)
              </label>
              <input id="resume-upload" type="file" accept=".pdf,.doc,.docx" className="input" onChange={(event) => onResume(event.target.files?.[0])} />
              {/* MOCK: the selected resume is validated but not uploaded until the user logs in and uses the resume manager. */}
              <p className={`text-xs ${resumeError ? 'text-danger' : 'text-muted'}`}>{resumeError || (resume ? resume.name : 'PDF, DOC or DOCX up to 2 MB')}</p>
            </div>
          </>
        )}
        <CheckboxField
          checked={terms}
          onChange={setTerms}
          error={attempted ? errors.terms : ''}
          label={
            <>
              I agree to the{' '}
              <Link to="/terms" className="font-semibold text-primary">Terms</Link> and{' '}
              <Link to="/privacy" className="font-semibold text-primary">Privacy Policy</Link>
            </>
          }
        />
        <button type="submit" className="btn-primary w-full py-2.5" disabled={loading || (attempted && !isValid)}>
          {loading ? 'Creating account…' : 'Register'}
        </button>
      </form>
      <p className="mt-4 text-center text-sm text-muted">
        Already registered?{' '}
        <Link to="/login" className="font-semibold text-primary">Login</Link>
      </p>
    </AuthCard>
  )
}
