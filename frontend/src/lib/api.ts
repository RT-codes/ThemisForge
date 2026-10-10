import type { Graph, NodeKind } from './workflow'
export interface User {
  id: number
  email: string
  name: string
  is_admin: boolean
}

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

/** the parts of a cell a project, agent or run may change: only the fields that are set override anything */
export interface ProfileOverrides {
  image?: string | null
  cpus?: number | null
  memory_mb?: number | null
  timeout_seconds?: number | null
}

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

export type Harness = '' | 'codex' | 'workflow'

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
  workflow_id: number | null
  agent_id: number | null
  /** how many times in a row automation moved or made this task; a person acting on it starts again at 0 */
  hops: number
  /** this task's own automation guard; null follows the project's */
  cooldown_seconds: number | null
  max_hops: number | null
  created_at: string
  updated_at: string
  last_attempt_status: AttemptStatus | null
  /** the workflow run this task started that is still going, if any */
  workflow_run: { run_id: number; workflow_id: number; workflow_name: string; step: string } | null
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
  workflow_id?: number | null
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
  kind: 'managed' | 'host' | 'config' // config: the project's own agents, skills and tools, never mounted
  host_path: string
  mode: 'ro' | 'rw'
  exclusive_write: boolean
  created_at: string
  is_default: boolean
  problem: string | null
  can_write: boolean
}

export interface FileEntry {
  name: string
  is_dir: boolean
  size: number
  modified: string
}

export interface FolderListing {
  path: string
  entries: FileEntry[]
  writable: boolean // the folder allows changes
  runs: { task_id: number; title: string }[] // the runs using it: while there are any, it is locked
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
  connections: string[] // providers (github, ...) it may use through the project's connections
  path: string // the agent's file in the project's config folder
  config_error: string // why that file cannot be used right now, "" when it is fine
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
  description: string
  kind: 'stdio' | 'http'
  command: string
  args: string[]
  url: string
  env: Record<string, string>
  secret_env: Record<string, number>
  bearer_secret_id: number | null
  path: string // the tool's file in the project's config folder
  config_error: string
  last_test: McpTest | null
  created_at: string
}

/** the outcome of trying a tool: a web tool is connected to, a command is looked up in the image */
export interface McpTest {
  ok: boolean
  message: string
  tools: string[]
  at: string
}

export type McpInput = Omit<McpServer, 'id' | 'project_id' | 'created_at' | 'path' | 'config_error' | 'last_test'>

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

export type AgentInput = Omit<Agent, 'id' | 'project_id' | 'created_at' | 'updated_at' | 'path' | 'config_error'>

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
  github_client_id: string // the OAuth App that "Sign in with GitHub" uses, empty until an administrator adds it
  check_for_updates: boolean // ask GitHub once a day whether a newer release exists
  update_channel: 'stable' | 'beta'
  keep_workspaces_days: number
  start_cooldown_seconds: number
  max_automation_hops: number
}

export interface DockerStatus {
  ok: boolean
  installed: boolean
  host: string
  version: string | null
  os: string | null
  os_type: string | null // linux or windows: the kind of containers the engine runs
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
  version: string
  platform: 'windows' | 'linux' | 'mac' // what a folder path looks like on the server
  cells_ready: boolean // false while Docker cannot run cells: tasks wait instead of failing
  problems: Problem[] // what the checks found; only filled in for administrators
  update: UpdateInfo | null // only for administrators
}

/** is there a newer Themis: what the server found the last time it looked (only administrators get it) */
export interface UpdateInfo {
  enabled: boolean
  current: string
  latest: string // "" until a check has worked
  available: boolean
  url: string // the release notes
  checked_at: string // "" if never
  error: string
  channel: 'stable' | 'beta'
  kind: 'release' | 'checkout'
}

export interface Problem {
  id: string
  level: 'ok' | 'warn' | 'fail'
  message: string
  hint: string
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

// ----- connections to outside services (see backend/app/connections.py) -----

export interface ConnectionMethod {
  id: 'token' | 'oauth'
  available: boolean
  reason: string // why it is not available, in words for the person
}

export interface ConnectionField {
  key: string
  label: string
  placeholder: string
  help: string
}

export interface ConnectionProvider {
  id: string
  name: string
  category: string // "ai" | "service"
  description: string
  icon: string // a Lucide icon name
  token_help: string
  methods: ConnectionMethod[]
  config_fields: ConnectionField[] // what a project sets on its connection
}

export interface Connection {
  id: number
  provider: string
  method: 'token' | 'oauth'
  account: string
  settings: Record<string, unknown>
  connected_at: string
  checked_at: string | null
  needs_reconnect: boolean // stored, but unreadable (the secret key changed)
}

export interface ConnectionsList {
  secret_key_secure: boolean
  providers: ConnectionProvider[]
  connections: Connection[]
}

export interface ConnectionLogin {
  status: 'starting' | 'waiting' | 'connected' | 'failed' | 'cancelled'
  verification_url: string
  code: string
  expires_at: string | null
  error: string
}

export interface ProjectConnection {
  provider: string
  connection_id: number
  account: string
  config: Record<string, string>
}

export interface CodexLogin {
  status: 'starting' | 'waiting' | 'connected' | 'failed' | 'cancelled'
  verification_url: string
  code: string
  expires_at: string | null
  error: string
}

export interface CodexStatus {
  can_sign_in: boolean // false when this server cannot run the sign in (Docker is missing, or in development no Codex CLI)
  sign_in_problem: string // why, in words for the person
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
  /** the statuses whose tasks start this workflow by themselves; empty for one that is only run by hand */
  /** what starts it by itself: a status and where ("" anywhere, "w:<id>" a workspace, "b:<id>" a board) */
  watches: { status: TaskStatus; where: string }[]
}

export interface TaskWorkflowRunSummary {
  id: number
  workflow_id: number
  workflow_name: string
  status: RunStatus
  outcome: string
  started_at: string
  finished_at: string | null
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

/** the error for a response that was not ok, with the server's own explanation */
async function failure(res: Response): Promise<ApiError> {
  let detail = res.statusText
  try {
    const body = await res.json()
    if (typeof body.detail === 'string') detail = body.detail
    else if (Array.isArray(body.detail)) detail = body.detail[0]?.msg?.replace(/^Value error, /, '') ?? detail
  } catch {
    // non-JSON error body
  }
  return new ApiError(res.status, detail)
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`/api${path}`, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...init?.headers },
  })
  if (!res.ok) throw await failure(res)
  return res.status === 204 ? (undefined as T) : res.json()
}

const send = (method: string, body?: unknown): RequestInit => ({
  method,
  body: body === undefined ? undefined : JSON.stringify(body),
})

/** where a file can be shown or downloaded from; the browser fetches it with the session cookie */
// `version` (the file's modified time) is ignored by the server; it only makes the browser fetch the file again after it changed
const fileUrl = (id: number, path: string, download = false, version = '') =>
  `/api/volumes/${id}/file?path=${encodeURIComponent(path)}${download ? '&download=true' : ''}${version ? `&v=${encodeURIComponent(version)}` : ''}`

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
  tasks: (projectId: number) => request<Task[]>(`/projects/${projectId}/tasks`),
  createTask: (projectId: number, body: TaskInput) => request<Task>(`/projects/${projectId}/tasks`, send('POST', body)),
  updateTask: (id: number, patch: TaskPatch) => request<Task>(`/tasks/${id}`, send('PATCH', patch)),
  /** the same task continues on another board (and status) */
  moveTask: (id: number, body: { board_id: number; status?: TaskStatus; position?: number }) =>
    request<Task>(`/tasks/${id}/move`, send('POST', body)),
  /** a new task on a board, linked to this one; this one stays where it is */
  spawnTask: (id: number, body: { board_id: number; title?: string; description?: string; status?: TaskStatus }) =>
    request<Task>(`/tasks/${id}/spawn`, send('POST', body)),
  /** `query` comes from historyQuery() */
  projectHistory: (projectId: number, query: string) => request<ProjectEvent[]>(`/projects/${projectId}/history?${query}`),
  deleteTask: (id: number) => request<void>(`/tasks/${id}`, send('DELETE')),
  runTask: (id: number) => request<Task>(`/tasks/${id}/run`, send('POST')),
  cancelTask: (id: number) => request<Task>(`/tasks/${id}/cancel`, send('POST')),
  attempts: (taskId: number) => request<Attempt[]>(`/tasks/${taskId}/attempts`),
  attempt: (id: number) => request<AttemptDetail>(`/attempts/${id}`),
  schedule: (projectId: number, hours: number) =>
    request<ScheduledRun[]>(`/projects/${projectId}/schedule?hours=${hours}`),

  systemStatus: () => request<SystemStatus>('/system/status'),
  checkForUpdates: () => request<UpdateInfo>('/system/update-check', send('POST')),
  /** The shared folders; the Files page also asks for the config folder, which pickers must never offer. */
  volumes: (projectId: number, includeConfig = false) => request<Volume[]>(`/projects/${projectId}/volumes${includeConfig ? '?include_config=true' : ''}`),
  configFolder: (projectId: number) => request<Volume>(`/projects/${projectId}/config`),
  createVolume: (projectId: number, body: VolumeInput) => request<Volume>(`/projects/${projectId}/volumes`, send('POST', body)),
  updateVolume: (id: number, patch: { name?: string; mode?: 'ro' | 'rw'; exclusive_write?: boolean }) => request<Volume>(`/volumes/${id}`, send('PATCH', patch)),
  deleteVolume: (id: number) => request<void>(`/volumes/${id}`, send('DELETE')),
  /** A folder's contents. Pass the `etag` of the last answer: if nothing changed since, the server sends no body and
   * this returns null, so watching a folder is cheap. */
  listFiles: async (id: number, path: string, etag = ''): Promise<{ listing: FolderListing; etag: string } | null> => {
    const res = await fetch(`/api/volumes/${id}/files?path=${encodeURIComponent(path)}`, {
      headers: etag ? { 'If-None-Match': etag } : {},
      cache: 'no-store', // the conditional request is ours; the browser's own cache must not answer instead
    })
    if (res.status === 304) return null
    if (!res.ok) throw await failure(res)
    return { listing: await res.json(), etag: res.headers.get('ETag') ?? '' }
  },
  fileUrl,
  readFileText: async (id: number, path: string) => {
    const res = await fetch(fileUrl(id, path), { cache: 'no-store' }) // a file that was just saved must not come from the cache
    if (!res.ok) throw new ApiError(res.status, res.statusText)
    return res.text()
  },
  /** `base`: the modified time the file had when it was opened; the save is refused (412) if it changed since */
  uploadFile: (id: number, path: string, file: File, overwrite = false, base = '') =>
    request<void>(`/volumes/${id}/file?path=${encodeURIComponent(path)}&overwrite=${overwrite}${base ? `&base=${encodeURIComponent(base)}` : ''}`, {
      method: 'PUT',
      body: file,
      headers: { 'Content-Type': 'application/octet-stream' },
    }),
  createFolder: (id: number, path: string) => request<void>(`/volumes/${id}/folder`, send('POST', { path })),
  moveFile: (id: number, source: string, destination: string) => request<void>(`/volumes/${id}/move`, send('POST', { source, destination })),
  deleteFile: (id: number, path: string) => request<void>(`/volumes/${id}/file?path=${encodeURIComponent(path)}`, send('DELETE')),
  skills: (projectId: number) => request<Skill[]>(`/projects/${projectId}/skills`),
  skill: (projectId: number, name: string) => request<SkillDetail>(`/projects/${projectId}/skills/${name}`),
  saveSkill: (projectId: number, name: string, content: string) => request<Skill>(`/projects/${projectId}/skills/${name}`, send('PUT', { content })),
  deleteSkill: (projectId: number, name: string) => request<void>(`/projects/${projectId}/skills/${name}`, send('DELETE')),
  mcpServers: (projectId: number) => request<McpServer[]>(`/projects/${projectId}/mcp-servers`),
  createMcpServer: (projectId: number, body: McpInput) => request<McpServer>(`/projects/${projectId}/mcp-servers`, send('POST', body)),
  updateMcpServer: (id: number, body: McpInput) => request<McpServer>(`/mcp-servers/${id}`, send('PUT', body)),
  deleteMcpServer: (id: number) => request<void>(`/mcp-servers/${id}`, send('DELETE')),
  testMcpServer: (id: number) => request<McpTest>(`/mcp-servers/${id}/test`, send('POST')),
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
  taskWorkflowRuns: (taskId: number) => request<TaskWorkflowRunSummary[]>(`/tasks/${taskId}/workflow-runs`),
  workflowRuns: (workflowId: number) => request<WorkflowRunSummary[]>(`/workflows/${workflowId}/runs`),
  workflowRun: (id: number) => request<WorkflowRunDetail>(`/workflow-runs/${id}`),
  cancelWorkflowRun: (id: number) => request<WorkflowRunDetail>(`/workflow-runs/${id}/cancel`, send('POST')),

  connections: () => request<ConnectionsList>('/connections'),
  connectWithToken: (provider: string, token: string) => request<Connection>('/connections', send('POST', { provider, token })),
  testConnection: (id: number) => request<Connection>(`/connections/${id}/test`, send('POST')),
  disconnect: (id: number) => request<void>(`/connections/${id}`, send('DELETE')),
  startConnectionLogin: (provider: string) => request<ConnectionLogin>(`/connection-logins/${provider}`, send('POST')),
  connectionLogin: (provider: string) => request<ConnectionLogin | null>(`/connection-logins/${provider}`),
  cancelConnectionLogin: (provider: string) => request<void>(`/connection-logins/${provider}`, send('DELETE')),
  projectConnections: (projectId: number) => request<ProjectConnection[]>(`/projects/${projectId}/connections`),
  useConnection: (projectId: number, provider: string, connectionId: number, config: Record<string, string>) =>
    request<ProjectConnection>(`/projects/${projectId}/connections/${provider}`, send('PUT', { connection_id: connectionId, config })),
  stopUsingConnection: (projectId: number, provider: string) => request<void>(`/projects/${projectId}/connections/${provider}`, send('DELETE')),
  codex: () => request<CodexStatus>('/codex'),
  codexStartLogin: () => request<CodexLogin>('/codex/login', send('POST')),
  codexCancelLogin: () => request<void>('/codex/login', send('DELETE')),
  codexDisconnect: () => request<void>('/codex', send('DELETE')),
}
