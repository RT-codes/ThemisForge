// A repeat schedule the way a person thinks of it ("every weekday at 09:00"). The server keeps it as a cron
// expression, so this file is the only place that knows how to turn one into the other. Nothing else in the app
// should show or ask for cron syntax.

export type Recurrence =
  | { every: 'minutes'; interval: number }
  | { every: 'hour'; minute: number }
  | { every: 'day'; time: string }
  | { every: 'weekdays'; time: string }
  | { every: 'week'; days: number[]; time: string }
  | { every: 'month'; day: number; time: string }

export type RepeatKind = Recurrence['every']

/** 0 is Sunday, like the server counts, but the week is shown starting on Monday */
export const WEEKDAYS = [
  { n: 1, short: 'Mon', long: 'Monday' },
  { n: 2, short: 'Tue', long: 'Tuesday' },
  { n: 3, short: 'Wed', long: 'Wednesday' },
  { n: 4, short: 'Thu', long: 'Thursday' },
  { n: 5, short: 'Fri', long: 'Friday' },
  { n: 6, short: 'Sat', long: 'Saturday' },
  { n: 0, short: 'Sun', long: 'Sunday' },
]

export const REPEAT_KINDS: { id: RepeatKind; label: string }[] = [
  { id: 'day', label: 'Every day' },
  { id: 'weekdays', label: 'Every weekday (Mon to Fri)' },
  { id: 'week', label: 'Every week on chosen days' },
  { id: 'month', label: 'Every month on a day' },
  { id: 'hour', label: 'Every hour' },
  { id: 'minutes', label: 'Every few minutes' },
]

export const MINUTE_INTERVALS = [5, 10, 15, 20, 30]

const pad = (n: number) => String(n).padStart(2, '0')
const split = (time: string): [number, number] => {
  const [h, m] = time.split(':').map(Number)
  return [Number.isFinite(h) ? h : 9, Number.isFinite(m) ? m : 0]
}
const ordinal = (n: number) => `${n}${n % 100 >= 11 && n % 100 <= 13 ? 'th' : ({ 1: 'st', 2: 'nd', 3: 'rd' } as Record<number, string>)[n % 10] ?? 'th'}`

export function defaultRecurrence(kind: RepeatKind): Recurrence {
  switch (kind) {
    case 'minutes':
      return { every: 'minutes', interval: 15 }
    case 'hour':
      return { every: 'hour', minute: 0 }
    case 'weekdays':
      return { every: 'weekdays', time: '09:00' }
    case 'week':
      return { every: 'week', days: [1], time: '09:00' }
    case 'month':
      return { every: 'month', day: 1, time: '09:00' }
    default:
      return { every: 'day', time: '09:00' }
  }
}

export function toCron(r: Recurrence): string {
  switch (r.every) {
    case 'minutes':
      return `*/${r.interval} * * * *`
    case 'hour':
      return `${r.minute} * * * *`
    case 'day': {
      const [h, m] = split(r.time)
      return `${m} ${h} * * *`
    }
    case 'weekdays': {
      const [h, m] = split(r.time)
      return `${m} ${h} * * 1-5`
    }
    case 'week': {
      const [h, m] = split(r.time)
      const days = [...new Set(r.days)].sort((a, b) => ((a + 6) % 7) - ((b + 6) % 7)) // Monday first
      return `${m} ${h} * * ${days.length ? days.join(',') : '1'}`
    }
    case 'month': {
      const [h, m] = split(r.time)
      return `${m} ${h} ${r.day} * *`
    }
  }
}

const int = (s: string) => (/^\d+$/.test(s) ? Number(s) : null)

/** the other way round; null for an expression this editor cannot express (an advanced schedule set up elsewhere) */
export function fromCron(cron: string | null): Recurrence | null {
  const f = (cron ?? '').trim().split(/\s+/)
  if (f.length !== 5) return null
  const [min, hour, dom, month, dow] = f
  if (month !== '*') return null
  const step = min.match(/^\*\/(\d+)$/)
  if (step && hour === '*' && dom === '*' && dow === '*') {
    const interval = Number(step[1])
    return interval >= 1 && interval <= 59 ? { every: 'minutes', interval } : null
  }
  const m = int(min)
  if (m === null || m > 59) return null
  if (hour === '*') return dom === '*' && dow === '*' ? { every: 'hour', minute: m } : null
  const h = int(hour)
  if (h === null || h > 23) return null
  const time = `${pad(h)}:${pad(m)}`
  if (dom === '*' && dow === '*') return { every: 'day', time }
  if (dom !== '*' && dow === '*') {
    const day = int(dom)
    return day !== null && day >= 1 && day <= 31 ? { every: 'month', day, time } : null
  }
  if (dom === '*') {
    const days = new Set<number>()
    for (const part of dow.split(',')) {
      const range = part.match(/^(\d)-(\d)$/)
      const [from, to] = range ? [Number(range[1]), Number(range[2])] : [int(part), int(part)]
      if (from === null || to === null || from > to || to > 7) return null
      for (let d = from; d <= to; d++) days.add(d % 7)
    }
    if (days.size === 7) return { every: 'day', time }
    if ([1, 2, 3, 4, 5].every((d) => days.has(d)) && days.size === 5) return { every: 'weekdays', time }
    return { every: 'week', days: [...days].sort((a, b) => ((a + 6) % 7) - ((b + 6) % 7)), time }
  }
  return null
}

export function describeRecurrence(r: Recurrence): string {
  switch (r.every) {
    case 'minutes':
      return r.interval === 1 ? 'Every minute' : `Every ${r.interval} minutes`
    case 'hour':
      return r.minute === 0 ? 'Every hour, on the hour' : `Every hour at :${pad(r.minute)}`
    case 'day':
      return `Every day at ${r.time}`
    case 'weekdays':
      return `Every weekday at ${r.time}`
    case 'week': {
      const names = r.days.map((d) => WEEKDAYS.find((w) => w.n === d)!)
      // one day in full ("Every Monday"), several as short names so the sentence stays short on a card
      const list =
        names.length === 1
          ? names[0].long
          : names.length === 2
            ? `${names[0].short} and ${names[1].short}`
            : `${names.slice(0, -1).map((w) => w.short).join(', ')} and ${names.at(-1)!.short}`
      return `Every ${list} at ${r.time}`
    }
    case 'month':
      return `Monthly on the ${ordinal(r.day)} at ${r.time}`
  }
}

/** what to show for a stored schedule: a sentence, never the expression */
export function describeSchedule(cron: string | null): string {
  const r = fromCron(cron)
  return r ? describeRecurrence(r) : cron ? 'Custom schedule' : ''
}
