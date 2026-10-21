// What the Settings page says about each section when it is folded, and the small rules behind its form. Plain
// functions of the settings (no state), so the wording and the edge cases can be tested.

import type { AppSettings, CellPackage, DockerStatus, UpdateInfo } from './api/settings'
import type { MountRoot } from './api/volumes'

/** "4.0 GB"; nothing for a value the host did not report */
export const gb = (mb: number | null) => (mb === null ? '' : `${(mb / 1024).toFixed(1)} GB`)

/** A copy the form can change without touching the saved one: the nested parts are copied too. */
export const copySettings = (s: AppSettings): AppSettings => ({
  ...s,
  budget: { ...s.budget },
  mcp_auth: { ...s.mcp_auth },
  cell_package: { ...s.cell_package, retry_waits: [...s.cell_package.retry_waits] },
  mount_roots: s.mount_roots.map((r) => ({ ...r })),
})

export function summarizeUpdate(update: UpdateInfo | null): string {
  if (!update) return ''
  if (update.available) return `${update.latest} available`
  if (update.error) return 'Could not check'
  return update.enabled ? `Up to date, ${update.current}` : 'Checking is off'
}

export function summarizeDocker(docker: DockerStatus | null): string {
  if (!docker) return 'Checking...'
  if (docker.ok) return `Connected, Docker ${docker.version}`
  return docker.version ? 'Needs attention' : 'Not reachable'
}

export const summarizeCell = (s: Pick<AppSettings, 'cell_image' | 'cell_cpus' | 'cell_memory_mb'>) =>
  `${s.cell_image} · ${s.cell_cpus} CPU · ${s.cell_memory_mb} MB`

/** `fits`: how many cells of the default size the budget holds (see budget.ts) */
export const summarizeResources = (budget: AppSettings['budget'], fits: number) =>
  `${budget.cpus} CPU · ${gb(budget.memory_mb)} · fits ${fits} ${fits === 1 ? 'cell' : 'cells'}`

export const summarizeRoots = (roots: MountRoot[]) => (roots.length ? `${roots.length} approved` : 'None approved')

export const summarizePackage = (p: CellPackage) =>
  `Rules ${p.rules_enabled ? 'on' : 'off'} · skill ${p.skill_enabled ? 'on' : 'off'} · ${p.retry_waits.length} retr${p.retry_waits.length === 1 ? 'y' : 'ies'}`

export const summarizeAgent = (s: Pick<AppSettings, 'codex_model' | 'codex_reasoning_effort' | 'codex_max_parallel'>) =>
  `${s.codex_model} · ${s.codex_reasoning_effort} effort · ${s.codex_max_parallel} at once`

export const summarizeClaude = (s: Pick<AppSettings, 'claude_model' | 'claude_reasoning_effort'>) =>
  `${s.claude_model} · ${s.claude_reasoning_effort} effort`

export const summarizeKeys = (count: number) => `${count} ${count === 1 ? 'key' : 'keys'}`

/**
 * The approved folders with one more, typed by hand: trailing slashes dropped, new ones read-only until a person allows
 * writing. A blank entry or one that is already there changes nothing (the same list comes back).
 */
export function withMountRoot(roots: MountRoot[], typed: string): MountRoot[] {
  const path = typed.trim().replace(/\/+$/, '')
  if (!path || roots.some((r) => r.path === path)) return roots
  return [...roots, { path, allow_write: false }]
}
