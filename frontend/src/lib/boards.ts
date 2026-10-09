// Workspaces and boards: pure helpers for picking boards and describing their columns (the pages do the loading).

import type { Board, BuiltinStatus, TaskStatus, Workspace } from './api'

/** The project's first board: first workspace, first board in it (the server sends both in display order). */
export function defaultBoard(workspaces: Workspace[]): Board | null {
  for (const workspace of workspaces) if (workspace.boards.length) return workspace.boards[0]
  return null
}

/** What each built-in status means. The seven are the same on every board; their names come from the server. */
export const BUILTIN_HINTS: Record<BuiltinStatus, string> = {
  backlog: 'Not scheduled yet. Recurring tasks parked here are paused.',
  ready: 'Picked up by the scheduler when due.',
  running: 'A cell is working on it.',
  review: 'Finished, waiting for a human.',
  done: 'Finished.',
  blocked: 'Waiting on something or cancelled.',
  failed: 'The last attempt failed.',
}

export const CUSTOM_HINT = 'A status of this board. Tasks wait here until you move them on.'

/** One column of a board as the interface shows it */
export interface ColumnInfo {
  id: TaskStatus
  label: string
  hint: string
  builtin: boolean
  color: string | null // custom statuses only
}

/** A board's columns left to right: the built-in statuses with the custom ones placed among them. */
export function columnsOf(board: Board): ColumnInfo[] {
  return board.columns.map((c) => ({
    id: c.key as TaskStatus,
    label: c.name,
    hint: c.builtin ? BUILTIN_HINTS[c.key as BuiltinStatus] : CUSTOM_HINT,
    builtin: c.builtin,
    color: c.color,
  }))
}

/** The id behind a "custom:12" status; null for a built-in one. */
export function customId(status: string): number | null {
  const m = status.match(/^custom:(\d+)$/)
  return m ? Number(m[1]) : null
}

/** A status as a person reads it. A custom status needs its board for a name; without it (or after it was deleted) the
 *  text stays generic rather than showing "custom:12". */
export function statusLabel(status: string, board?: Board | null): string {
  const column = board?.columns.find((c) => c.key === status)
  if (column) return column.name
  if (customId(status) !== null) return 'A custom status'
  return status.charAt(0).toUpperCase() + status.slice(1)
}

/** The custom statuses of all boards as choices for a workflow step ("Development: Peer review"). The built-in ones are
 *  the same everywhere, so a step lists them once on its own. */
export function customStatusChoices(workspaces: Workspace[]): { value: string; label: string }[] {
  return workspaces.flatMap((w) =>
    w.boards.flatMap((b) => b.columns.filter((c) => !c.builtin).map((c) => ({ value: c.key, label: `${b.name}: ${c.name}` })))
  )
}

export function findBoard(workspaces: Workspace[], boardId: number): Board | null {
  for (const workspace of workspaces) {
    const board = workspace.boards.find((b) => b.id === boardId)
    if (board) return board
  }
  return null
}

export const workspaceOf = (workspaces: Workspace[], boardId: number): Workspace | null => workspaces.find((w) => w.boards.some((b) => b.id === boardId)) ?? null

/** One workspace with one board is how every project starts. It is shown the way tasks always were: a single "Tasks" page,
 *  with no workspace level in between. */
export const isSimple = (workspaces: Workspace[]): boolean => workspaces.length === 1 && workspaces[0].boards.length === 1

/** how many tasks a board holds, whatever their status */
export const taskTotal = (board: Board): number => Object.values(board.task_counts).reduce<number>((sum, n) => sum + (n ?? 0), 0)

/** The boards that can take over the tasks of a board or workspace that is being deleted. */
export function survivingBoards(workspaces: Workspace[], leaving: { board?: number; workspace?: number }): Board[] {
  return workspaces.flatMap((w) => w.boards.filter((b) => b.id !== leaving.board && b.workspace_id !== leaving.workspace))
}

/** A one-line summary of a board for a collapsed card or an overview: "3 ready, 1 running, 5 done". */
export function boardSummary(board: Board): string {
  const parts = board.columns
    .filter((c) => (board.task_counts[c.key as keyof typeof board.task_counts] ?? 0) > 0)
    .map((c) => `${board.task_counts[c.key as keyof typeof board.task_counts]} ${c.name.toLowerCase()}`)
  return parts.length ? parts.join(', ') : 'No tasks yet'
}

/** The boards a person folded away on a workspace page, kept in this browser. */
export function parseCollapsed(raw: string | null): number[] {
  try {
    const value = JSON.parse(raw ?? '[]')
    return Array.isArray(value) ? value.filter((n): n is number => Number.isInteger(n)) : []
  } catch {
    return []
  }
}
