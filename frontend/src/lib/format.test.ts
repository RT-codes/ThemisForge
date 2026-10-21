import assert from 'node:assert/strict'
import { test } from 'node:test'
import { accessLabel, attemptLabel, duration, fromLocalInput, relative, slug, toLocalInput } from './format.ts'

const NOW = Date.parse('2026-06-15T12:00:00Z')
const at = (seconds: number) => new Date(NOW + seconds * 1000).toISOString()
// the wording of "5 minutes ago" depends on the machine's language, so the expected text comes from the same formatter
const rtf = new Intl.RelativeTimeFormat(undefined, { numeric: 'auto' })

test('a time within about a minute of now reads as "a moment", whichever way it points', () => {
  assert.equal(relative(at(30), NOW), 'in a moment')
  assert.equal(relative(at(-30), NOW), 'just now')
  assert.equal(relative(at(0), NOW), 'in a moment')
})

test('a nearby time is counted in minutes, then hours, then days', () => {
  assert.equal(relative(at(-5 * 60), NOW), rtf.format(-5, 'minute'))
  assert.equal(relative(at(3 * 3600), NOW), rtf.format(3, 'hour'))
  assert.equal(relative(at(-2 * 86400), NOW), rtf.format(-2, 'day'))
})

test('the boundaries fall where the units change', () => {
  assert.equal(relative(at(44), NOW), 'in a moment')
  assert.equal(relative(at(45), NOW), rtf.format(1, 'minute'))
  assert.equal(relative(at(3599), NOW), rtf.format(60, 'minute'))
  assert.equal(relative(at(3600), NOW), rtf.format(1, 'hour'))
  assert.equal(relative(at(86400), NOW), rtf.format(1, 'day'))
})

test('no time at all reads as nothing', () => {
  assert.equal(relative(null, NOW), '')
})

test('a duration is written in the largest units that matter', () => {
  const start = '2026-06-15T12:00:00Z'
  const later = (s: number) => new Date(Date.parse(start) + s * 1000).toISOString()
  assert.equal(duration(start, later(7)), '7s')
  assert.equal(duration(start, later(60)), '1m 0s')
  assert.equal(duration(start, later(125)), '2m 5s')
  assert.equal(duration(start, later(3600)), '1h 0m')
  assert.equal(duration(start, later(3 * 3600 + 29 * 60 + 59)), '3h 29m')
})

test('a run that ends before it starts (clock skew) shows zero, never a negative time', () => {
  assert.equal(duration('2026-06-15T12:00:10Z', '2026-06-15T12:00:00Z'), '0s')
})

test('a datetime-local value goes to ISO and back to the same moment', () => {
  const iso = '2026-03-08T14:35:00.000Z'
  const local = toLocalInput(iso)
  assert.match(local, /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/)
  assert.equal(fromLocalInput(local), iso) // minutes survive; seconds were never in the input
})

test('an empty datetime-local value means "no time"', () => {
  assert.equal(toLocalInput(null), '')
  assert.equal(fromLocalInput(''), null)
})

test('a property name becomes a key of lowercase letters, digits and underscores', () => {
  assert.equal(slug('Due Date'), 'due_date')
  assert.equal(slug('  --Story points!!  '), 'story_points')
  assert.equal(slug('Ünïcode & more'), 'n_code_more')
})

test('a name with nothing usable in it, or one that is too long, still gives a key', () => {
  assert.equal(slug('???'), 'property')
  assert.equal(slug(''), 'property')
  assert.equal(slug('a'.repeat(60)).length, 40)
})

test('labels cover every attempt status and both folder modes', () => {
  assert.deepEqual(Object.keys(attemptLabel).sort(), ['cancelled', 'failed', 'running', 'succeeded'])
  assert.equal(accessLabel('ro'), 'Read only')
  assert.equal(accessLabel('rw'), 'Read and write')
})
