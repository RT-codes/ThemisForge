import assert from 'node:assert/strict'
import { test } from 'node:test'
import type { Board, Column, Task, Workspace } from './api.ts'
import { boardChoices, boardSummary, columnsOf, customId, customStatusChoices, defaultBoard, destinationLabel, findBoard, lineage, whereChoices, isSimple, parseCollapsed, statusLabel, survivingBoards, taskTotal, workspaceOf } from './boards.ts'

const builtin = (key: string): Column => ({ key, name: key.charAt(0).toUpperCase() + key.slice(1), builtin: true, color: null })
const custom = (id: number, name: string, color: string | null = null): Column => ({ key: `custom:${id}`, name, builtin: false, color })
const board = (id: number, columns: Column[] = []): Board => ({ id, project_id: 1, workspace_id: 1, name: `B${id}`, purpose: '', position: id, columns, task_counts: {}, created_at: '' })
const workspace = (id: number, boards: Board[]): Workspace => ({ id, project_id: 1, name: `W${id}`, purpose: '', description: '', position: id, created_at: '', boards })

test('the default board is the first board of the first workspace that has one', () => {
  assert.equal(defaultBoard([workspace(1, []), workspace(2, [board(5), board(6)])])?.id, 5)
  assert.equal(defaultBoard([workspace(1, [board(3)]), workspace(2, [board(5)])])?.id, 3)
})

test('a project without boards has no default board', () => {
  assert.equal(defaultBoard([]), null)
  assert.equal(defaultBoard([workspace(1, [])]), null)
})

test('a board shows its columns in the order the server sent, custom ones among the built-ins', () => {
  const columns = columnsOf(board(1, [builtin('backlog'), custom(12, 'Investigating', '#aabbcc'), builtin('ready')]))
  assert.deepEqual(columns.map((c) => [c.id, c.label, c.builtin]), [['backlog', 'Backlog', true], ['custom:12', 'Investigating', false], ['ready', 'Ready', true]])
  assert.equal(columns[1].color, '#aabbcc')
  assert.match(columns[0].hint, /Recurring/)
})

test('custom ids are read from their key', () => {
  assert.equal(customId('custom:12'), 12)
  assert.equal(customId('ready'), null)
  assert.equal(customId('custom:x'), null)
})

test('a status is named after its board, and stays generic when the board cannot say', () => {
  const b = board(1, [builtin('ready'), custom(7, 'Waiting')])
  assert.equal(statusLabel('custom:7', b), 'Waiting')
  assert.equal(statusLabel('custom:7'), 'A custom status')
  assert.equal(statusLabel('custom:99', b), 'A custom status') // deleted
  assert.equal(statusLabel('blocked'), 'Blocked')
})

test('workflow steps are offered the custom statuses of every board, named by board', () => {
  const ws = [workspace(1, [board(1, [builtin('ready'), custom(1, 'Peer review')]), board(2, [builtin('ready')])]), workspace(2, [board(3, [custom(4, 'Verified')])])]
  assert.deepEqual(customStatusChoices(ws), [
    { value: 'custom:1', label: 'B1: Peer review' },
    { value: 'custom:4', label: 'B3: Verified' },
  ])
})

const withCounts = (b: Board, counts: Board['task_counts']): Board => ({ ...b, task_counts: counts })

test('boards are found by id, with the workspace they sit in', () => {
  const ws = [workspace(1, [board(3)]), workspace(2, [board(5)])]
  assert.equal(findBoard(ws, 5)?.id, 5)
  assert.equal(findBoard(ws, 9), null)
  assert.equal(workspaceOf(ws, 5)?.id, 2)
})

test('only a single workspace with a single board counts as simple', () => {
  assert.equal(isSimple([workspace(1, [board(1)])]), true)
  assert.equal(isSimple([workspace(1, [board(1), board(2)])]), false)
  assert.equal(isSimple([workspace(1, [board(1)]), workspace(2, [])]), false)
})

test('a board is summed up by its columns, in order, skipping empty ones', () => {
  const b = withCounts(board(1, [builtin('backlog'), custom(4, 'Waiting'), builtin('ready'), builtin('done')]), { done: 5, ready: 3, 'custom:4': 1 })
  assert.equal(taskTotal(b), 9)
  assert.equal(boardSummary(b), '1 waiting, 3 ready, 5 done')
  assert.equal(boardSummary(withCounts(board(2, [builtin('ready')]), {})), 'No tasks yet')
})

test('a deleted board or workspace leaves out its own boards as destinations', () => {
  const ws = [workspace(1, [{ ...board(1), workspace_id: 1 }, { ...board(2), workspace_id: 1 }]), workspace(2, [{ ...board(3), workspace_id: 2 }])]
  assert.deepEqual(survivingBoards(ws, { board: 1 }).map((b) => b.id), [2, 3])
  assert.deepEqual(survivingBoards(ws, { workspace: 1 }).map((b) => b.id), [3])
})

test('folded boards are read back, and bad storage is ignored', () => {
  assert.deepEqual(parseCollapsed('[1,2]'), [1, 2])
  assert.deepEqual(parseCollapsed(null), [])
  assert.deepEqual(parseCollapsed('nope'), [])
  assert.deepEqual(parseCollapsed('{"a":1}'), [])
  assert.deepEqual(parseCollapsed('[1,"x",2.5]'), [1])
})

const taskOf = (id: number, origin: number | null = null) => ({ id, origin_task_id: origin }) as Task

test('a board is named with its workspace only when the project has several', () => {
  const one = [workspace(1, [{ ...board(1), workspace_id: 1 }])]
  const two = [...one, workspace(2, [{ ...board(2), workspace_id: 2 }])]
  assert.equal(destinationLabel(one, one[0].boards[0]), 'B1')
  assert.equal(destinationLabel(two, two[1].boards[0]), 'W2: B2')
})

test('a task knows what it follows and what followed it', () => {
  const tasks = [taskOf(1), taskOf(2, 1), taskOf(3, 1), taskOf(4, 99)]
  assert.deepEqual(lineage(tasks, tasks[0]).followUps.map((t) => t.id), [2, 3])
  assert.equal(lineage(tasks, tasks[1]).origin?.id, 1)
  assert.equal(lineage(tasks, tasks[0]).origin, null)
  assert.equal(lineage(tasks, tasks[3]).origin, null) // the task it followed was deleted
})

test('a step picks a board by id and a trigger a workspace or a board', () => {
  const ws = [
    workspace(1, [{ ...board(1, [builtin('ready'), custom(5, 'Waiting')]), workspace_id: 1 }]),
    workspace(2, [{ ...board(2), workspace_id: 2 }]),
  ]
  assert.deepEqual(boardChoices(ws), [{ value: '1', label: 'W1: B1' }, { value: '2', label: 'W2: B2' }])
  assert.deepEqual(whereChoices(ws).map((c) => c.value), ['w:1', 'w:2', 'b:1', 'b:2'])
  // knowing the board, its own statuses are listed without its name
  assert.deepEqual(customStatusChoices(ws, 1), [{ value: 'custom:5', label: 'Waiting' }])
  assert.deepEqual(customStatusChoices(ws, 2), [])
})
