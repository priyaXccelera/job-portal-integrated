const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

/** "12 Mar 2026" */
export function formatDate(value: string): string {
  if (!value) return ''
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return `${date.getDate()} ${MONTHS[date.getMonth()]} ${date.getFullYear()}`
}

/** YYYY-MM-DD, the format sent to the API */
export function toApiDate(value: Date | string): string {
  const date = typeof value === 'string' ? new Date(value) : value
  return date.toISOString().slice(0, 10)
}

export function timeAgo(value: string): string {
  const diffMs = Date.now() - new Date(value).getTime()
  const minutes = Math.floor(diffMs / 60000)
  if (minutes < 1) return 'Just now'
  if (minutes < 60) return `${minutes} min ago`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours} hour${hours > 1 ? 's' : ''} ago`
  const days = Math.floor(hours / 24)
  if (days < 30) return `${days} day${days > 1 ? 's' : ''} ago`
  const months = Math.floor(days / 30)
  return `${months} month${months > 1 ? 's' : ''} ago`
}

/** Indian style: "6-10 Lacs PA" (inputs are in lakhs per annum) */
export function formatSalary(min: number, max: number, disclosed: boolean): string {
  if (!disclosed) return 'Not disclosed'
  return `${min}-${max} Lacs PA`
}

export function formatCtc(lakhs: number): string {
  return `${lakhs} Lacs PA`
}

export function formatExperience(min: number, max: number): string {
  return `${min}-${max} Yrs`
}

export function formatIndianNumber(value: number): string {
  return new Intl.NumberFormat('en-IN').format(value)
}

export function slugify(text: string): string {
  return text
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
}

export function slugWithId(text: string, id: string): string {
  return `${slugify(text)}-${id}`
}

/** Extracts the id from "senior-dev-j12" style slugs */
export function idFromSlug(slugId: string | undefined): string {
  if (!slugId) return ''
  const parts = slugId.split('-')
  return parts[parts.length - 1]
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

export function downloadCsv(filename: string, rows: (string | number)[][]): void {
  const csv = rows
    .map((row) => row.map((cell) => `"${String(cell).replace(/"/g, '""')}"`).join(','))
    .join('\n')
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' })
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  anchor.click()
  URL.revokeObjectURL(url)
}

export function parseCsv(text: string): string[][] {
  return text
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => line.split(',').map((cell) => cell.trim().replace(/^"|"$/g, '')))
}
