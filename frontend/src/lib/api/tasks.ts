// Tasks, their attempts and the custom properties a project gives them (backend/app/routers/tasks.py).

import { failure, request, send } from './core'
import type { RunStatus } from './workflows'

/** the seven statuses every board has, locked */
export type BuiltinStatus = 'backlog' | 'ready' | 'running' | 'review' | 'done' | 'blocked' | 'failed'

/** a built-in status, or a custom one of the task's board: "custom:12" */
export type TaskStatus = BuiltinStatus | `custom:${number}`

export type ScheduleKind = 'none' | 'once' | 'cron'

export type AttemptStatus = 'running' | 'succeeded' | 'failed' | 'cancelled'

export type PropertyType = 'text' | 'number' | 'select' | 'checkbox' | 'date'

export type PropertyValue = string | number | boolean

export interface PropertyDef {
  key: string
  name: string
  type: PropertyType
  options: string[]
  colors?: Record<string, string> // option -> "#rrggbb", for select properties
}

export type Harness = '' | 'codex' | 'workflow'

/** one workflow a task plays; "pending" until a run of it starts, then the run's own status */
export interface TaskStage {
  workflow_id: number
  workflow_name: string
  status: 'pending' | RunStatus
  run_id: number | null
}

export interface Task {
  id: number
  project_id: number
  board_id: number
  /** the task this one was spawned from, as a follow-up */
  origin_task_id: number | null
  title: string
  description: string
  status: TaskStatus
  position: number
  properties: Record<string, PropertyValue>
  schedule_kind: ScheduleKind
  cron: string | null
  run_at: string | null
  next_run_at: string | null
  last_run_at: string | null
  review_on_success: boolean
  harness: Harness
  agent_id: number | null
  /** made by a workflow's Agent node to run its step: not board work, so it is only listed when asked for */
  internal: boolean
  /** the workflows this task plays, in order, each with how far its latest attempt got */
  stages: TaskStage[]
  /** how many times in a row automation moved or made this task; a person acting on it starts again at 0 */
  hops: number
  /** this task's own automation guard; null follows the project's */
  cooldown_seconds: number | null
  max_hops: number | null
  created_at: string
  updated_at: string
  last_attempt_status: AttemptStatus | null
  /** why the latest attempt failed, in a sentence for the card; empty when it did not fail */
  last_failure_reason: string
  /** the workflow run this task started that is still going, if any */
  workflow_run: { run_id: number; workflow_id: number; workflow_name: string; step: string } | null
}

export interface TaskInput {
  title: string
  description?: string
  status?: TaskStatus
  board_id?: number // left out: the project's first board
  properties?: Record<string, PropertyValue>
  schedule_kind?: ScheduleKind
  cron?: string | null
  run_at?: string | null
  review_on_success?: boolean
  harness?: Harness
  /** the workflows to play in order, when harness is "workflow" */
  workflow_ids?: number[]
  agent_id?: number | null
  cooldown_seconds?: number | null
  max_hops?: number | null
}

export type TaskPatch = Partial<TaskInput> & { position?: number }

export interface Attempt {
  workflow_run_id?: number | null
  id: number
  task_id: number
  status: AttemptStatus
  started_at: string
  finished_at: string | null
  exit_code: number | null
}

/** Why an attempt failed: found by Themis from what it saw, or written by the agent that stopped and said so */
export interface AttemptFailure {
  source: 'themis' | 'agent'
  reason: string
  /** what the person can change; empty when nobody knows */
  action: string
  /** the last lines of the log of what failed */
  tail: string
}

export interface AttemptDetail extends Attempt {
  workflow_id: number | null
  failure: AttemptFailure | null
  log: string
  result: string
}

export interface ScheduledRun {
  task_id: number
  title: string
  at: string
  recurring: boolean
}

export const tasksApi = {
  tasks: (projectId: number, includeSteps = false) =>
    request<Task[]>(`/projects/${projectId}/tasks${includeSteps ? '?include_steps=true' : ''}`),
  createTask: (projectId: number, body: TaskInput) => request<Task>(`/projects/${projectId}/tasks`, send('POST', body)),
  updateTask: (id: number, patch: TaskPatch) => request<Task>(`/tasks/${id}`, send('PATCH', patch)),
  /** the same task continues on another board (and status) */
  moveTask: (id: number, body: { board_id: number; status?: TaskStatus; position?: number }) =>
    request<Task>(`/tasks/${id}/move`, send('POST', body)),
  /** a new task on a board, linked to this one; this one stays where it is */
  spawnTask: (id: number, body: { board_id: number; title?: string; description?: string; status?: TaskStatus }) =>
    request<Task>(`/tasks/${id}/spawn`, send('POST', body)),
  /** the same task again, in the Backlog of its board, without its history */
  duplicateTask: (id: number) => request<Task>(`/tasks/${id}/duplicate`, send('POST')),
  deleteTask: (id: number) => request<void>(`/tasks/${id}`, send('DELETE')),
  runTask: (id: number) => request<Task>(`/tasks/${id}/run`, send('POST')),
  cancelTask: (id: number) => request<Task>(`/tasks/${id}/cancel`, send('POST')),
  attempts: (taskId: number) => request<Attempt[]>(`/tasks/${taskId}/attempts`),
  attempt: (id: number) => request<AttemptDetail>(`/attempts/${id}`),
  schedule: (projectId: number, hours: number) =>
    request<ScheduledRun[]>(`/projects/${projectId}/schedule?hours=${hours}`),
}
