const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/
const MOBILE_PATTERN = /^[6-9]\d{9}$/

export function validateRequired(value: string, label = 'This field'): string {
  return value.trim() ? '' : `${label} is required`
}

export function validateEmail(value: string): string {
  if (!value.trim()) return 'Email is required'
  return EMAIL_PATTERN.test(value.trim()) ? '' : 'Enter a valid email address'
}

export function validateMobile(value: string): string {
  if (!value.trim()) return 'Mobile number is required'
  return MOBILE_PATTERN.test(value.trim()) ? '' : 'Enter a valid 10-digit mobile number'
}

export function validateIdentifier(value: string): string {
  if (!value.trim()) return 'Email or mobile is required'
  const trimmed = value.trim()
  return EMAIL_PATTERN.test(trimmed) || MOBILE_PATTERN.test(trimmed)
    ? ''
    : 'Enter a valid email or 10-digit mobile'
}

export const PASSWORD_HELP = 'At least 8 characters with an uppercase letter, a number and a symbol'

export function passwordScore(value: string): number {
  let score = 0
  if (value.length >= 8) score += 1
  if (/[A-Z]/.test(value) && /[a-z]/.test(value)) score += 1
  if (/\d/.test(value)) score += 1
  if (/[^A-Za-z0-9]/.test(value)) score += 1
  return score
}

export function validatePassword(value: string): string {
  if (!value) return 'Password is required'
  return passwordScore(value) >= 4 ? '' : PASSWORD_HELP
}

export function validateConfirm(password: string, confirm: string): string {
  if (!confirm) return 'Please confirm your password'
  return password === confirm ? '' : 'Passwords do not match'
}

export function validateOtp(value: string, length = 6): string {
  return new RegExp(`^\\d{${length}}$`).test(value) ? '' : `Enter the ${length}-digit code`
}

export function validateMinLength(value: string, min: number, label: string): string {
  if (!value.trim()) return `${label} is required`
  return value.trim().length >= min ? '' : `${label} must be at least ${min} characters`
}

export function hasErrors(errors: Record<string, string>): boolean {
  return Object.values(errors).some(Boolean)
}
