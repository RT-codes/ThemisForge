import assert from 'node:assert/strict'
import { test } from 'node:test'
import { commandLine, formatEnv, isVariableName, parseEnv } from './tools.ts'

test('a command and its arguments read back as one line', () => {
  assert.equal(commandLine('npx', ['-y', '@scope/server', '/workspace']), 'npx -y @scope/server /workspace')
  assert.equal(commandLine('node', ['my server.js', 'say "hi"']), 'node "my server.js" "say \\"hi\\""')
  assert.equal(commandLine('uvx', []), 'uvx')
})

test('variables are one KEY=value per line, and values may hold an equals sign', () => {
  assert.deepEqual(parseEnv('A=1\n B = two \nURL=https://x.io/?a=b\n\nnoequals\n=novalue'), { A: '1', B: 'two', URL: 'https://x.io/?a=b' })
  assert.equal(formatEnv({ A: '1', B: 'two' }), 'A=1\nB=two')
  assert.deepEqual(parseEnv(formatEnv({ A: '1', B: 'x=y' })), { A: '1', B: 'x=y' })
})

test('variable names follow the server rule', () => {
  for (const ok of ['A', 'API_KEY', '_x', 'a1']) assert.ok(isVariableName(ok), ok)
  for (const bad of ['', '1A', 'A-B', 'A B']) assert.ok(!isVariableName(bad), bad)
})
