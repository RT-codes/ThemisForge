import assert from 'node:assert/strict'
import { test } from 'node:test'
import type { Board, Column, Workspace } from './api.ts'
import { columnsOf, customId, customStatusChoices, defaultBoard, statusLabel } from './boards.ts'

const builtin = (key: string): Column => ({ key, name: key.charAt(0).toUpperCase() + key.slice(1), builtin: true, color: null })
const custom = (id: number, name: string, color: string | null = null): Column => ({ key: `custom:${id}`, name, builtin: false, color })
const board = (id: number, columns: Column[] = []): Board => ({ id, project_id: 1, workspace_id: 1, name: `B${id}`, purpose: '', position: id, columns, created_at: '' })
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
