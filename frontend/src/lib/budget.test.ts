import assert from 'node:assert/strict'
import { test } from 'node:test'
import { cellsThatFit } from './budget.ts'

const cell = { cpus: 1, memory_mb: 1024 }

test('the tighter of CPUs and memory decides how many cells fit', () => {
  assert.equal(cellsThatFit({ cpus: 6, memory_mb: 8192 }, cell), 6)
  assert.equal(cellsThatFit({ cpus: 6, memory_mb: 3000 }, cell), 2)
  assert.equal(cellsThatFit({ cpus: 0.5, memory_mb: 4096 }, cell), 0)
})

test('fractions of a CPU add up without float surprises', () => {
  assert.equal(cellsThatFit({ cpus: 0.3, memory_mb: 4096 }, { cpus: 0.1, memory_mb: 64 }), 3)
})

test('a cell size that is not filled in yet fits nowhere', () => {
  assert.equal(cellsThatFit({ cpus: 4, memory_mb: 4096 }, { cpus: 0, memory_mb: 1024 }), 0)
  assert.equal(cellsThatFit({ cpus: 4, memory_mb: 4096 }, { cpus: Number.NaN, memory_mb: 1024 }), 0)
})
