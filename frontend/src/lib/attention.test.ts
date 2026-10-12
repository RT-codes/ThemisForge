import assert from 'node:assert/strict'
import { test } from 'node:test'
import type { Task } from './api.ts'
import { attentionTasks } from './attention.ts'

const task = (id: number, overrides: Partial<Task> = {}): Task => ({
  id, project_id: 1, board_id: 1, origin_task_id: null, title: `Task ${id}`, description: '',
  status: 'backlog', position: id, properties: {}, schedule_kind: 'none', cron: null, run_at: null,
  next_run_at: null, last_run_at: null, review_on_success: false, harness: '', agent_id: null,
  stages: [], hops: 0, cooldown_seconds: null, max_hops: null, created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z', last_attempt_status: null, workflow_run: null, ...overrides,
})

test('review and failed tasks across boards each have one reason', () => {
  const review = task(1, { status: 'review', last_attempt_status: 'failed' })
  const failed = task(2, { status: 'failed', board_id: 2 })
  assert.deepEqual(attentionTasks([failed, review]), {
    items: [{ task: review, reason: 'Waiting for review' }, { task: failed, reason: 'Last run failed' }],
    total: 2,
  })
})

test('a failed recurring run remains visible after its task returns to Ready', () => {
  const recurring = task(1, { status: 'ready', schedule_kind: 'cron', last_attempt_status: 'failed' })
  assert.deepEqual(attentionTasks([recurring]).items, [{ task: recurring, reason: 'Last run failed' }])
  for (const last_attempt_status of ['succeeded', 'cancelled', 'running', null] as const) {
    assert.equal(attentionTasks([{ ...recurring, last_attempt_status }]).total, 0)
  }
})

test('old failures on paused, running or resolved tasks do not need attention', () => {
  const tasks = ['backlog', 'running', 'done', 'blocked', 'custom:3'].map((status, index) =>
    task(index, { status: status as Task['status'], schedule_kind: 'cron', last_attempt_status: 'failed' })
  )
  tasks.push(task(10, { status: 'ready', schedule_kind: 'none', last_attempt_status: 'failed' }))
  tasks.push(task(11, { status: 'ready', schedule_kind: 'once', last_attempt_status: 'failed' }))
  assert.deepEqual(attentionTasks(tasks), { items: [], total: 0 })
})

test('tasks leave the list when review finishes or a recurring run starts', () => {
  const review = task(1, { status: 'review', last_attempt_status: 'succeeded' })
  const recurring = task(2, { status: 'ready', schedule_kind: 'cron', last_attempt_status: 'failed' })
  assert.equal(attentionTasks([review, recurring]).total, 2)
  assert.equal(attentionTasks([
    { ...review, status: 'done' }, { ...recurring, status: 'running', last_attempt_status: 'running' },
  ]).total, 0)
})

test('review comes first, then recent changes, with ids breaking ties independent of input order', () => {
  const tasks = [
    task(4, { status: 'failed', updated_at: '2026-01-03T00:00:00Z' }),
    task(3, { status: 'review' }), task(2, { status: 'review' }),
    task(1, { status: 'review', updated_at: '2026-01-02T00:00:00Z' }),
    task(5, { status: 'failed' }),
  ]
  const ids = (input: Task[]) => attentionTasks(input).items.map(({ task }) => task.id)
  assert.deepEqual(ids(tasks), [1, 2, 3, 4, 5])
  assert.deepEqual(ids([...tasks].reverse()), [1, 2, 3, 4, 5])
  assert.deepEqual(tasks.map((task) => task.id), [4, 3, 2, 1, 5])
})

test('duplicate ids use the current task and count only once', () => {
  const old = task(1, { status: 'failed' })
  const moved = { ...old, board_id: 2 }
  assert.deepEqual(attentionTasks([old, moved]), {
    items: [{ task: moved, reason: 'Last run failed' }], total: 1,
  })
  assert.equal(attentionTasks([old, { ...moved, status: 'done' }]).total, 0)
})

test('the compact list keeps the total and can expand to every task', () => {
  const tasks = Array.from({ length: 7 }, (_, index) => task(index + 1, { status: 'review' }))
  assert.equal(attentionTasks(tasks).items.length, 5)
  assert.equal(attentionTasks(tasks).total, 7)
  assert.equal(attentionTasks(tasks, tasks.length).items.length, 7)
  assert.deepEqual(attentionTasks(tasks, 0), { items: [], total: 7 })
  assert.deepEqual(attentionTasks([]), { items: [], total: 0 })
})
