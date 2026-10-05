import type { ScheduledRun } from './api.ts'

const DAY = 24 * 3600_000

/** Runs due before the end of today (local time) and within the next 7 days. */
export function countScheduled(runs: Pick<ScheduledRun, 'at'>[], now: number) {
  const midnight = new Date(now)
  midnight.setHours(24, 0, 0, 0)
  let today = 0
  let week = 0
  for (const r of runs) {
    const t = new Date(r.at).getTime()
    if (t < now || t >= now + 7 * DAY) continue
    week++
    if (t < midnight.getTime()) today++
  }
  return { today, week }
}
