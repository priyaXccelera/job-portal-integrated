import { useCallback, useEffect, useRef, useState } from 'react'

export function useDebouncedValue<T>(value: T, delayMs = 250): T {
  const [debounced, setDebounced] = useState(value)
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delayMs)
    return () => clearTimeout(timer)
  }, [value, delayMs])
  return debounced
}

export interface AsyncState<T> {
  data: T | undefined
  loading: boolean
  error: string
  reload: () => void
  setData: (value: T | undefined) => void
}

/** Runs an async loader whenever deps change; exposes loading / error / retry. */
export function useAsync<T>(loader: () => Promise<T>, deps: unknown[]): AsyncState<T> {
  const [data, setData] = useState<T | undefined>(undefined)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [version, setVersion] = useState(0)
  const loaderRef = useRef(loader)
  loaderRef.current = loader

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError('')
    loaderRef
      .current()
      .then((result) => {
        if (!cancelled) setData(result)
      })
      .catch((caught: Error) => {
        if (!cancelled) setError(caught.message || 'Something went wrong')
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, version])

  const reload = useCallback(() => setVersion((current) => current + 1), [])
  return { data, loading, error, reload, setData }
}

/** Warns before leaving the page while a form has unsaved changes. */
export function useUnsavedWarning(isDirty: boolean): void {
  useEffect(() => {
    if (!isDirty) return undefined
    const handler = (event: BeforeUnloadEvent) => {
      event.preventDefault()
      event.returnValue = ''
    }
    window.addEventListener('beforeunload', handler)
    return () => window.removeEventListener('beforeunload', handler)
  }, [isDirty])
}

/** Sets document title, meta description and optional JSON-LD structured data. */
export function useSeo(title: string, description: string, jsonLd?: object): void {
  const serialized = jsonLd ? JSON.stringify(jsonLd) : ''
  useEffect(() => {
    document.title = title ? `${title} | JobHub` : 'JobHub - Find your dream job'
    let meta = document.querySelector('meta[name="description"]')
    if (!meta) {
      meta = document.createElement('meta')
      meta.setAttribute('name', 'description')
      document.head.appendChild(meta)
    }
    meta.setAttribute('content', description)
    let script = document.getElementById('json-ld')
    if (serialized) {
      if (!script) {
        script = document.createElement('script')
        script.id = 'json-ld'
        script.setAttribute('type', 'application/ld+json')
        document.head.appendChild(script)
      }
      script.textContent = serialized
    }
    return () => {
      document.getElementById('json-ld')?.remove()
    }
  }, [title, description, serialized])
}

/** Countdown used for OTP resend timers. */
export function useCountdown(seconds: number): { remaining: number; restart: () => void } {
  const [remaining, setRemaining] = useState(seconds)
  useEffect(() => {
    if (remaining <= 0) return undefined
    const timer = setTimeout(() => setRemaining((current) => current - 1), 1000)
    return () => clearTimeout(timer)
  }, [remaining])
  return { remaining, restart: () => setRemaining(seconds) }
}

export function useMediaQuery(query: string): boolean {
  const [matches, setMatches] = useState(() => (typeof window.matchMedia === 'function' ? window.matchMedia(query).matches : false))
  useEffect(() => {
    if (typeof window.matchMedia !== 'function') return undefined
    const media = window.matchMedia(query)
    const handler = () => setMatches(media.matches)
    handler()
    media.addEventListener('change', handler)
    return () => media.removeEventListener('change', handler)
  }, [query])
  return matches
}
