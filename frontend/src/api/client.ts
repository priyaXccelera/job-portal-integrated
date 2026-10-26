import axios, { AxiosError } from 'axios'
import type { AxiosResponse, InternalAxiosRequestConfig } from 'axios'
import toast from 'react-hot-toast'
import type { ApiFieldError, ListResult } from '../types'

export const AUTH_STORAGE_KEY = 'auth_token'

interface ApiErrorBody {
  success: false
  error?: { code: string; message: string; details?: ApiFieldError[] }
}

export type NormalizedError = Error & {
  status?: number
  code?: string
  fieldErrors: Record<string, string>
}

// The ONLY env var read by the app for API wiring (see .env.example).
export const apiClient = axios.create({
  baseURL: `${import.meta.env.VITE_API_URL || ''}/api/v1`,
  headers: { 'Content-Type': 'application/json' },
})

function readSession(): { token?: string; refreshToken?: string } | null {
  try {
    const raw = localStorage.getItem(AUTH_STORAGE_KEY)
    return raw ? JSON.parse(raw) : null
  } catch {
    return null
  }
}

apiClient.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  const session = readSession()
  if (session?.token) {
    config.headers.Authorization = `Bearer ${session.token}`
  }
  return config
})

function forceLogout(): void {
  localStorage.removeItem(AUTH_STORAGE_KEY)
  window.dispatchEvent(new Event('auth-changed'))
  const returnTo = encodeURIComponent(window.location.pathname + window.location.search)
  window.location.assign(`/login?returnTo=${returnTo}`)
}

function messageFor(error: AxiosError<ApiErrorBody>): string {
  if (!error.response) return 'Network error. Please check your connection and retry.'
  const status = error.response.status
  if (status === 403) return 'You are not allowed to do that.'
  if (status === 404) return 'We could not find what you were looking for.'
  if (status >= 500) return 'Something went wrong on our side. Please retry.'
  return error.response.data?.error?.message ?? 'Request failed.'
}

let refreshing: Promise<string | null> | null = null

async function refreshToken(): Promise<string | null> {
  const session = readSession()
  if (!session?.refreshToken) return null
  try {
    const res = await axios.post(`${apiClient.defaults.baseURL}/auth/refresh`, {
      refreshToken: session.refreshToken,
    })
    const next = { ...session, ...res.data.data }
    localStorage.setItem(AUTH_STORAGE_KEY, JSON.stringify(next))
    return next.token as string
  } catch {
    return null
  }
}

apiClient.interceptors.response.use(
  (response) => response,
  async (error: AxiosError<ApiErrorBody>) => {
    const original = error.config as (InternalAxiosRequestConfig & { _retry?: boolean }) | undefined
    const isAuthCall = original?.url?.includes('/auth/')
    if (error.response?.status === 401 && original && !original._retry && !isAuthCall) {
      original._retry = true
      refreshing = refreshing ?? refreshToken()
      const nextToken = await refreshing
      refreshing = null
      if (nextToken) {
        original.headers.Authorization = `Bearer ${nextToken}`
        return apiClient(original)
      }
      toast.error('Your session expired. Please log in again.')
      forceLogout()
    } else if (!(isAuthCall && error.response?.status === 401)) {
      toast.error(messageFor(error))
    }
    const normalized = new Error(
      error.response?.data?.error?.message ?? messageFor(error),
    ) as NormalizedError
    normalized.status = error.response?.status
    normalized.code = error.response?.data?.error?.code
    normalized.fieldErrors = Object.fromEntries(
      (error.response?.data?.error?.details ?? []).map((detail) => [detail.field, detail.message]),
    )
    return Promise.reject(normalized)
  },
)

export function unwrap<T>(response: AxiosResponse): T {
  return response.data.data as T
}

export function unwrapList<T>(response: AxiosResponse): ListResult<T> {
  return { data: response.data.data as T[], meta: response.data.meta }
}
