import assert from 'node:assert/strict'
import { test } from 'node:test'
import type { Board, Workspace } from './api.ts'
import { defaultBoard } from './boards.ts'

const board = (id: number): Board => ({ id, project_id: 1, workspace_id: 1, name: `B${id}`, purpose: '', position: id, columns: [], created_at: '' })
const workspace = (id: number, boards: Board[]): Workspace => ({ id, project_id: 1, name: `W${id}`, purpose: '', description: '', position: id, created_at: '', boards })

test('the default board is the first board of the first workspace that has one', () => {
  assert.equal(defaultBoard([workspace(1, []), workspace(2, [board(5), board(6)])])?.id, 5)
  assert.equal(defaultBoard([workspace(1, [board(3)]), workspace(2, [board(5)])])?.id, 3)
})

test('a project without boards has no default board', () => {
  assert.equal(defaultBoard([]), null)
  assert.equal(defaultBoard([workspace(1, [])]), null)
})
