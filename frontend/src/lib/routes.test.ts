import assert from 'node:assert/strict'
import { test } from 'node:test'
import { parse, parseBoardTarget, parseTaskTarget, taskHref, taskResultHref, workspaceBoardHref } from './routes.ts'

test('a project path opens the overview', () => assert.deepEqual(parse('/projects/3'), { name: 'project', id: 3, page: 'overview' }))
test('a trailing slash is fine', () => assert.deepEqual(parse('/projects/3/'), { name: 'project', id: 3, page: 'overview' }))
test('the tasks sub page', () => assert.deepEqual(parse('/projects/3/tasks'), { name: 'project', id: 3, page: 'tasks' }))
test('the project settings sub page', () => assert.deepEqual(parse('/projects/3/settings'), { name: 'project', id: 3, page: 'settings' }))
test('the global settings page is not the project one', () => assert.deepEqual(parse('/settings'), { name: 'settings' }))
test('the files sub page', () => assert.deepEqual(parse('/projects/3/files/'), { name: 'project', id: 3, page: 'files' }))
test('a workspace and a board have their own addresses', () => {
  assert.deepEqual(parse('/projects/3/workspaces/5'), { name: 'project', id: 3, page: 'workspace', workspaceId: 5 })
  assert.deepEqual(parse('/projects/3/boards/8/'), { name: 'project', id: 3, page: 'board', boardId: 8 })
  assert.deepEqual(parse('/projects/3/boards'), { name: 'not-found' })
  assert.deepEqual(parse('/projects/3/boards/x'), { name: 'not-found' })
})
test('a workflow opens in the editor, optionally on one of its runs', () => {
  assert.deepEqual(parse('/projects/3/workflows/7'), { name: 'workflow', id: 3, workflowId: 7, run: null, resume: false })
  assert.deepEqual(parse('/projects/3/workflows/7/runs/12/'), { name: 'workflow', id: 3, workflowId: 7, run: 12, resume: false })
})
test('a new workflow has its own address, and no id yet', () => assert.deepEqual(parse('/projects/3/workflows/new'), { name: 'workflow', id: 3, workflowId: null, run: null, resume: false }))
test('the old single workflow page is gone', () => assert.deepEqual(parse('/projects/3/workflow'), { name: 'not-found' }))
test('an unknown sub page is not found', () => assert.deepEqual(parse('/projects/3/foo'), { name: 'not-found' }))
test('other routes are untouched', () => {
  assert.deepEqual(parse('/'), { name: 'home' })
  assert.deepEqual(parse('/docs/tasks'), { name: 'docs', slug: 'tasks' })
})
test('the bare workflows address means: open the latest one', () => {
  assert.deepEqual(parse('/projects/3/workflows'), { name: 'workflow', id: 3, workflowId: null, run: null, resume: true })
  assert.deepEqual(parse('/projects/3/workflows/'), { name: 'workflow', id: 3, workflowId: null, run: null, resume: true })
})
test('the agents list, one agent, editing it, and a new one', () => {
  assert.deepEqual(parse('/projects/3/agents'), { name: 'agents', id: 3, agentId: null, isNew: false, editing: false })
  assert.deepEqual(parse('/projects/3/agents/'), { name: 'agents', id: 3, agentId: null, isNew: false, editing: false })
  assert.deepEqual(parse('/projects/3/agents/9'), { name: 'agents', id: 3, agentId: 9, isNew: false, editing: false })
  assert.deepEqual(parse('/projects/3/agents/9/edit'), { name: 'agents', id: 3, agentId: 9, isNew: false, editing: true })
  assert.deepEqual(parse('/projects/3/agents/9/edit/'), { name: 'agents', id: 3, agentId: 9, isNew: false, editing: true })
  assert.deepEqual(parse('/projects/3/agents/new'), { name: 'agents', id: 3, agentId: null, isNew: true, editing: true })
  assert.deepEqual(parse('/projects/3/agents/nope'), { name: 'not-found' })
  assert.deepEqual(parse('/projects/3/agents/new/edit'), { name: 'not-found' })
  assert.deepEqual(parse('/projects/3/agents/9/other'), { name: 'not-found' })
})

test('attention links target the exact task on History', () => {
  const href = taskResultHref(3, 8, 42)
  const [path, hash] = href.split('#')
  assert.deepEqual(parse(path), { name: 'project', id: 3, page: 'board', boardId: 8 })
  assert.deepEqual(parseTaskTarget(hash), { taskId: 42, tab: 'history' })
  assert.deepEqual(parseTaskTarget('task=42&tab=details'), { taskId: 42, tab: 'details' })
})

test('task targets reject invalid ids, unknown tabs and unrelated fragments', () => {
  for (const hash of ['', 'node=42', 'task=0&tab=history', 'task=-1&tab=history',
    'task=1.5&tab=history', 'task=abc&tab=history', 'task=9007199254740992&tab=history',
    'task=42', 'task=42&tab=unknown', 'task=42&tab=history&extra=1']) {
    assert.equal(parseTaskTarget(hash), null, hash)
  }
})

test('a task link opens its details unless asked for another tab', () => {
  const [, hash] = taskHref(3, 8, 42).split('#')
  assert.deepEqual(parseTaskTarget(hash), { taskId: 42, tab: 'details' })
  assert.equal(taskHref(3, 8, 42, 'history'), taskResultHref(3, 8, 42))
})

test('a workspace link names the board to land on, and nothing else is accepted', () => {
  const href = workspaceBoardHref(3, 2, 17)
  const [path, hash] = href.split('#')
  assert.deepEqual(parse(path), { name: 'project', id: 3, page: 'workspace', workspaceId: 2 })
  assert.equal(parseBoardTarget(hash), 17)
  for (const bad of ['', 'board=0', 'board=-1', 'board=1.5', 'board=abc', 'task=4&tab=details', 'board=4&x=1']) {
    assert.equal(parseBoardTarget(bad), null, bad)
  }
})
