// Projects, workspaces, boards and the history of what happened in them.

import { request, send } from './core'
import type { ProfileOverrides } from './settings'
import type { PropertyDef, TaskStatus } from './tasks'

/** The parts of the automation guard a project may change; an empty field uses the settings' value */
export interface AutomationOverrides {
  start_cooldown_seconds?: number | null
  max_hops?: number | null
}

export interface Project {
  id: number
  name: string
  /** one line on what it is for */
  purpose: string
  description: string
  /** a Lucide icon name such as "folder-kanban"; empty is the default icon */
  icon: string
  properties: PropertyDef[]
  cell_profile: ProfileOverrides | null
  automation: AutomationOverrides | null
  /** set while the project is halted: nothing in it starts until it is resumed */
  halted_at: string | null
  created_at: string
}

/** A column of a board: one of the seven built-in statuses, or a custom one the board added */
export interface Column {
  key: string // "ready", or "custom:12"
  name: string
  builtin: boolean
  color: string | null // custom statuses only
  icon: string // custom statuses only: a Lucide icon name (the built-in ones have theirs in the interface)
  description: string // custom statuses only: what it is for, in its owner's words
}

export interface Board {
  id: number
  project_id: number
  workspace_id: number
  name: string
  purpose: string
  position: number
  columns: Column[]
  task_counts: Partial<Record<TaskStatus, number>>
  /** set while the board is halted: none of its tasks start until it is resumed */
  halted_at: string | null
  created_at: string
}

/** A named area of a project that holds boards (not the /workspace folder inside a cell) */
export interface Workspace {
  id: number
  project_id: number
  name: string
  purpose: string
  description: string
  icon: string
  position: number
  created_at: string
  boards: Board[]
}

export interface ProjectSummary extends Project {
  task_counts: Partial<Record<TaskStatus, number>>
  next_run_at: string | null
}

export interface ProjectEvent {
  id: number
  kind: 'task_deleted' | 'task_moved' | 'task_spawned' | string
  title: string
  actor: string
  /** what set it off when it was not a person: "run:<workflow run>:<node>" */
  cause: string
  workspace_id: number | null
  board_id: number | null
  task_id: number | null
  /** a copy of the thing as it was (for a deleted task: its description, status, schedule...) */
  data: Record<string, unknown>
  created_at: string
}

export const projectsApi = {
  projects: () => request<ProjectSummary[]>('/projects'),
  project: (id: number) => request<Project>(`/projects/${id}`),
  createProject: (body: { name: string; purpose?: string; description?: string; icon?: string; cell_profile?: ProfileOverrides | null }) =>
    request<Project>('/projects', send('POST', body)),
  updateProject: (id: number, patch: Partial<Pick<Project, 'name' | 'purpose' | 'description' | 'icon' | 'properties' | 'cell_profile' | 'automation'>>) =>
    request<Project>(`/projects/${id}`, send('PATCH', patch)),
  deleteProject: (id: number) => request<void>(`/projects/${id}`, send('DELETE')),
  workspaces: (projectId: number) => request<Workspace[]>(`/projects/${projectId}/workspaces`),
  createWorkspace: (projectId: number, body: { name: string; purpose?: string; description?: string; icon?: string }) =>
    request<Workspace>(`/projects/${projectId}/workspaces`, send('POST', body)),
  updateWorkspace: (id: number, patch: { name?: string; purpose?: string; description?: string; icon?: string; position?: number }) =>
    request<Workspace>(`/workspaces/${id}`, send('PATCH', patch)),
  /** `moveTo`: the board that takes over the tasks of its boards (needed when there are any) */
  deleteWorkspace: (id: number, moveTo?: number) => request<void>(`/workspaces/${id}${moveTo ? `?move_to=${moveTo}` : ''}`, send('DELETE')),
  createBoard: (workspaceId: number, body: { name: string; purpose?: string }) =>
    request<Board>(`/workspaces/${workspaceId}/boards`, send('POST', body)),
  /** `stopRunning` also stops what is running in it; off only holds back what is next */
  haltProject: (id: number, stopRunning = true) => request<Project>(`/projects/${id}/halt`, send('POST', { stop_running: stopRunning })),
  resumeProject: (id: number) => request<Project>(`/projects/${id}/resume`, send('POST')),
  haltBoard: (id: number, stopRunning = true) => request<Board>(`/boards/${id}/halt`, send('POST', { stop_running: stopRunning })),
  resumeBoard: (id: number) => request<Board>(`/boards/${id}/resume`, send('POST')),
  updateBoard: (id: number, patch: { name?: string; purpose?: string; position?: number; workspace_id?: number }) =>
    request<Board>(`/boards/${id}`, send('PATCH', patch)),
  duplicateBoard: (id: number) => request<Board>(`/boards/${id}/duplicate`, send('POST')),
  deleteBoard: (id: number, moveTo?: number) => request<void>(`/boards/${id}${moveTo ? `?move_to=${moveTo}` : ''}`, send('DELETE')),
  addStatus: (boardId: number, body: { name: string; color?: string | null; index?: number; icon?: string; description?: string }) =>
    request<Board>(`/boards/${boardId}/statuses`, send('POST', body)),
  updateStatus: (boardId: number, statusId: number, patch: { name?: string; color?: string | null; index?: number; icon?: string; description?: string }) =>
    request<Board>(`/boards/${boardId}/statuses/${statusId}`, send('PATCH', patch)),
  /** its tasks go to `moveTo` (a status of the board; the server defaults to Backlog) */
  removeStatus: (boardId: number, statusId: number, moveTo?: TaskStatus) =>
    request<Board>(`/boards/${boardId}/statuses/${statusId}${moveTo ? `?move_to=${encodeURIComponent(moveTo)}` : ''}`, send('DELETE')),
  /** `query` comes from historyQuery() */
  projectHistory: (projectId: number, query: string) => request<ProjectEvent[]>(`/projects/${projectId}/history?${query}`),
}
