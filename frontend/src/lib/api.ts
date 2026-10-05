export interface User {
  id: number
  email: string
  name: string
  is_admin: boolean
}

export type TaskStatus = 'inbox' | 'ready' | 'running' | 'review' | 'done' | 'blocked' | 'failed'
export type ScheduleKind = 'none' | 'once' | 'cron'
export type AttemptStatus = 'running' | 'succeeded' | 'failed' | 'cancelled'
export type PropertyType = 'text' | 'number' | 'select' | 'checkbox' | 'date'
export type PropertyValue = string | number | boolean

export interface PropertyDef {
  key: string
  name: string
  type: PropertyType
  options: string[]
}

export interface Project {
  id: number
  name: string
  description: string
  properties: PropertyDef[]
  created_at: string
}

export interface ProjectSummary extends Project {
  task_counts: Partial<Record<TaskStatus, number>>
  next_run_at: string | null
}

export type Harness = '' | 'codex'

export interface Task {
  id: number
  project_id: number
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
  created_at: string
  updated_at: string
  last_attempt_status: AttemptStatus | null
}

export interface TaskInput {
  title: string
  description?: string
  status?: TaskStatus
  properties?: Record<string, PropertyValue>
  schedule_kind?: ScheduleKind
  cron?: string | null
  run_at?: string | null
  review_on_success?: boolean
  harness?: Harness
}

export type TaskPatch = Partial<TaskInput> & { position?: number }

export interface Attempt {
  id: number
  task_id: number
  status: AttemptStatus
  started_at: string
  finished_at: string | null
  exit_code: number | null
}

export interface AttemptDetail extends Attempt {
  log: string
  result: string
}

export interface ScheduledRun {
  task_id: number
  title: string
  at: string
  recurring: boolean
}

export interface AppSettings {
  timezone: string
  docker_host: string
  cell_image: string
  cell_cpus: number
  cell_memory_mb: number
  cell_timeout_seconds: number
  max_concurrent_cells: number
  codex_image: string
  keep_workspaces_days: number
}

export interface DockerStatus {
  ok: boolean
  installed: boolean
  host: string
  version: string | null
  os: string | null
  cpus: number | null
  memory_mb: number | null
  error: string | null
  hint: string | null
}

export interface SystemStatus {
  scheduler: { running: boolean; active_cells: number; max_cells: number }
  timezone: string
  pending_access_requests: number
  insecure_secret_key: boolean
  cell_backend: string
}

export interface AccessRequest {
  id: number
  name: string
  email: string
  reason: string
  status: 'pending' | 'approved' | 'denied'
  created_at: string
  decided_at: string | null
}

export interface Invite {
  id: number
  email: string
  created_at: string
  expires_at: string
}

export interface InviteCreated extends Invite {
  token: string
}

export interface Secret {
  id: number
  name: string
  kind: string
  hint: string
  created_at: string
}

export interface CodexLogin {
  status: 'starting' | 'waiting' | 'connected' | 'failed' | 'cancelled'
  verification_url: string
  code: string
  expires_at: string | null
  error: string
}

export interface CodexStatus {
  cli_installed: boolean
  secret_key_secure: boolean
  connected: boolean
  needs_reconnect: boolean
  account: string
  connected_at: string | null
  refreshed_at: string | null
  login: CodexLogin | null
}

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message)
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`/api${path}`, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...init?.headers },
  })
  if (!res.ok) {
    let detail = res.statusText
    try {
      const body = await res.json()
      if (typeof body.detail === 'string') detail = body.detail
      else if (Array.isArray(body.detail)) detail = body.detail[0]?.msg?.replace(/^Value error, /, '') ?? detail
    } catch {
      // non-JSON error body
    }
    throw new ApiError(res.status, detail)
  }
  return res.status === 204 ? (undefined as T) : res.json()
}

const send = (method: string, body?: unknown): RequestInit => ({
  method,
  body: body === undefined ? undefined : JSON.stringify(body),
})

export const api = {
  me: () => request<User>('/auth/me'),
  login: (email: string, password: string) => request<User>('/auth/login', send('POST', { email, password })),
  register: (name: string, email: string, password: string) =>
    request<User>('/auth/register', send('POST', { name, email, password })),
  logout: () => request<void>('/auth/logout', send('POST')),
  setup: () => request<{ needs_admin: boolean }>('/auth/setup'),

  requestAccess: (name: string, email: string, reason: string) =>
    request<{ status: string }>('/access-requests', send('POST', { name, email, reason })),
  accessRequests: () => request<AccessRequest[]>('/access-requests'),
  approveRequest: (id: number) => request<InviteCreated>(`/access-requests/${id}/approve`, send('POST')),
  denyRequest: (id: number) => request<AccessRequest>(`/access-requests/${id}/deny`, send('POST')),
  invites: () => request<Invite[]>('/invites'),
  createInvite: (email: string) => request<InviteCreated>('/invites', send('POST', { email })),
  revokeInvite: (id: number) => request<void>(`/invites/${id}`, send('DELETE')),
  checkInvite: (token: string) => request<{ email: string }>(`/invites/by-token/${encodeURIComponent(token)}`),
  acceptInvite: (token: string, name: string, password: string) =>
    request<User>(`/invites/by-token/${encodeURIComponent(token)}/accept`, send('POST', { name, password })),

  projects: () => request<ProjectSummary[]>('/projects'),
  project: (id: number) => request<Project>(`/projects/${id}`),
  createProject: (name: string, description = '') => request<Project>('/projects', send('POST', { name, description })),
  updateProject: (id: number, patch: Partial<Pick<Project, 'name' | 'description' | 'properties'>>) =>
    request<Project>(`/projects/${id}`, send('PATCH', patch)),
  deleteProject: (id: number) => request<void>(`/projects/${id}`, send('DELETE')),

  tasks: (projectId: number) => request<Task[]>(`/projects/${projectId}/tasks`),
  createTask: (projectId: number, body: TaskInput) => request<Task>(`/projects/${projectId}/tasks`, send('POST', body)),
  updateTask: (id: number, patch: TaskPatch) => request<Task>(`/tasks/${id}`, send('PATCH', patch)),
  deleteTask: (id: number) => request<void>(`/tasks/${id}`, send('DELETE')),
  runTask: (id: number) => request<Task>(`/tasks/${id}/run`, send('POST')),
  cancelTask: (id: number) => request<Task>(`/tasks/${id}/cancel`, send('POST')),
  attempts: (taskId: number) => request<Attempt[]>(`/tasks/${taskId}/attempts`),
  attempt: (id: number) => request<AttemptDetail>(`/attempts/${id}`),
  schedule: (projectId: number, hours: number) =>
    request<ScheduledRun[]>(`/projects/${projectId}/schedule?hours=${hours}`),

  systemStatus: () => request<SystemStatus>('/system/status'),
  docker: (host?: string) =>
    request<DockerStatus>(`/system/docker${host === undefined ? '' : `?host=${encodeURIComponent(host)}`}`),
  settings: () => request<AppSettings>('/settings'),
  saveSettings: (body: AppSettings) => request<AppSettings>('/settings', send('PUT', body)),
  secrets: () => request<Secret[]>('/secrets'),
  createSecret: (name: string, kind: string, value: string) =>
    request<Secret>('/secrets', send('POST', { name, kind, value })),
  deleteSecret: (id: number) => request<void>(`/secrets/${id}`, send('DELETE')),

  codex: () => request<CodexStatus>('/codex'),
  codexStartLogin: () => request<CodexLogin>('/codex/login', send('POST')),
  codexCancelLogin: () => request<void>('/codex/login', send('DELETE')),
  codexDisconnect: () => request<void>('/codex', send('DELETE')),
}
