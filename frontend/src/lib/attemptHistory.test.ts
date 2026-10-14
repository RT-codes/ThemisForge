import assert from 'node:assert/strict'
import { test } from 'node:test'
import { createAttemptHistory, emptyAttemptHistory } from './attemptHistory.ts'
import type { AttemptDetail } from './api.ts'

const attempt = (id: number): AttemptDetail => ({
  id, task_id: 1, status: 'succeeded', started_at: '2026-10-14T10:00:00Z',
  finished_at: '2026-10-14T10:01:00Z', exit_code: 0, workflow_id: null,
  failure: null, log: `Log ${id}`, result: `Result ${id}`,
})
function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (error: Error) => void
  const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no })
  return { promise, resolve, reject }
}

test('list failure is distinct from empty history and retry loads attempts', async () => {
  let state = emptyAttemptHistory()
  let fail = true
  const history = createAttemptHistory(1, {
    attempts: async () => { if (fail) throw new Error('offline'); return [attempt(1)] },
    attempt: async (id) => attempt(id),
  }, (next) => { state = next })
  await history.load()
  assert.equal(state.error, true)
  assert.equal(state.loaded, false)
  assert.equal(state.loading, false)
  fail = false
  await history.load()
  assert.equal(state.error, false)
  assert.equal(state.loaded, true)
  assert.equal(state.detail?.id, 1)
})

test('successful empty history does not show an error or request detail', async () => {
  let state = emptyAttemptHistory()
  const history = createAttemptHistory(1, {
    attempts: async () => [],
    attempt: async () => { throw new Error('unexpected detail request') },
  }, (next) => { state = next })
  await history.load()
  assert.equal(state.loaded, true)
  assert.equal(state.error, false)
  assert.equal(state.detailError, false)
  assert.deepEqual(state.attempts, [])
})

test('selection clears previous detail and failed detail can be retried', async () => {
  let state = emptyAttemptHistory()
  const pending = deferred<AttemptDetail>()
  let fail = true
  const history = createAttemptHistory(1, {
    attempts: async () => [attempt(1), attempt(2)],
    attempt: async (id) => id === 2 && fail ? pending.promise : attempt(id),
  }, (next) => { state = next })
  await history.load()
  const selecting = history.select(2)
  assert.equal(state.selectedId, 2)
  assert.equal(state.detail, null)
  assert.equal(state.detailLoading, true)
  pending.reject(new Error('offline'))
  await selecting
  assert.equal(state.detailError, true)
  assert.equal(state.detailLoading, false)
  fail = false
  await history.select(2)
  assert.equal(state.detailError, false)
  assert.equal(state.detail?.id, 2)
})

test('obsolete successes and failures cannot replace the latest selection', async () => {
  for (const failure of [false, true]) {
    let state = emptyAttemptHistory()
    const older = deferred<AttemptDetail>()
    const newer = deferred<AttemptDetail>()
    const history = createAttemptHistory(1, {
      attempts: async () => [],
      attempt: (id) => id === 1 ? older.promise : newer.promise,
    }, (next) => { state = next })
    const first = history.select(1)
    const second = history.select(2)
    newer.resolve(attempt(2))
    await second
    if (failure) older.reject(new Error('offline'))
    else older.resolve(attempt(1))
    await first
    assert.equal(state.selectedId, 2)
    assert.equal(state.detail?.id, 2)
    assert.equal(state.detailError, false)
  }
})

test('polling cannot overwrite a selection and disposed viewers cannot update', async () => {
  let state = emptyAttemptHistory()
  const poll = deferred<AttemptDetail>()
  let polling = false
  const history = createAttemptHistory(1, {
    attempts: async () => [attempt(1), attempt(2)],
    attempt: async (id) => id === 1 && polling ? poll.promise : attempt(id),
  }, (next) => { state = next })
  await history.load()
  polling = true
  const refresh = history.load()
  await Promise.resolve()
  await history.select(2)
  poll.resolve(attempt(1))
  await refresh
  assert.equal(state.detail?.id, 2)
  const before = state
  history.dispose()
  await history.load()
  await history.select(1)
  assert.equal(state, before)
})

test('a failed refresh keeps known attempts available and retry clears the error', async () => {
  let state = emptyAttemptHistory()
  let fail = false
  const history = createAttemptHistory(1, {
    attempts: async () => { if (fail) throw new Error('offline'); return [attempt(1)] },
    attempt: async (id) => attempt(id),
  }, (next) => { state = next })
  await history.load()
  fail = true
  await history.load()
  assert.equal(state.error, true)
  assert.equal(state.attempts[0].id, 1)
  assert.equal(state.detail?.id, 1)
  fail = false
  await history.load()
  assert.equal(state.error, false)
})

test('unmounting or changing tasks ignores pending list and detail responses', async () => {
  for (const pendingList of [true, false]) {
    let state = emptyAttemptHistory()
    const list = deferred<AttemptDetail[]>()
    const detail = deferred<AttemptDetail>()
    const history = createAttemptHistory(1, {
      attempts: () => list.promise,
      attempt: () => detail.promise,
    }, (next) => { state = next })
    const request = pendingList ? history.load() : history.select(1)
    history.dispose()
    const before = state
    if (pendingList) list.resolve([attempt(1)])
    else detail.resolve(attempt(1))
    await request
    assert.equal(state, before)
  }
})
