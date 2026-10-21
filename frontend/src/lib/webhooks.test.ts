import assert from 'node:assert/strict'
import { test } from 'node:test'
import { addressOf, toRows, toRules } from './webhooks.ts'

test('a rule is edited as a path and a line of values, and goes back the same', () => {
  const rules = [{ path: 'action', equals: ['opened', 'reopened'] }, { path: 'issue.title', equals: [] }]
  assert.deepEqual(toRows(rules), [
    { path: 'action', values: 'opened, reopened' },
    { path: 'issue.title', values: '' },
  ])
  assert.deepEqual(toRules(toRows(rules)), rules)
})

test('rows that were added and never filled in are dropped, and values are trimmed', () => {
  assert.deepEqual(toRules([{ path: '  ', values: 'x' }, { path: ' action ', values: ' opened ,, closed ' }]), [
    { path: 'action', equals: ['opened', 'closed'] },
  ])
})

test('the address is the path on the address the page was opened from', () => {
  assert.equal(addressOf('/api/hooks/abc', 'https://themis.example.com'), 'https://themis.example.com/api/hooks/abc')
  assert.equal(addressOf('/api/hooks/abc', 'http://localhost:5173/'), 'http://localhost:5173/api/hooks/abc')
})
