import assert from 'node:assert/strict'
import { test } from 'node:test'
import { describeCell, effectiveCell } from './cell.ts'

const defaults = { cpus: 1, memory_mb: 1024, timeout_seconds: 3600, image: 'alpine:3' }

test('with nothing overridden the defaults are what is used', () => {
  assert.deepEqual(effectiveCell(defaults), defaults)
  assert.deepEqual(effectiveCell(defaults, null, undefined, {}), defaults)
})

test('each layer changes only what it sets, and later layers win', () => {
  const project = { cpus: 2, memory_mb: 2048 }
  const agent = { memory_mb: 4096, timeout_seconds: 60 }
  assert.deepEqual(effectiveCell(defaults, project, agent), { cpus: 2, memory_mb: 4096, timeout_seconds: 60, image: 'alpine:3' })
})

test('empty or missing fields do not override anything', () => {
  assert.deepEqual(effectiveCell(defaults, { cpus: null, memory_mb: undefined, image: '' }), defaults)
})

test('a cell is described in one short line', () => {
  assert.equal(describeCell(defaults), '1 CPU · 1024 MB · 1 h')
  assert.equal(describeCell({ cpus: 2.5, memory_mb: 512, timeout_seconds: 90 }), '2.5 CPUs · 512 MB · 90 s')
  assert.equal(describeCell({ cpus: 2, memory_mb: 2048, timeout_seconds: 600 }), '2 CPUs · 2048 MB · 10 min')
})
