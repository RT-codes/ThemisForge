import assert from 'node:assert/strict'
import { test } from 'node:test'
import type { ProjectEvent } from './api.ts'
import { describeEvent, historyQuery } from './history.ts'

const event = (kind: string, title: string, data: Record<string, unknown> = {}): ProjectEvent => ({ id: 1, kind, title, actor: 'Ada', workspace_id: null, board_id: null, task_id: null, data, created_at: '' })

test('a page of history is asked for by scope, kinds and where to continue', () => {
  assert.equal(historyQuery({}, [], null, 50), 'limit=50')
  assert.equal(historyQuery({ boardId: 3 }, ['task_created', 'task_moved'], 20, 10), 'limit=10&board_id=3&before=20&kind=task_created&kind=task_moved')
  assert.equal(historyQuery({ workspaceId: 1, taskId: 7 }, [], null, 5), 'limit=5&workspace_id=1&task_id=7')
})

test('task events say where the task went', () => {
  assert.equal(describeEvent(event('task_moved', 'Ship', { from: { board: 'Dev' }, to: { board: 'QA' } })), 'Sent the task "Ship" from Dev to QA')
  assert.equal(describeEvent(event('task_status', 'Ship', { from: { status: 'ready' }, to: { status: 'review' } })), 'Moved the task "Ship" from Ready to Review')
  assert.equal(describeEvent(event('task_spawned', 'Build', { origin: { title: 'Research' }, to: { board: 'Dev' } })), 'Created the task "Build" on Dev as a follow-up of "Research"')
  assert.equal(describeEvent(event('task_deleted', 'Old', { status: 'review' })), 'Deleted the task "Old" (was in Review)')
})

test('structure events name what changed and what happened to the tasks', () => {
  assert.equal(describeEvent(event('board_deleted', 'QA', { moved: 2, to: 'Dev' })), 'Deleted the board "QA", moving 2 tasks to Dev')
  assert.equal(describeEvent(event('board_deleted', 'QA', { moved: 0 })), 'Deleted the board "QA"')
  assert.equal(describeEvent(event('board_created', 'Dev copy', { copy_of: 'Dev' })), 'Duplicated the board "Dev" as "Dev copy"')
  assert.equal(describeEvent(event('status_renamed', 'Sorting', { was: 'Triage', board: 'QA' })), 'Renamed the status "Triage" to "Sorting" on QA')
  assert.equal(describeEvent(event('status_removed', 'Sorting', { board: 'QA', moved: 1, to: 'backlog' })), 'Deleted the status "Sorting" from QA, moving 1 task to Backlog')
})

test('a kind this version does not know still shows its title', () => assert.equal(describeEvent(event('from_the_future', 'Something')), 'Something'))
