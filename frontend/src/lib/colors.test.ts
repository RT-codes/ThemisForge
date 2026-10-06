import assert from 'node:assert/strict'
import { test } from 'node:test'
import { PALETTE, chipStyle, isHex, normalizeHex } from './colors.ts'

test('the palette is made of valid, distinct colours', () => {
  assert.ok(PALETTE.every((c) => isHex(c.hex)))
  assert.equal(new Set(PALETTE.map((c) => c.hex)).size, PALETTE.length)
})

test('colours can be typed in several ways', () => {
  assert.equal(normalizeHex('#3B82F6'), '#3b82f6')
  assert.equal(normalizeHex(' 3b82f6 '), '#3b82f6')
  assert.equal(normalizeHex('#38f'), '#3388ff')
  for (const bad of ['', 'red', '#12345', '#12345g', 'rgb(1,2,3)']) assert.equal(normalizeHex(bad), null, bad)
})

test('a chip is only coloured by a real colour', () => {
  assert.match(chipStyle('#ef4444')!, /color-mix\(in oklab, #ef4444 20%/)
  assert.equal(chipStyle(undefined), undefined)
  assert.equal(chipStyle('red'), undefined)
})
