import assert from 'node:assert/strict'
import { test } from 'node:test'
import { parse } from './routes.ts'

test('a project path opens the overview', () => assert.deepEqual(parse('/projects/3'), { name: 'project', id: 3, page: 'overview' }))
test('a trailing slash is fine', () => assert.deepEqual(parse('/projects/3/'), { name: 'project', id: 3, page: 'overview' }))
test('the tasks sub page', () => assert.deepEqual(parse('/projects/3/tasks'), { name: 'project', id: 3, page: 'tasks' }))
test('an unknown sub page is not found', () => assert.deepEqual(parse('/projects/3/foo'), { name: 'not-found' }))
test('other routes are untouched', () => {
  assert.deepEqual(parse('/'), { name: 'home' })
  assert.deepEqual(parse('/account'), { name: 'account' })
  assert.deepEqual(parse('/docs/tasks'), { name: 'docs', slug: 'tasks' })
})
