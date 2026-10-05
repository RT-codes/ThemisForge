import assert from 'node:assert/strict'
import { test } from 'node:test'
import { classify } from './loglines.ts'

const kinds = (text: string) => classify(text.split('\n')).map((r) => r.kind)

test('commands, their output, thinking and notes get their own look', () => {
  assert.deepEqual(kinds('[codex] session 1\n\n[thinking] hmm\nmore thought\n\n$ ls\na.txt\n[exit 2]\n\nDone.'), [
    'note', 'plain', 'thinking', 'thinking', 'plain', 'command', 'output', 'error', 'plain', 'plain',
  ])
})

test('a blank line ends a block', () => assert.deepEqual(kinds('$ ls\nfile\n\nplain text'), ['command', 'output', 'plain', 'plain']))
test('failures stand out', () => assert.deepEqual(kinds('[Cell error] boom\n[Cancelled]\n[codex] error: x'), ['error', 'error', 'error']))
test('a plain log stays plain', () => assert.deepEqual(kinds('hello\nworld'), ['plain', 'plain']))
