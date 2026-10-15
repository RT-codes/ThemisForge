import assert from 'node:assert/strict'
import { test } from 'node:test'
import type { Attempt, AttemptDetail } from '../../api.ts'
import { createAttemptHistory } from './attemptHistory.ts'

const attempt = (id: number): Attempt => ({
	id, task_id: 1, status: 'succeeded', started_at: '2026-01-01T00:00:00Z',
	finished_at: '2026-01-01T00:01:00Z', exit_code: 0,
})
const detail = (id: number): AttemptDetail => ({
	...attempt(id), workflow_id: null, failure: null, log: `Log ${id}`, result: `Result ${id}`,
})
function deferred<T>() {
	let resolve!: (value: T) => void
	let reject!: (reason: Error) => void
	const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no })
	return { promise, resolve, reject }
}

test('an initial list failure is distinct from a successful empty history and can be retried', async () => {
	let fail = true
	const history = createAttemptHistory(() => 1, {
		attempts: async () => { if (fail) throw new Error('offline'); return [] },
		attempt: async (id) => detail(id),
	}, () => {})
	await history.load()
	assert.equal(history.state.loaded, true)
	assert.equal(history.state.listError, true)
	assert.deepEqual(history.state.attempts, [])
	fail = false
	await history.load()
	assert.equal(history.state.listError, false)
	assert.deepEqual(history.state.attempts, [])
	assert.equal(history.state.selectedId, null)
})

test('a failed detail request leaves no result for a new selection and Retry loads it', async () => {
	let fail = true
	const history = createAttemptHistory(() => 1, {
		attempts: async () => [attempt(2), attempt(1)],
		attempt: async (id) => { if (id === 1 && fail) throw new Error('offline'); return detail(id) },
	}, () => {})
	await history.load()
	assert.equal(history.state.detail?.id, 2)
	await history.select(1)
	assert.equal(history.state.selectedId, 1)
	assert.equal(history.state.detail, null)
	assert.equal(history.state.detailError, true)
	fail = false
	await history.select(1)
	assert.equal(history.state.detailError, false)
	assert.equal(history.state.detail?.id, 1)
})

test('a late detail response cannot replace the selected attempt', async () => {
	const first = deferred<AttemptDetail>()
	const second = deferred<AttemptDetail>()
	const history = createAttemptHistory(() => 1, {
		attempts: async () => [attempt(2), attempt(1)],
		attempt: (id) => id === 2 ? first.promise : second.promise,
	}, () => {})
	const loading = history.load()
	await Promise.resolve()
	const selecting = history.select(1)
	second.resolve(detail(1))
	await selecting
	first.resolve(detail(2))
	await loading
	assert.equal(history.state.selectedId, 1)
	assert.equal(history.state.detail?.id, 1)
})

test('refresh failures keep loaded content with an error until a successful retry', async () => {
	let failList = false
	let failDetail = false
	const history = createAttemptHistory(() => 1, {
		attempts: async () => { if (failList) throw new Error('offline'); return [attempt(1)] },
		attempt: async () => { if (failDetail) throw new Error('offline'); return detail(1) },
	}, () => {})
	await history.load()
	failList = true
	await history.load()
	assert.equal(history.state.listError, true)
	assert.equal(history.state.detail?.id, 1)
	failList = false
	failDetail = true
	await history.load()
	assert.equal(history.state.listError, false)
	assert.equal(history.state.detailError, true)
	assert.equal(history.state.detail?.id, 1)
	failDetail = false
	await history.select(1)
	assert.equal(history.state.detailError, false)
})
