import assert from 'node:assert/strict'
import { test } from 'node:test'
import { nextLogMatch, searchLog } from './logSearch.ts'

test('empty queries and logs have no matches and preserve text', () => {
  assert.deepEqual(searchLog(['', 'hello'], ''), {
    rows: [[{ text: '', match: null }], [{ text: 'hello', match: null }]], count: 0,
  })
  assert.deepEqual(searchLog([], 'error'), { rows: [], count: 0 })
  assert.equal(searchLog(['hello'], 'missing').count, 0)
})

test('matches are case insensitive, non-overlapping and numbered across lines', () => {
  assert.deepEqual(searchLog(['Error ERROR', 'error!'], 'error'), {
    rows: [
      [{ text: 'Error', match: 0 }, { text: ' ', match: null }, { text: 'ERROR', match: 1 }],
      [{ text: 'error', match: 2 }, { text: '!', match: null }],
    ], count: 3,
  })
  assert.equal(searchLog(['aaaa'], 'aa').count, 2)
})

test('punctuation and whitespace are literal, and HTML remains plain text', () => {
  const line = '<script>[a].*+?^${}()|\\</script>  '
  for (const query of ['[a]', '.*+?^${}()|\\', '<script>', '  ']) {
    const result = searchLog([line], query)
    assert.equal(result.count, 1)
    assert.equal(result.rows[0].map((part) => part.text).join(''), line)
    assert.equal(result.rows[0].find((part) => part.match === 0)?.text, query)
  }
})

test('Unicode matching keeps offsets in the original text', () => {
  const result = searchLog(['İ ERROR 😀 error'], 'error')
  assert.deepEqual(result.rows[0].map((part) => part.text), ['İ ', 'ERROR', ' 😀 ', 'error'])
})

test('appended output adds matches without renumbering existing ones', () => {
  const before = searchLog(['Error one'], 'error')
  const after = searchLog(['Error one', 'error two ERROR'], 'error')
  assert.deepEqual(after.rows[0], before.rows[0])
  assert.equal(after.count, 3)
})

test('navigation wraps in both directions and handles disappearing matches', () => {
  assert.equal(nextLogMatch(2, 3, 1), 0)
  assert.equal(nextLogMatch(0, 3, -1), 2)
  assert.equal(nextLogMatch(0, 1, 1), 0)
  assert.equal(nextLogMatch(2, 0, -1), 0)
})
