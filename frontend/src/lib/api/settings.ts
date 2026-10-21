// Settings, the system's state, cell sizes and stored secrets.

import { request, send } from './core'
import type { MountRoot } from './volumes'

/** the parts of a cell a project, agent or run may change: only the fields that are set override anything */
export interface ProfileOverrides {
  image?: string | null
  cpus?: number | null
  memory_mb?: number | null
  timeout_seconds?: number | null
}

/** the numbers signing in to tool servers depends on (backend/app/app_settings.py McpAuthPolicy) */
export interface McpAuthPolicy {
  refresh_margin_seconds: number // a token must still last this long, on top of the run's time limit, or it is renewed
  default_token_seconds: number // a token's assumed life when the service does not say
  keepalive_days: number // renew a sign in nobody used for this long; 0 = off
  sign_in_minutes: number // how long a started sign in waits for the person
  request_timeout_seconds: number
  public_url: string // where a browser reaches Themis, when that differs from the address the page was opened on
  client_name: string // shown on the service's consent screen
}

/** What Themis puts into every Codex cell by itself; empty text means the built-in one (see app/cell_package.py) */
export interface CellPackage {
  rules_enabled: boolean
  rules: string
  skill_enabled: boolean
  skill: string
  /** seconds to wait before each new try when the model provider could not serve a run; empty = never retry */
  retry_waits: number[]
}

export interface CellPackageDefaults {
  rules: string
  skill: string
}

// what every Codex agent is given right now (edits and switches in Settings applied), readable by any user
export interface CellPackageInUse {
  skill_name: string
  skill_enabled: boolean
  skill: string
  description: string
  rules_enabled: boolean
  rules: string
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
  codex_max_parallel: number // Codex runs of one person that may use their login at the same time
  claude_image: string
  claude_model: string
  claude_reasoning_effort: 'low' | 'medium' | 'high'
  cell_package: CellPackage
  github_client_id: string // the OAuth App that "Sign in with GitHub" uses, empty until an administrator adds it
  mcp_auth: McpAuthPolicy
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

export interface Secret {
  id: number
  name: string
  kind: string
  hint: string
  created_at: string
}

export const settingsApi = {
  systemStatus: () => request<SystemStatus>('/system/status'),
  checkForUpdates: () => request<UpdateInfo>('/system/update-check', send('POST')),
  resources: () => request<Resources>('/system/resources'),
  docker: (host?: string) =>
    request<DockerStatus>(`/system/docker${host === undefined ? '' : `?host=${encodeURIComponent(host)}`}`),
  settings: () => request<AppSettings>('/settings'),
  cellPackage: () => request<CellPackageInUse>('/cell-package'),
  cellPackageDefaults: () => request<CellPackageDefaults>('/settings/cell-package'),
  saveSettings: (body: AppSettings) => request<AppSettings>('/settings', send('PUT', body)),
  secrets: () => request<Secret[]>('/secrets'),
  createSecret: (name: string, kind: string, value: string) =>
    request<Secret>('/secrets', send('POST', { name, kind, value })),
  deleteSecret: (id: number) => request<void>(`/secrets/${id}`, send('DELETE')),
}
