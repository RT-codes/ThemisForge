import type { Graph, NodeKind } from './workflow'
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
  colors?: Record<string, string> // option -> "#rrggbb", for select properties
}

/** the parts of a cell a project, agent or run may change: only the fields that are set override anything */
export interface ProfileOverrides {
  image?: string | null
  cpus?: number | null
  memory_mb?: number | null
  timeout_seconds?: number | null
}

export interface Project {
  id: number
  name: string
  description: string
  properties: PropertyDef[]
  cell_profile: ProfileOverrides | null
  created_at: string
}

export interface ProjectSummary extends Project {
  task_counts: Partial<Record<TaskStatus, number>>
  next_run_at: string | null
}

export type Harness = '' | 'codex' | 'workflow'

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
  workflow_id: number | null
  agent_id: number | null
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
  workflow_id?: number | null
  agent_id?: number | null
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

export interface AttemptDetail extends Attempt {
  workflow_id: number | null
  log: string
  result: string
}

export interface ScheduledRun {
  task_id: number
  title: string
  at: string
  recurring: boolean
}

export interface MountRoot {
  path: string
  allow_write: boolean
}

export interface Volume {
  id: number
  project_id: number
  name: string
  kind: 'managed' | 'host'
  host_path: string
  mode: 'ro' | 'rw'
  exclusive_write: boolean
  created_at: string
  is_default: boolean
  problem: string | null
  can_write: boolean
}

export interface VolumeInput {
  name: string
  kind?: 'managed' | 'host'
  host_path?: string
  mode?: 'ro' | 'rw'
  exclusive_write?: boolean | null
}

export interface MountRef {
  volume_id: number
  mode: 'ro' | 'rw'
}

export interface Agent {
  id: number
  project_id: number
  name: string
  role: string
  description: string
  instructions: string
  harness: string
  model: string
  reasoning_effort: '' | 'low' | 'medium' | 'high'
  cell_profile: ProfileOverrides | null
  mounts: MountRef[]
  skills: string[]
  mcp_servers: number[]
  secrets: number[]
  created_at: string
  updated_at: string
}

export interface Skill {
  name: string
  description: string
  files: number
}

export interface SkillDetail extends Skill {
  content: string
}

export interface McpServer {
  id: number
  project_id: number
  name: string
  kind: 'stdio' | 'http'
  command: string
  args: string[]
  url: string
  env: Record<string, string>
  secret_env: Record<string, number>
  bearer_secret_id: number | null
  created_at: string
}

export type McpInput = Omit<McpServer, 'id' | 'project_id' | 'created_at'>

/** a stored key as an agent sees it: never its value, only the variable it is available as */
export interface KeyInfo {
  id: number
  name: string
  kind: string
  env_name: string
}

export interface AgentCheck {
  image: string
  warnings: string[]
}

export type AgentInput = Omit<Agent, 'id' | 'project_id' | 'created_at' | 'updated_at'>

export interface HarnessInfo {
  id: string
  label: string
  description: string
  supports_skills: boolean
  supports_mcp: boolean
  supports_keys: boolean
}

export interface AppSettings {
  timezone: string
  docker_host: string
  cell_image: string
  cell_cpus: number
  cell_memory_mb: number
  cell_timeout_seconds: number
  budget: { cpus: number; memory_mb: number }
  mount_roots: MountRoot[]
  codex_image: string
  codex_model: string
  codex_reasoning_effort: 'low' | 'medium' | 'high'
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

export interface Resources {
  ok: boolean
  error: string | null
  hint: string | null
  host_cpus: number | null
  host_memory_mb: number | null
  disk_total_mb: number
  disk_free_mb: number
  recommended: { cpus: number; memory_mb: number } | null
}

export interface CellDefaults {
  image: string
  cpus: number
  memory_mb: number
  timeout_seconds: number
}

export interface SystemStatus {
  scheduler: { running: boolean; active_cells: number; max_cells: number }
  cell_defaults: CellDefaults
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

export type RunStatus = 'running' | 'succeeded' | 'failed' | 'cancelled'
export type NodeRunStatus = 'running' | 'succeeded' | 'failed' | 'skipped' | 'cancelled'

export interface NodeRun {
  id: number
  node_id: string
  kind: NodeKind
  label: string
  seq: number
  status: NodeRunStatus
  started_at: string | null
  finished_at: string | null
  log: string
  result: string
  error: string
  task_id: number | null
  attempt_id: number | null
}

export interface WorkflowSummary {
  id: number
  project_id: number
  name: string
  description: string
  node_count: number
  created_at: string
  updated_at: string
  runs: number
  last_run: { id: number; status: RunStatus; started_at: string } | null
}

export interface WorkflowDetail {
  id: number
  project_id: number
  name: string
  description: string
  graph: Graph
  created_at: string
  updated_at: string
}

export interface WorkflowRunSummary {
  id: number
  status: RunStatus
  trigger: string
  outcome: string
  started_at: string
  finished_at: string | null
  nodes_total: number
  nodes_succeeded: number
  nodes_failed: number
}

export interface WorkflowRunDetail {
  id: number
  project_id: number
  workflow_id: number
  status: RunStatus
  trigger: string
  outcome: string
  started_at: string
  finished_at: string | null
  nodes: NodeRun[]
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
  createProject: (name: string, description = '', cell_profile: ProfileOverrides | null = null) =>
    request<Project>('/projects', send('POST', { name, description, cell_profile })),
  updateProject: (id: number, patch: Partial<Pick<Project, 'name' | 'description' | 'properties' | 'cell_profile'>>) =>
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
  volumes: (projectId: number) => request<Volume[]>(`/projects/${projectId}/volumes`),
  createVolume: (projectId: number, body: VolumeInput) => request<Volume>(`/projects/${projectId}/volumes`, send('POST', body)),
  updateVolume: (id: number, patch: { mode?: 'ro' | 'rw'; exclusive_write?: boolean }) => request<Volume>(`/volumes/${id}`, send('PATCH', patch)),
  deleteVolume: (id: number) => request<void>(`/volumes/${id}`, send('DELETE')),
  skills: (projectId: number) => request<Skill[]>(`/projects/${projectId}/skills`),
  skill: (projectId: number, name: string) => request<SkillDetail>(`/projects/${projectId}/skills/${name}`),
  saveSkill: (projectId: number, name: string, content: string) => request<Skill>(`/projects/${projectId}/skills/${name}`, send('PUT', { content })),
  deleteSkill: (projectId: number, name: string) => request<void>(`/projects/${projectId}/skills/${name}`, send('DELETE')),
  mcpServers: (projectId: number) => request<McpServer[]>(`/projects/${projectId}/mcp-servers`),
  createMcpServer: (projectId: number, body: McpInput) => request<McpServer>(`/projects/${projectId}/mcp-servers`, send('POST', body)),
  updateMcpServer: (id: number, body: McpInput) => request<McpServer>(`/mcp-servers/${id}`, send('PUT', body)),
  deleteMcpServer: (id: number) => request<void>(`/mcp-servers/${id}`, send('DELETE')),
  keys: () => request<KeyInfo[]>('/keys'),
  checkAgent: (projectId: number, body: { harness: string; cell_profile: ProfileOverrides | null; mcp_servers: number[] }) =>
    request<AgentCheck>(`/projects/${projectId}/agents/check`, send('POST', body)),
  harnesses: () => request<HarnessInfo[]>('/harnesses'),
  agents: (projectId: number) => request<Agent[]>(`/projects/${projectId}/agents`),
  createAgent: (projectId: number, body: AgentInput) => request<Agent>(`/projects/${projectId}/agents`, send('POST', body)),
  updateAgent: (id: number, patch: Partial<AgentInput>) => request<Agent>(`/agents/${id}`, send('PATCH', patch)),
  deleteAgent: (id: number) => request<void>(`/agents/${id}`, send('DELETE')),
  resources: () => request<Resources>('/system/resources'),
  docker: (host?: string) =>
    request<DockerStatus>(`/system/docker${host === undefined ? '' : `?host=${encodeURIComponent(host)}`}`),
  settings: () => request<AppSettings>('/settings'),
  saveSettings: (body: AppSettings) => request<AppSettings>('/settings', send('PUT', body)),
  secrets: () => request<Secret[]>('/secrets'),
  createSecret: (name: string, kind: string, value: string) =>
    request<Secret>('/secrets', send('POST', { name, kind, value })),
  deleteSecret: (id: number) => request<void>(`/secrets/${id}`, send('DELETE')),

  workflows: (projectId: number) => request<WorkflowSummary[]>(`/projects/${projectId}/workflows`),
  createWorkflow: (projectId: number, body: { name?: string; graph?: Graph } = {}) => request<WorkflowDetail>(`/projects/${projectId}/workflows`, send('POST', body)),
  workflow: (id: number) => request<WorkflowDetail>(`/workflows/${id}`),
  updateWorkflow: (id: number, patch: { name?: string; description?: string; graph?: Graph }) => request<WorkflowDetail>(`/workflows/${id}`, send('PATCH', patch)),
  deleteWorkflow: (id: number) => request<void>(`/workflows/${id}`, send('DELETE')),
  startWorkflowRun: (workflowId: number) => request<WorkflowRunDetail>(`/workflows/${workflowId}/runs`, send('POST')),
  workflowRuns: (workflowId: number) => request<WorkflowRunSummary[]>(`/workflows/${workflowId}/runs`),
  workflowRun: (id: number) => request<WorkflowRunDetail>(`/workflow-runs/${id}`),
  cancelWorkflowRun: (id: number) => request<WorkflowRunDetail>(`/workflow-runs/${id}/cancel`, send('POST')),

  codex: () => request<CodexStatus>('/codex'),
  codexStartLogin: () => request<CodexLogin>('/codex/login', send('POST')),
  codexCancelLogin: () => request<void>('/codex/login', send('DELETE')),
  codexDisconnect: () => request<void>('/codex', send('DELETE')),
}
