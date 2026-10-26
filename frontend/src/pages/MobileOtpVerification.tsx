import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { Smartphone } from 'lucide-react'
import toast from 'react-hot-toast'
import { sendOtp, verifyOtp } from '../auth/auth'
import { AuthCard, FormAlert } from '../components/AuthCard'
import { OtpInput, TextField } from '../components/fields'
import { DEMO_OTP, OTP_RESEND_SECONDS } from '../constants'
import { useCountdown, useSeo } from '../hooks'
import { validateMobile, validateOtp } from '../validation'

export function MobileOtpVerification() {
  const navigate = useNavigate()
  const [params] = useSearchParams()
  const [mobile, setMobile] = useState(params.get('mobile') ?? '')
  const [otp, setOtp] = useState('')
  const [attempted, setAttempted] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const { remaining, restart } = useCountdown(OTP_RESEND_SECONDS)
  useSeo('Verify mobile', 'Verify your mobile number with a one time password.')

  const mobileError = validateMobile(mobile)
  const otpError = validateOtp(otp)

  useEffect(() => {
    if (!validateMobile(params.get('mobile') ?? '')) sendOtp(params.get('mobile') ?? '').catch(() => undefined)
  }, [params])

  const resend = async () => {
    if (mobileError) return
    await sendOtp(mobile)
    restart()
    toast.success('OTP sent')
  }

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    setAttempted(true)
    if (mobileError || otpError || loading) return
    setLoading(true)
    setError('')
    try {
      if (await verifyOtp(mobile, otp)) {
        toast.success('Mobile verified. You can log in now.')
        navigate('/login')
      } else {
        setError('Incorrect OTP. Please try again.')
      }
    } catch (caught) {
      setError((caught as Error).message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <AuthCard title="Verify your mobile" subtitle="Enter the 6-digit code we sent by SMS.">
      <Smartphone className="mx-auto mb-4 h-12 w-12 text-primary" aria-hidden="true" />
      <FormAlert message={error} />
      <form onSubmit={submit} noValidate className="space-y-4">
        <TextField label="Mobile number" inputMode="numeric" maxLength={10} value={mobile} error={attempted ? mobileError : ''} onChange={(event) => setMobile(event.target.value.replace(/\D/g, ''))} />
        <OtpInput value={otp} onChange={setOtp} />
        {attempted && otpError && <p className="text-center text-xs text-danger" role="alert">{otpError}</p>}
        {/* MOCK: demo mode accepts the fixed OTP below; no SMS is sent. */}
        <p className="text-center text-xs text-muted">Demo OTP: {DEMO_OTP}</p>
        <button type="submit" className="btn-primary w-full" disabled={loading || (attempted && Boolean(mobileError || otpError))}>
          {loading ? 'Verifying…' : 'Verify'}
        </button>
      </form>
      <div className="mt-4 text-center text-sm">
        {remaining > 0 ? (
          <span className="text-muted">Resend OTP in {remaining}s</span>
        ) : (
          <button type="button" className="font-semibold text-primary" onClick={resend}>
            Resend OTP
          </button>
        )}
      </div>
      <p className="mt-3 text-center text-sm text-muted">
        <Link to="/login" className="font-semibold text-primary">
          Skip for now
        </Link>
      </p>
    </AuthCard>
  )
}
