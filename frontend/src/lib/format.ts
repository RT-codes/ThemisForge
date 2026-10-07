import type { AttemptStatus, TaskStatus } from './api'

export const STATUSES: { id: TaskStatus; label: string; hint: string }[] = [
  { id: 'inbox', label: 'Inbox', hint: 'Not scheduled yet. Recurring tasks parked here are paused.' },
  { id: 'ready', label: 'Ready', hint: 'Picked up by the scheduler when due.' },
  { id: 'running', label: 'Running', hint: 'A cell is working on it.' },
  { id: 'review', label: 'Review', hint: 'Finished, waiting for a human.' },
  { id: 'done', label: 'Done', hint: 'Finished.' },
  { id: 'blocked', label: 'Blocked', hint: 'Waiting on something or cancelled.' },
  { id: 'failed', label: 'Failed', hint: 'The last attempt failed.' },
]

export const statusLabel = (s: TaskStatus) => STATUSES.find((x) => x.id === s)?.label ?? s

export const attemptLabel: Record<AttemptStatus, string> = {
  running: 'Running',
  succeeded: 'Succeeded',
  failed: 'Failed',
  cancelled: 'Cancelled',
}

const rtf = new Intl.RelativeTimeFormat(undefined, { numeric: 'auto' })

/** "in 3 hours", "5 minutes ago" */
export function relative(iso: string | null, now = Date.now()): string {
  if (!iso) return ''
  const diff = (new Date(iso).getTime() - now) / 1000
  const abs = Math.abs(diff)
  if (abs < 45) return diff >= 0 ? 'in a moment' : 'just now'
  if (abs < 3600) return rtf.format(Math.round(diff / 60), 'minute')
  if (abs < 86400) return rtf.format(Math.round(diff / 3600), 'hour')
  return rtf.format(Math.round(diff / 86400), 'day')
}

export const dateTime = (iso: string | null) =>
  iso ? new Date(iso).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' }) : ''

export const timeOnly = (iso: string) => new Date(iso).toLocaleTimeString(undefined, { timeStyle: 'short' })

export function duration(start: string, end: string | null): string {
  const s = Math.max(0, Math.round(((end ? new Date(end).getTime() : Date.now()) - new Date(start).getTime()) / 1000))
  if (s < 60) return `${s}s`
  if (s < 3600) return `${Math.floor(s / 60)}m ${s % 60}s`
  return `${Math.floor(s / 3600)}h ${Math.floor((s % 3600) / 60)}m`
}

/** <input type="datetime-local"> works in local time without a zone. */
export const toLocalInput = (iso: string | null) => {
  if (!iso) return ''
  const d = new Date(iso)
  const p = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}`
}
export const fromLocalInput = (v: string) => (v ? new Date(v).toISOString() : null)

export const slug = (name: string) =>
  name
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '_')
    .replace(/^_+|_+$/g, '')
    .slice(0, 40) || 'property'

/** how a shared folder's access reads: what cells may do there */
export const accessLabel = (mode: 'ro' | 'rw') => (mode === 'ro' ? 'Read only' : 'Read and write')
