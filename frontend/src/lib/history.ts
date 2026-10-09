// The project's history: what each kind of event says, how events are grouped for filtering, and the address of a scope.

import type { ProjectEvent } from './api'

/** Where in the project to look: everything, or only what concerns one workspace, board or task. */
export type HistoryScope = { workspaceId?: number; boardId?: number; taskId?: number }

export const KIND_GROUPS = [
  { id: 'all', label: 'Everything', kinds: [] as string[] },
  { id: 'tasks', label: 'Tasks', kinds: ['task_created', 'task_status', 'task_moved', 'task_spawned', 'task_deleted', 'automation_stopped'] },
  {
    id: 'structure',
    label: 'Boards and statuses',
    kinds: ['workspace_created', 'workspace_renamed', 'workspace_deleted', 'board_created', 'board_renamed', 'board_deleted', 'status_added', 'status_renamed', 'status_removed'],
  },
]

/** The query string for a page of history: the scope, a group of kinds, and the id to continue after. */
export function historyQuery(scope: HistoryScope, kinds: string[], before: number | null, limit: number): string {
  const q = new URLSearchParams({ limit: String(limit) })
  if (scope.workspaceId !== undefined) q.set('workspace_id', String(scope.workspaceId))
  if (scope.boardId !== undefined) q.set('board_id', String(scope.boardId))
  if (scope.taskId !== undefined) q.set('task_id', String(scope.taskId))
  if (before !== null) q.set('before', String(before))
  for (const kind of kinds) q.append('kind', kind)
  return q.toString()
}

/** A status as an event tells it. The name of a custom status is not kept in the event, so it stays generic. */
const statusLabel = (status: string) => (status.startsWith('custom:') ? 'a custom status' : status.charAt(0).toUpperCase() + status.slice(1))

type Place = { board?: string; status?: string | null }
const place = (part: unknown): Place => (part && typeof part === 'object' ? (part as Place) : {})
const name = (part: unknown) => place(part).board ?? 'a board'

/** One line of text for an event. Unknown kinds (from a newer version) still show their title. */
export function describeEvent(e: ProjectEvent): string {
  const d = e.data
  switch (e.kind) {
    case 'task_created':
      return `Created the task "${e.title}" on ${name(d.to)}`
    case 'task_status': {
      const from = place(d.from).status
      const to = place(d.to).status
      return `Moved the task "${e.title}" from ${from ? statusLabel(from) : 'a status'} to ${to ? statusLabel(to) : 'another'}`
    }
    case 'task_moved':
      return `Sent the task "${e.title}" from ${name(d.from)} to ${name(d.to)}`
    case 'task_spawned': {
      const origin = d.origin as { title?: string } | undefined
      return `Created the task "${e.title}" on ${name(d.to)} as a follow-up of "${origin?.title ?? 'another task'}"`
    }
    case 'task_deleted': {
      const was = typeof d.status === 'string' ? ` (was in ${statusLabel(d.status)})` : ''
      return `Deleted the task "${e.title}"${was}`
    }
    case 'automation_stopped':
      return `Stopped automation on the task "${e.title}": ${typeof d.reason === 'string' ? d.reason.replace(/^Stopped to keep automation from looping: /, '') : 'a loop'}`
    case 'workspace_created':
      return `Created the workspace "${e.title}"`
    case 'workspace_renamed':
      return `Renamed the workspace "${d.was}" to "${e.title}"`
    case 'workspace_deleted':
      return `Deleted the workspace "${e.title}"${moved(d)}`
    case 'board_created':
      return d.copy_of ? `Duplicated the board "${d.copy_of}" as "${e.title}"` : `Created the board "${e.title}" in ${d.workspace ?? 'a workspace'}`
    case 'board_renamed':
      return `Renamed the board "${d.was}" to "${e.title}"`
    case 'board_deleted':
      return `Deleted the board "${e.title}"${moved(d)}`
    case 'status_added':
      return `Added the status "${e.title}" to ${d.board ?? 'a board'}`
    case 'status_renamed':
      return `Renamed the status "${d.was}" to "${e.title}" on ${d.board ?? 'a board'}`
    case 'status_removed': {
      const n = Number(d.moved ?? 0)
      return `Deleted the status "${e.title}" from ${d.board ?? 'a board'}${n ? `, moving ${n} ${n === 1 ? 'task' : 'tasks'} to ${typeof d.to === 'string' ? statusLabel(d.to) : 'another status'}` : ''}`
    }
    default:
      return e.title
  }
}

function moved(d: Record<string, unknown>): string {
  const n = Number(d.moved ?? 0)
  return n ? `, moving ${n} ${n === 1 ? 'task' : 'tasks'} to ${d.to ?? 'another board'}` : ''
}
