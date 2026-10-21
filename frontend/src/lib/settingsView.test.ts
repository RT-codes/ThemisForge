import assert from 'node:assert/strict'
import { test } from 'node:test'
import type { AppSettings, CellPackage, DockerStatus, UpdateInfo } from './api/settings.ts'
import { copySettings, gb, summarizeAgent, summarizeCell, summarizeDocker, summarizeKeys, summarizePackage, summarizeResources, summarizeRoots, summarizeUpdate, withMountRoot } from './settingsView.ts'

const update = (over: Partial<UpdateInfo> = {}): UpdateInfo =>
  ({ enabled: true, current: '0.3.0', latest: '', available: false, url: '', checked_at: '', error: '', channel: 'stable', kind: 'release', ...over }) as UpdateInfo
const docker = (over: Partial<DockerStatus> = {}): DockerStatus =>
  ({ ok: true, installed: true, host: 'local socket', version: '27.1', os: null, os_type: null, cpus: null, memory_mb: null, error: null, hint: null, ...over }) as DockerStatus

test('memory reads in gigabytes, and as nothing when the host did not say', () => {
  assert.equal(gb(4096), '4.0 GB')
  assert.equal(gb(1536), '1.5 GB')
  assert.equal(gb(null), '')
})

test('the update line says what the person needs to know first', () => {
  assert.equal(summarizeUpdate(null), '')
  assert.equal(summarizeUpdate(update({ available: true, latest: '0.4.0' })), '0.4.0 available')
  assert.equal(summarizeUpdate(update({ error: 'offline' })), 'Could not check')
  assert.equal(summarizeUpdate(update()), 'Up to date, 0.3.0')
  assert.equal(summarizeUpdate(update({ enabled: false })), 'Checking is off')
  // a newer version wins over a failed check that came after it
  assert.equal(summarizeUpdate(update({ available: true, latest: '0.4.0', error: 'offline' })), '0.4.0 available')
})

test('the Docker line tells connected, needing attention and unreachable apart', () => {
  assert.equal(summarizeDocker(null), 'Checking...')
  assert.equal(summarizeDocker(docker()), 'Connected, Docker 27.1')
  assert.equal(summarizeDocker(docker({ ok: false })), 'Needs attention') // the engine answered but something is wrong
  assert.equal(summarizeDocker(docker({ ok: false, version: null })), 'Not reachable')
})

test('the resource line counts cells in the singular and the plural', () => {
  const budget = { cpus: 4, memory_mb: 8192 }
  assert.equal(summarizeResources(budget, 1), '4 CPU · 8.0 GB · fits 1 cell')
  assert.equal(summarizeResources(budget, 3), '4 CPU · 8.0 GB · fits 3 cells')
  assert.equal(summarizeResources(budget, 0), '4 CPU · 8.0 GB · fits 0 cells')
})

test('the cell, agent and package lines read out the settings they stand for', () => {
  assert.equal(summarizeCell({ cell_image: 'themis/cell', cell_cpus: 2, cell_memory_mb: 2048 }), 'themis/cell · 2 CPU · 2048 MB')
  assert.equal(summarizeAgent({ codex_model: 'gpt-x', codex_reasoning_effort: 'high', codex_max_parallel: 2 }), 'gpt-x · high effort · 2 at once')
  const pkg = (over: Partial<CellPackage>) => ({ rules_enabled: true, skill_enabled: false, retry_waits: [], ...over }) as CellPackage
  assert.equal(summarizePackage(pkg({})), 'Rules on · skill off · 0 retries')
  assert.equal(summarizePackage(pkg({ retry_waits: [5] })), 'Rules on · skill off · 1 retry')
  assert.equal(summarizePackage(pkg({ rules_enabled: false, skill_enabled: true, retry_waits: [5, 30] })), 'Rules off · skill on · 2 retries')
})

test('the folder and key counts agree with their number', () => {
  assert.equal(summarizeRoots([]), 'None approved')
  assert.equal(summarizeRoots([{ path: '/home/me', allow_write: false }]), '1 approved')
  assert.equal(summarizeKeys(0), '0 keys')
  assert.equal(summarizeKeys(1), '1 key')
  assert.equal(summarizeKeys(2), '2 keys')
})

test('an approved folder typed by hand is tidied and starts read-only', () => {
  const roots = [{ path: '/home/me/notes', allow_write: true }]
  assert.deepEqual(withMountRoot(roots, '  /srv/data//  '), [...roots, { path: '/srv/data', allow_write: false }])
  assert.deepEqual(roots, [{ path: '/home/me/notes', allow_write: true }]) // the list it was given is not changed
})

test('a blank or repeated folder adds nothing, and the same list comes back', () => {
  const roots = [{ path: '/home/me/notes', allow_write: true }]
  assert.equal(withMountRoot(roots, ''), roots)
  assert.equal(withMountRoot(roots, '   '), roots)
  assert.equal(withMountRoot(roots, '///'), roots) // nothing is left once the slashes go
  assert.equal(withMountRoot(roots, '/home/me/notes/'), roots) // already approved, with or without the slash
})

test('the form copy shares nothing with the saved settings', () => {
  const saved = {
    budget: { cpus: 2, memory_mb: 2048 },
    mcp_auth: { renew_days: 7 },
    cell_package: { rules_enabled: true, skill_enabled: true, retry_waits: [5] },
    mount_roots: [{ path: '/a', allow_write: false }],
    timezone: 'UTC',
  } as unknown as AppSettings
  const form = copySettings(saved)
  form.budget.cpus = 8
  form.cell_package.retry_waits.push(60)
  form.mount_roots[0].allow_write = true
  form.mcp_auth = { ...form.mcp_auth }
  assert.equal(saved.budget.cpus, 2)
  assert.deepEqual(saved.cell_package.retry_waits, [5])
  assert.equal(saved.mount_roots[0].allow_write, false)
  assert.equal(form.timezone, 'UTC')
})
