import assert from 'node:assert/strict'
import { test } from 'node:test'
import { commandLine, formatCount, formatEnv, hueOf, initials, isVariableName, missingInputs, parseEnv, signInOutcome, signInSummary, splitInputs, startingValues, withoutSignInOutcome } from './tools.ts'

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

const input = (id: string, label: string, required: boolean, def = '') => ({ id, label, required, default: def })

test('a registry tool starts with the defaults it has', () => {
  assert.deepEqual(startingValues([input('a', 'A', true), input('b', 'B', false, 'x')]), { b: 'x' })
})

test('required answers that are empty are listed, unless the input has a default', () => {
  const inputs = [input('a', 'Token', true), input('b', 'Region', true, 'eu'), input('c', 'Note', false)]
  assert.deepEqual(missingInputs(inputs, {}), ['Token'])
  assert.deepEqual(missingInputs(inputs, { a: '  ' }), ['Token'])
  assert.deepEqual(missingInputs(inputs, { a: '7' }), [])
})

test('inputs split into the ones that must be filled in and the ones that need not', () => {
  const { needed, optional } = splitInputs([input('a', 'A', true), input('b', 'B', false), input('c', 'C', true)])
  assert.deepEqual(needed.map((i) => i.id), ['a', 'c'])
  assert.deepEqual(optional.map((i) => i.id), ['b'])
})

test('download counts are short', () => {
  assert.equal(formatCount(0), '0')
  assert.equal(formatCount(999), '999')
  assert.equal(formatCount(1200), '1.2K')
  assert.equal(formatCount(15000), '15K')
  assert.equal(formatCount(30_500_978), '31M')
  assert.equal(formatCount(2_000_000), '2M')
  assert.equal(formatCount(1_250_000_000), '1.3B')
})

test('a tool without an icon gets the first letters of its name', () => {
  assert.equal(initials('GitHub MCP Server'), 'GM')
  assert.equal(initials('notion'), 'NO')
  assert.equal(initials('slack-mcp'), 'SM')
  assert.equal(initials('  '), '?')
})

test('the same name always gets the same colour', () => {
  assert.equal(hueOf('io.github.a/x'), hueOf('io.github.a/x'))
  assert.ok(hueOf('anything') >= 0 && hueOf('anything') < 360)
  assert.notEqual(hueOf('alpha'), hueOf('beta'))
})

const sign = (state: 'signed_in' | 'needs_sign_in' | 'not_signed_in', account = '') => ({ state, method: 'Sign in', login_id: 1, account, error: '', expires_at: null })

test('a tool that signs in shows where it stands, and one that does not shows nothing', () => {
  assert.equal(signInSummary(null), null)
  assert.deepEqual(signInSummary(sign('signed_in', 'Acme')), { label: 'Signed in as Acme', tone: 'ok', action: 'Sign in again' })
  assert.equal(signInSummary(sign('signed_in'))?.label, 'Signed in')
  assert.deepEqual(signInSummary(sign('not_signed_in')), { label: 'Not signed in', tone: 'warn', action: 'Sign in' })
  assert.deepEqual(signInSummary(sign('needs_sign_in')), { label: 'Needs a new sign in', tone: 'warn', action: 'Sign in again' })
})

test('the outcome of a sign in is read from the address and then removed from it', () => {
  assert.deepEqual(signInOutcome('?mcp_sign_in=ok&message=Acme'), { ok: true, message: 'Acme' })
  assert.deepEqual(signInOutcome('?mcp_sign_in=error&message=The%20sign%20in%20was%20declined.'), { ok: false, message: 'The sign in was declined.' })
  assert.equal(signInOutcome('?tab=tools'), null)
  assert.equal(signInOutcome('?mcp_sign_in=maybe'), null)
  assert.equal(withoutSignInOutcome('?mcp_sign_in=ok&message=Acme&tab=tools'), '?tab=tools')
  assert.equal(withoutSignInOutcome('?mcp_sign_in=ok&message=Acme'), '')
})
