import { useState } from 'react'
import type { FormEvent } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import toast from 'react-hot-toast'
import { currentRole, homeFor, loginWithOtp, sendOtp } from '../auth/auth'
import { AuthCard, FormAlert } from '../components/AuthCard'
import { OtpInput, TextField } from '../components/fields'
import { DEMO_OTP, OTP_RESEND_SECONDS } from '../constants'
import { useCountdown, useSeo } from '../hooks'
import { validateMobile, validateOtp } from '../validation'

export function LoginOtp() {
  const navigate = useNavigate()
  const [params] = useSearchParams()
  const [mobile, setMobile] = useState('')
  const [otp, setOtp] = useState('')
  const [otpSent, setOtpSent] = useState(false)
  const [attempted, setAttempted] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const { remaining, restart } = useCountdown(OTP_RESEND_SECONDS)
  useSeo('Login with OTP', 'Log in to JobHub using a one time password.')

  const mobileError = validateMobile(mobile)
  const otpError = otpSent ? validateOtp(otp) : ''

  const requestOtp = async () => {
    setAttempted(true)
    if (mobileError) return
    setLoading(true)
    try {
      await sendOtp(mobile)
      setOtpSent(true)
      restart()
      setAttempted(false)
      toast.success('OTP sent to your mobile')
    } catch (caught) {
      setError((caught as Error).message)
    } finally {
      setLoading(false)
    }
  }

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    if (!otpSent) {
      await requestOtp()
      return
    }
    setAttempted(true)
    if (otpError || loading) return
    setLoading(true)
    setError('')
    try {
      if (await loginWithOtp(mobile, otp)) {
        const returnTo = params.get('returnTo')
        navigate(returnTo && returnTo.startsWith('/') ? returnTo : homeFor(currentRole()), { replace: true })
      } else {
        setError('Incorrect OTP or unregistered mobile number')
      }
    } catch (caught) {
      setError((caught as Error).message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <AuthCard title="Login with OTP" subtitle="We will send a 6-digit code to your mobile number.">
      <FormAlert message={error} />
      <form onSubmit={submit} noValidate className="space-y-4">
        <TextField label="Mobile number" inputMode="numeric" maxLength={10} required disabled={otpSent} value={mobile} error={attempted ? mobileError : ''} onChange={(event) => setMobile(event.target.value.replace(/\D/g, ''))} />
        {otpSent && (
          <>
            <OtpInput value={otp} onChange={setOtp} />
            {attempted && otpError && <p className="text-center text-xs text-danger" role="alert">{otpError}</p>}
            {/* MOCK: demo mode accepts the fixed OTP below; no SMS is sent. */}
            <p className="text-center text-xs text-muted">Demo OTP: {DEMO_OTP}</p>
          </>
        )}
        <button type="submit" className="btn-primary w-full py-2.5" disabled={loading}>
          {loading ? 'Please wait…' : otpSent ? 'Verify & login' : 'Send OTP'}
        </button>
      </form>
      {otpSent && (
        <div className="mt-4 text-center text-sm">
          {remaining > 0 ? (
            <span className="text-muted">Resend OTP in {remaining}s</span>
          ) : (
            <button type="button" className="font-semibold text-primary" onClick={requestOtp}>
              Resend OTP
            </button>
          )}
        </div>
      )}
      <p className="mt-4 text-center text-sm text-muted">
        <Link to="/login" className="font-semibold text-primary">
          Login with password instead
        </Link>
      </p>
    </AuthCard>
  )
}
