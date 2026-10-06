import assert from 'node:assert/strict'
import { test } from 'node:test'
import { describeSchedule, fromCron, toCron, type Recurrence } from './recurrence.ts'

const cases: [Recurrence, string, string][] = [
  [{ every: 'minutes', interval: 15 }, '*/15 * * * *', 'Every 15 minutes'],
  [{ every: 'hour', minute: 0 }, '0 * * * *', 'Every hour, on the hour'],
  [{ every: 'hour', minute: 30 }, '30 * * * *', 'Every hour at :30'],
  [{ every: 'day', time: '09:00' }, '0 9 * * *', 'Every day at 09:00'],
  [{ every: 'weekdays', time: '18:30' }, '30 18 * * 1-5', 'Every weekday at 18:30'],
  [{ every: 'week', days: [1], time: '09:00' }, '0 9 * * 1', 'Every Monday at 09:00'],
  [{ every: 'week', days: [1, 4], time: '07:05' }, '5 7 * * 1,4', 'Every Mon and Thu at 07:05'],
  [{ every: 'week', days: [1, 3, 5, 0], time: '09:00' }, '0 9 * * 1,3,5,0', 'Every Mon, Wed, Fri and Sun at 09:00'],
  [{ every: 'month', day: 1, time: '09:00' }, '0 9 1 * *', 'Monthly on the 1st at 09:00'],
  [{ every: 'month', day: 22, time: '18:30' }, '30 18 22 * *', 'Monthly on the 22nd at 18:30'],
]

for (const [rule, cron, text] of cases) {
  test(`${text}: both ways, and in words`, () => {
    assert.equal(toCron(rule), cron)
    assert.deepEqual(fromCron(cron), rule)
    assert.equal(describeSchedule(cron), text)
  })
}

test('the same schedule written differently is still understood', () => {
  assert.deepEqual(fromCron('0 9 * * 1,2,3,4,5'), { every: 'weekdays', time: '09:00' })
  assert.deepEqual(fromCron('0 9 * * 0,1,2,3,4,5,6'), { every: 'day', time: '09:00' })
  assert.deepEqual(fromCron('0 9 * * 7'), { every: 'week', days: [0], time: '09:00' })
  assert.deepEqual(fromCron('  0   9 * * 1-3 '), { every: 'week', days: [1, 2, 3], time: '09:00' })
})

test('days are always written Monday first, and never empty', () => {
  assert.equal(toCron({ every: 'week', days: [0, 3, 1], time: '08:00' }), '0 8 * * 1,3,0')
  assert.equal(toCron({ every: 'week', days: [], time: '08:00' }), '0 8 * * 1')
})

test('an expression the editor cannot express is a custom schedule, never shown raw', () => {
  for (const odd of ['0 9 1 6 *', '0 */2 * * *', '0 9 * * 1#2', '0 0 9 * * *', 'nonsense', '61 9 * * *']) {
    assert.equal(fromCron(odd), null, odd)
    assert.equal(describeSchedule(odd), 'Custom schedule', odd)
  }
  assert.equal(describeSchedule(null), '')
})
