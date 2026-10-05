import assert from 'node:assert/strict'
import { test } from 'node:test'
import { countScheduled } from './schedule.ts'

const now = new Date(2026, 9, 6, 10, 0).getTime()
const at = (ms: number) => ({ at: new Date(ms).toISOString() })
const H = 3600_000

test('nothing scheduled', () => assert.deepEqual(countScheduled([], now), { today: 0, week: 0 }))
test('today stops at local midnight', () => {
  const runs = [at(now + H), at(now + 13 * H), at(now + 15 * H)]
  assert.deepEqual(countScheduled(runs, now), { today: 2, week: 3 })
})
test('runs past 7 days and in the past are ignored', () => {
  const runs = [at(now - H), at(now + 24 * 7 * H), at(now + 24 * 7 * H - 1)]
  assert.deepEqual(countScheduled(runs, now), { today: 0, week: 1 })
})
