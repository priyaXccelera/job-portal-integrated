import type { ReactNode } from 'react'

export function AuthCard({
  title,
  subtitle,
  children,
  wide = false,
}: {
  title: string
  subtitle?: string
  children: ReactNode
  wide?: boolean
}) {
  return (
    <div className={`mx-auto px-4 py-10 ${wide ? 'max-w-2xl' : 'max-w-md'}`}>
      <div className="card p-6 sm:p-8">
        <h1 className="text-2xl font-bold">{title}</h1>
        {subtitle && <p className="mt-1 text-sm text-muted">{subtitle}</p>}
        <div className="mt-6">{children}</div>
      </div>
    </div>
  )
}

export function FormAlert({ message, tone = 'error' }: { message: string; tone?: 'error' | 'success' }) {
  if (!message) return null
  return (
    <p
      role={tone === 'error' ? 'alert' : 'status'}
      className={`mb-4 rounded-lg px-3 py-2 text-sm ${tone === 'error' ? 'bg-danger/10 text-danger' : 'bg-success/10 text-success'}`}
    >
      {message}
    </p>
  )
}
