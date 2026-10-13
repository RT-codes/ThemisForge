import assert from 'node:assert/strict'
import { test } from 'node:test'
import { approxTokens, formatWaits, parseWaits, shownText, storedText } from './cellPackage.ts'

test('an unedited text shows the built-in one and stores nothing', () => {
  assert.equal(shownText('', 'built in'), 'built in')
  assert.equal(shownText('  ', 'built in'), 'built in')
  assert.equal(shownText('mine', 'built in'), 'mine')
  assert.equal(storedText('built in\n', 'built in'), '')
  assert.equal(storedText('mine', 'built in'), 'mine')
})

test('a size in tokens is rounded up', () => {
  assert.equal(approxTokens(''), 0)
  assert.equal(approxTokens('abcde'), 2)
})

test('waits are a list of whole seconds', () => {
  assert.deepEqual(parseWaits('30, 90 180'), [30, 90, 180])
  assert.deepEqual(parseWaits(''), [])
  assert.equal(parseWaits('30, soon'), null)
  assert.equal(parseWaits('-5'), null)
  assert.equal(parseWaits('1.5'), null)
  assert.equal(parseWaits('4000'), null)
  assert.equal(parseWaits('1 2 3 4 5 6 7 8 9 10 11'), null)
  assert.equal(formatWaits([30, 90]), '30, 90')
})
