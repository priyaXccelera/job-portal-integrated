import { useEffect, useId, useRef, useState } from 'react'
import type { InputHTMLAttributes, ReactNode, SelectHTMLAttributes, TextareaHTMLAttributes } from 'react'
import { X } from 'lucide-react'
import { OTP_LENGTH } from '../constants'
import { useDebouncedValue } from '../hooks'
import { getSuggestions } from '../data/store'
import { passwordScore } from '../validation'

interface FieldShell {
  label: string
  error?: string
  help?: string
  required?: boolean
}

function FieldWrapper({
  id,
  label,
  error,
  help,
  required,
  children,
}: FieldShell & { id: string; children: ReactNode }) {
  return (
    <div className="space-y-1">
      <label htmlFor={id} className="block text-sm font-medium">
        {label}
        {required && <span className="text-danger"> *</span>}
      </label>
      {children}
      {error ? (
        <p id={`${id}-msg`} className="text-xs text-danger" role="alert">
          {error}
        </p>
      ) : (
        help && (
          <p id={`${id}-msg`} className="text-xs text-muted">
            {help}
          </p>
        )
      )}
    </div>
  )
}

export function TextField({ label, error, help, required, ...rest }: FieldShell & InputHTMLAttributes<HTMLInputElement>) {
  const id = useId()
  return (
    <FieldWrapper id={id} label={label} error={error} help={help} required={required}>
      <input
        id={id}
        className={`input ${error ? 'border-danger' : ''}`}
        aria-invalid={Boolean(error)}
        aria-describedby={`${id}-msg`}
        {...rest}
      />
    </FieldWrapper>
  )
}

export function SelectField({
  label,
  error,
  help,
  required,
  options,
  placeholder,
  ...rest
}: FieldShell & SelectHTMLAttributes<HTMLSelectElement> & { options: (string | { value: string; label: string })[]; placeholder?: string }) {
  const id = useId()
  return (
    <FieldWrapper id={id} label={label} error={error} help={help} required={required}>
      <select id={id} className={`input ${error ? 'border-danger' : ''}`} aria-invalid={Boolean(error)} {...rest}>
        {placeholder !== undefined && <option value="">{placeholder}</option>}
        {options.map((option) => {
          const value = typeof option === 'string' ? option : option.value
          const text = typeof option === 'string' ? option : option.label
          return (
            <option key={value} value={value}>
              {text}
            </option>
          )
        })}
      </select>
    </FieldWrapper>
  )
}

export function TextAreaField({ label, error, help, required, ...rest }: FieldShell & TextareaHTMLAttributes<HTMLTextAreaElement>) {
  const id = useId()
  return (
    <FieldWrapper id={id} label={label} error={error} help={help} required={required}>
      <textarea id={id} rows={4} className={`input ${error ? 'border-danger' : ''}`} aria-invalid={Boolean(error)} {...rest} />
    </FieldWrapper>
  )
}

export function PasswordStrength({ value }: { value: string }) {
  const score = passwordScore(value)
  const labels = ['Too weak', 'Weak', 'Fair', 'Good', 'Strong']
  const colors = ['bg-line', 'bg-danger', 'bg-warning', 'bg-primary', 'bg-success']
  return (
    <div aria-live="polite">
      <div className="flex gap-1">
        {[1, 2, 3, 4].map((segment) => (
          <div key={segment} className={`h-1.5 flex-1 rounded-full ${segment <= score ? colors[score] : 'bg-line'}`} />
        ))}
      </div>
      <p className="mt-1 text-xs text-muted">Password strength: {value ? labels[score] : 'enter a password'}</p>
    </div>
  )
}

/** Text input with debounced typeahead suggestions from GET /suggestions. */
export function SuggestInput({
  value,
  onChange,
  onSelect,
  type,
  placeholder,
  label,
  className = '',
}: {
  value: string
  onChange: (value: string) => void
  onSelect?: (value: string) => void
  type: 'job' | 'skill' | 'company' | 'location'
  placeholder: string
  label: string
  className?: string
}) {
  const [options, setOptions] = useState<string[]>([])
  const [open, setOpen] = useState(false)
  const debounced = useDebouncedValue(value, 250)
  const cache = useRef<Record<string, string[]>>({})
  const wrapper = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!debounced.trim()) {
      setOptions([])
      return
    }
    const key = `${type}:${debounced}`
    if (cache.current[key]) {
      setOptions(cache.current[key])
      return
    }
    getSuggestions(type, debounced)
      .then((result) => {
        cache.current[key] = result
        setOptions(result)
      })
      .catch(() => setOptions([]))
  }, [debounced, type])

  useEffect(() => {
    const handler = (event: MouseEvent) => {
      if (wrapper.current && !wrapper.current.contains(event.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  return (
    <div ref={wrapper} className={`relative ${className}`}>
      <input
        aria-label={label}
        className="w-full bg-transparent px-3 py-2 text-sm text-ink placeholder:text-muted focus:outline-none"
        placeholder={placeholder}
        value={value}
        autoComplete="off"
        onChange={(event) => {
          onChange(event.target.value)
          setOpen(true)
        }}
        onFocus={() => setOpen(true)}
      />
      {open && options.length > 0 && (
        <ul role="listbox" className="card absolute left-0 right-0 top-full z-30 mt-1 max-h-60 overflow-y-auto py-1">
          {options.map((option) => (
            <li key={option}>
              <button
                type="button"
                role="option"
                aria-selected={option === value}
                className="w-full px-3 py-2 text-left text-sm text-ink hover:bg-soft"
                onClick={() => {
                  onChange(option)
                  onSelect?.(option)
                  setOpen(false)
                }}
              >
                {option}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

/** Chip list with typeahead add (skills, locations). */
export function ChipInput({
  label,
  values,
  onChange,
  type,
  placeholder,
  error,
}: {
  label: string
  values: string[]
  onChange: (values: string[]) => void
  type: 'skill' | 'location'
  placeholder: string
  error?: string
}) {
  const [text, setText] = useState('')
  const add = (item: string) => {
    const trimmed = item.trim()
    if (trimmed && !values.includes(trimmed)) onChange([...values, trimmed])
    setText('')
  }
  return (
    <div className="space-y-1">
      <span className="block text-sm font-medium">{label}</span>
      <div className={`rounded-lg border bg-surface ${error ? 'border-danger' : 'border-line'}`}>
        <div className="flex flex-wrap gap-2 px-3 pt-2">
          {values.map((item) => (
            <span key={item} className="chip">
              {item}
              <button type="button" aria-label={`Remove ${item}`} onClick={() => onChange(values.filter((entry) => entry !== item))}>
                <X className="h-3 w-3" />
              </button>
            </span>
          ))}
        </div>
        <div
          onKeyDown={(event) => {
            if (event.key === 'Enter') {
              event.preventDefault()
              add(text)
            }
          }}
        >
          <SuggestInput value={text} onChange={setText} onSelect={add} type={type} placeholder={placeholder} label={`Add ${label}`} />
        </div>
      </div>
      {error && <p className="text-xs text-danger" role="alert">{error}</p>}
    </div>
  )
}

export function OtpInput({ value, onChange }: { value: string; onChange: (value: string) => void }) {
  const refs = useRef<(HTMLInputElement | null)[]>([])
  const digits = Array.from({ length: OTP_LENGTH }, (_, index) => value[index] ?? '')
  const update = (index: number, digit: string) => {
    const next = digits.slice()
    next[index] = digit
    onChange(next.join(''))
    if (digit && index < OTP_LENGTH - 1) refs.current[index + 1]?.focus()
  }
  return (
    <div className="flex justify-center gap-2" role="group" aria-label="One time password">
      {digits.map((digit, index) => (
        <input
          key={index}
          ref={(element) => {
            refs.current[index] = element
          }}
          inputMode="numeric"
          maxLength={1}
          aria-label={`Digit ${index + 1}`}
          value={digit}
          className="input h-12 w-11 text-center text-lg font-semibold"
          onChange={(event) => update(index, event.target.value.replace(/\D/g, ''))}
          onKeyDown={(event) => {
            if (event.key === 'Backspace' && !digit && index > 0) refs.current[index - 1]?.focus()
          }}
          onPaste={(event) => {
            const pasted = event.clipboardData.getData('text').replace(/\D/g, '').slice(0, OTP_LENGTH)
            if (pasted) {
              event.preventDefault()
              onChange(pasted)
            }
          }}
        />
      ))}
    </div>
  )
}

export function CheckboxField({
  label,
  checked,
  onChange,
  error,
}: {
  label: ReactNode
  checked: boolean
  onChange: (value: boolean) => void
  error?: string
}) {
  const id = useId()
  return (
    <div>
      <div className="flex items-start gap-2">
        <input id={id} type="checkbox" className="mt-1 h-4 w-4 accent-primary" checked={checked} onChange={(event) => onChange(event.target.checked)} />
        <label htmlFor={id} className="text-sm">
          {label}
        </label>
      </div>
      {error && <p className="mt-1 text-xs text-danger" role="alert">{error}</p>}
    </div>
  )
}
