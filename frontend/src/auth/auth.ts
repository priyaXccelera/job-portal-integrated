import { useMemo, useSyncExternalStore } from 'react'
import { apiClient, AUTH_STORAGE_KEY, unwrap } from '../api/client'
import { DEMO_OTP } from '../constants'
import { mockUsers } from '../data/mockData'
import type { MockUser, Role, Session, User } from '../types'

// TODO(USE_MOCK): verify path + response shape against the real
// backend's OpenAPI schema before flipping this to false.
// Uses the real backend by default; set VITE_DEMO_MODE=true to use local mock data.
export const USE_MOCK = import.meta.env.VITE_DEMO_MODE === 'true'

const USERS_KEY = 'app_users'

function notify(): void {
  window.dispatchEvent(new Event('auth-changed'))
}

// MOCK: demo users plus signed-up / edited users persisted in localStorage
export function getUsers(): MockUser[] {
  const raw = localStorage.getItem(USERS_KEY)
  const stored: MockUser[] = raw ? JSON.parse(raw) : []
  const overrides = new Map(stored.map((user) => [user.id, user]))
  const base = mockUsers.map((user) => overrides.get(user.id) ?? user)
  const added = stored.filter((user) => !mockUsers.some((seed) => seed.id === user.id))
  return [...base, ...added]
}

export function saveUser(user: MockUser): void {
  const raw = localStorage.getItem(USERS_KEY)
  const stored: MockUser[] = raw ? JSON.parse(raw) : []
  const next = stored.filter((entry) => entry.id !== user.id)
  next.push(user)
  localStorage.setItem(USERS_KEY, JSON.stringify(next))
  notify()
}

function toUser(user: MockUser): User {
  const { password: _password, ...rest } = user
  return rest
}

function startSession(user: MockUser): void {
  const session: Session = {
    token: `mock-token-${user.id}`,
    refreshToken: `mock-refresh-${user.id}`,
    user: toUser(user),
  }
  localStorage.setItem(AUTH_STORAGE_KEY, JSON.stringify(session))
  notify()
}

function findByIdentifier(identifier: string): MockUser | undefined {
  const value = identifier.trim().toLowerCase()
  return getUsers().find((user) => user.email.toLowerCase() === value || user.mobile === value)
}

// MOCK: stands in for POST /auth/login
function localLogin(identifier: string, password: string): boolean {
  const user = findByIdentifier(identifier)
  if (!user || user.password !== password || user.blocked) return false
  startSession(user)
  return true
}

// MOCK: stands in for POST /auth/register
function localSignup(input: RegisterInput): User {
  if (findByIdentifier(input.email)) throw new Error('An account with this email already exists')
  if (findByIdentifier(input.mobile)) throw new Error('An account with this mobile already exists')
  const user: MockUser = {
    id: `u-${Date.now()}`,
    name: input.name,
    email: input.email,
    mobile: input.mobile,
    role: input.role,
    password: input.password,
    emailVerified: false,
    mobileVerified: false,
    companyId: input.role === 'RECRUITER' ? `c${Date.now()}` : undefined,
  }
  if (user.companyId && input.companyName) {
    localStorage.setItem(`company_name_${user.companyId}`, input.companyName)
  }
  saveUser(user)
  return toUser(user)
}

export interface RegisterInput {
  name: string
  email: string
  mobile: string
  password: string
  role: Role
  companyName?: string
  workStatus?: string
}

export async function login(identifier: string, password: string): Promise<boolean> {
  if (USE_MOCK) return localLogin(identifier, password)
  const res = await apiClient.post('/auth/login', { identifier, password })
  localStorage.setItem(AUTH_STORAGE_KEY, JSON.stringify(unwrap(res)))
  notify()
  return true
}

export async function signup(input: RegisterInput): Promise<User> {
  if (USE_MOCK) return localSignup(input)
  const res = await apiClient.post('/auth/register', input)
  return unwrap<User>(res)
}

export async function sendOtp(mobile: string): Promise<void> {
  if (USE_MOCK) {
    // MOCK: no SMS is sent; every OTP is DEMO_OTP
    return
  }
  await apiClient.post('/auth/send-otp', { mobile })
}

export async function verifyOtp(mobile: string, otp: string): Promise<boolean> {
  if (USE_MOCK) {
    // MOCK: accepts the fixed demo OTP only
    const user = findByIdentifier(mobile)
    if (otp !== DEMO_OTP) return false
    if (user) saveUser({ ...user, mobileVerified: true })
    return true
  }
  await apiClient.post('/auth/verify-otp', { mobile, otp })
  return true
}

export async function loginWithOtp(mobile: string, otp: string): Promise<boolean> {
  if (USE_MOCK) {
    // MOCK: accepts the fixed demo OTP for any registered mobile
    const user = findByIdentifier(mobile)
    if (!user || otp !== DEMO_OTP || user.blocked) return false
    startSession(user)
    return true
  }
  const res = await apiClient.post('/auth/login-otp', { mobile, otp })
  localStorage.setItem(AUTH_STORAGE_KEY, JSON.stringify(unwrap(res)))
  notify()
  return true
}

export async function verifyEmail(token: string, email: string): Promise<boolean> {
  if (USE_MOCK) {
    // MOCK: any non-empty token verifies the email
    const user = findByIdentifier(email)
    if (!token.trim()) return false
    if (user) saveUser({ ...user, emailVerified: true })
    return true
  }
  await apiClient.post('/auth/verify-email', { token })
  return true
}

export async function forgotPassword(identifier: string): Promise<void> {
  if (USE_MOCK) {
    // MOCK: pretends a reset link/OTP was sent; reset code is DEMO_OTP
    if (!findByIdentifier(identifier)) throw new Error('No account found with these details')
    return
  }
  await apiClient.post('/auth/forgot-password', { identifier })
}

export async function resetPassword(identifier: string, code: string, password: string): Promise<void> {
  if (USE_MOCK) {
    // MOCK: reset code must equal DEMO_OTP
    const user = findByIdentifier(identifier)
    if (!user || code !== DEMO_OTP) throw new Error('Invalid or expired reset code')
    saveUser({ ...user, password })
    return
  }
  await apiClient.post('/auth/reset-password', { token: code, identifier, password })
}

export async function changePassword(oldPassword: string, newPassword: string): Promise<void> {
  if (USE_MOCK) {
    // MOCK: verifies against the locally stored password
    const current = currentUser()
    const user = getUsers().find((entry) => entry.id === current?.user.id)
    if (!user || user.password !== oldPassword) throw new Error('Current password is incorrect')
    saveUser({ ...user, password: newPassword })
    return
  }
  await apiClient.post('/auth/change-password', { oldPassword, newPassword })
}

export async function updateAccount(patch: { email?: string; mobile?: string }): Promise<void> {
  if (USE_MOCK) {
    // MOCK: stands in for an account update endpoint
    const current = currentUser()
    const user = getUsers().find((entry) => entry.id === current?.user.id)
    if (!user) return
    const updated = { ...user, ...patch }
    saveUser(updated)
    startSession(updated)
    return
  }
  await apiClient.put('/profile/me', patch)
}

export async function logout(): Promise<void> {
  if (!USE_MOCK) {
    try {
      await apiClient.post('/auth/logout')
    } catch {
      // the session is cleared locally either way
    }
  }
  localStorage.removeItem(AUTH_STORAGE_KEY)
  notify()
}

export function isAuthenticated(): boolean {
  return Boolean(localStorage.getItem(AUTH_STORAGE_KEY))
}

export function currentUser(): Session | null {
  try {
    const raw = localStorage.getItem(AUTH_STORAGE_KEY)
    return raw ? (JSON.parse(raw) as Session) : null
  } catch {
    return null
  }
}

export function currentRole(): Role | null {
  return currentUser()?.user.role ?? null
}

export function homeFor(role: Role | null | undefined): string {
  if (role === 'RECRUITER') return '/recruiter/dashboard'
  if (role === 'ADMIN') return '/admin/dashboard'
  if (role === 'JOB_SEEKER') return '/seeker/dashboard'
  return '/'
}

function subscribe(callback: () => void): () => void {
  window.addEventListener('auth-changed', callback)
  window.addEventListener('storage', callback)
  return () => {
    window.removeEventListener('auth-changed', callback)
    window.removeEventListener('storage', callback)
  }
}

function snapshot(): string {
  return localStorage.getItem(AUTH_STORAGE_KEY) ?? ''
}

/** React hook that re-renders on login / logout */
export function useAuth(): { user: User | null; role: Role | null; isLoggedIn: boolean } {
  const raw = useSyncExternalStore(subscribe, snapshot)
  return useMemo(() => {
    const session: Session | null = raw ? JSON.parse(raw) : null
    return {
      user: session?.user ?? null,
      role: session?.user.role ?? null,
      isLoggedIn: Boolean(session),
    }
  }, [raw])
}
