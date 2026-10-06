import assert from 'node:assert/strict'
import { test } from 'node:test'
import { parse } from './routes.ts'

test('a project path opens the overview', () => assert.deepEqual(parse('/projects/3'), { name: 'project', id: 3, page: 'overview' }))
test('a trailing slash is fine', () => assert.deepEqual(parse('/projects/3/'), { name: 'project', id: 3, page: 'overview' }))
test('the tasks sub page', () => assert.deepEqual(parse('/projects/3/tasks'), { name: 'project', id: 3, page: 'tasks' }))
test('a workflow opens in the editor, optionally on one of its runs', () => {
  assert.deepEqual(parse('/projects/3/workflows/7'), { name: 'workflow', id: 3, workflowId: 7, run: null })
  assert.deepEqual(parse('/projects/3/workflows/7/runs/12/'), { name: 'workflow', id: 3, workflowId: 7, run: 12 })
  assert.deepEqual(parse('/projects/3/workflows'), { name: 'not-found' })
})
test('a new workflow has its own address, and no id yet', () => assert.deepEqual(parse('/projects/3/workflows/new'), { name: 'workflow', id: 3, workflowId: null, run: null }))
test('the old single workflow page is gone', () => assert.deepEqual(parse('/projects/3/workflow'), { name: 'not-found' }))
test('an unknown sub page is not found', () => assert.deepEqual(parse('/projects/3/foo'), { name: 'not-found' }))
test('other routes are untouched', () => {
  assert.deepEqual(parse('/'), { name: 'home' })
  assert.deepEqual(parse('/docs/tasks'), { name: 'docs', slug: 'tasks' })
})
