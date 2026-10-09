// Workspaces and boards: pure helpers for picking boards and describing their columns (the pages do the loading).

import type { Board, BuiltinStatus, Task, TaskStatus, Workspace } from './api'

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

/** what a status of your own says about itself until its owner writes something */
export const CUSTOM_HINT = 'A status of this board. Tasks wait here until you move them on.'

/** How each built-in status looks (Tailwind classes for its dot and its figures). Done is green, Blocked and Failed are
 *  red. A status of your own has no tone: it brings its own colour, or this one. */
const TONES: Record<string, { dot: string; text: string }> = {
  backlog: { dot: 'bg-muted-foreground/60', text: 'text-foreground' },
  ready: { dot: 'bg-sky-400', text: 'text-sky-300' },
  running: { dot: 'bg-primary', text: 'text-primary' },
  review: { dot: 'bg-violet-400', text: 'text-violet-300' },
  done: { dot: 'bg-emerald-400', text: 'text-emerald-300' },
  blocked: { dot: 'bg-red-400', text: 'text-red-300' },
  failed: { dot: 'bg-rose-500', text: 'text-rose-400' },
}
export const statusTone = (key: string) => TONES[key] ?? TONES.backlog

/** One column of a board as the interface shows it */
export interface ColumnInfo {
  id: TaskStatus
  label: string
  /** what the status is for, as the tooltip says it: the fixed text of a built-in status, or its owner's own words */
  hint: string
  builtin: boolean
  color: string | null // custom statuses only
  icon: string // custom statuses only: a Lucide icon name
  /** the owner's own words, "" when there are none (a custom status only; the form edits this one) */
  description: string
}

/** A board's columns left to right: the built-in statuses with the custom ones placed among them. */
export function columnsOf(board: Board): ColumnInfo[] {
  return board.columns.map((c) => ({
    id: c.key as TaskStatus,
    label: c.name,
    hint: c.builtin ? BUILTIN_HINTS[c.key as BuiltinStatus] : c.description || CUSTOM_HINT,
    builtin: c.builtin,
    color: c.color,
    icon: c.icon,
    description: c.description,
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
export function customStatusChoices(workspaces: Workspace[], onlyBoard: number | null = null): { value: string; label: string }[] {
  return workspaces.flatMap((w) =>
    w.boards
      .filter((b) => onlyBoard === null || b.id === onlyBoard)
      // once the board is known its name adds nothing
      .flatMap((b) => b.columns.filter((c) => !c.builtin).map((c) => ({ value: c.key, label: onlyBoard === null ? `${b.name}: ${c.name}` : c.name })))
  )
}

/** The boards as choices for a workflow step, by id ("Workspace: Board"). */
export function boardChoices(workspaces: Workspace[]): { value: string; label: string }[] {
  return workspaces.flatMap((w) => w.boards.map((b) => ({ value: String(b.id), label: destinationLabel(workspaces, b) })))
}

/** Where a Trigger can look: the whole project (the field's own first option), one workspace ("w:<id>"), or one board ("b:<id>"). */
export function whereChoices(workspaces: Workspace[]): { value: string; label: string }[] {
  return [
    ...workspaces.map((w) => ({ value: `w:${w.id}`, label: `Workspace ${w.name}` })),
    ...boardChoices(workspaces).map((c) => ({ value: `b:${c.value}`, label: `Board ${c.label}` })),
  ]
}

export function findBoard(workspaces: Workspace[], boardId: number): Board | null {
  for (const workspace of workspaces) {
    const board = workspace.boards.find((b) => b.id === boardId)
    if (board) return board
  }
  return null
}

export const workspaceOf = (workspaces: Workspace[], boardId: number): Workspace | null => workspaces.find((w) => w.boards.some((b) => b.id === boardId)) ?? null

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

/** A board's height after the person dragged its handle: not too small to use, not taller than most of the window. */
export function clampHeight(px: number, viewport: number): number {
  const most = Math.max(MIN_BOARD_HEIGHT, Math.floor(viewport * 0.9))
  return Math.round(Math.min(Math.max(px, MIN_BOARD_HEIGHT), most))
}
export const MIN_BOARD_HEIGHT = 256

/** The boards a person folded away on a workspace page, kept in this browser. */
export function parseCollapsed(raw: string | null): number[] {
  try {
    const value = JSON.parse(raw ?? '[]')
    return Array.isArray(value) ? value.filter((n): n is number => Number.isInteger(n)) : []
  } catch {
    return []
  }
}

/** A board as a choice: "Workspace: Board", or just the board's name while the project has a single workspace. */
export function destinationLabel(workspaces: Workspace[], board: Board): string {
  const workspace = workspaces.find((w) => w.id === board.workspace_id)
  return workspaces.length > 1 && workspace ? `${workspace.name}: ${board.name}` : board.name
}

/** The follow-ups of a task and the task it follows, from the tasks of the project. */
export function lineage(tasks: Task[], task: Task): { origin: Task | null; followUps: Task[] } {
  return {
    origin: task.origin_task_id === null ? null : (tasks.find((t) => t.id === task.origin_task_id) ?? null),
    followUps: tasks.filter((t) => t.origin_task_id === task.id),
  }
}
