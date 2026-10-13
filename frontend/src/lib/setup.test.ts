import assert from 'node:assert/strict'
import { test } from 'node:test'
import { setupIssues } from './setup.ts'

const names: Record<string, string> = { github: 'GitHub' }
const base = { projectId: 4, agents: [], tools: [], connected: [], providerName: (p: string) => names[p] ?? p }
const agent = (id: number, name: string, connections: string[] = [], config_error = '') => ({ id, name, connections, config_error })
const tool = (id: number, name: string, state: 'signed_in' | 'needs_sign_in' | 'not_signed_in' | null, config_error = '') => ({
  id,
  name,
  config_error,
  sign_in: state ? { state, method: '', login_id: null, account: '', error: '', expires_at: null } : null,
})

test('a project with nothing wrong has no issues', () => {
  assert.deepEqual(setupIssues(base), [])
  assert.deepEqual(setupIssues({ ...base, agents: [agent(1, 'Ada', ['github'])], connected: ['github'], tools: [tool(1, 'notion', 'signed_in')] }), [])
})

test('an agent whose file has a problem links to that agent', () => {
  const [issue] = setupIssues({ ...base, agents: [agent(7, 'Ada', [], 'bad yaml')] })
  assert.deepEqual(issue, { id: 'agent-7', text: 'Agent Ada has a problem: bad yaml', href: '/projects/4/agents/7' })
})

test('a connection that agents want and the project lacks is one issue naming them', () => {
  const issues = setupIssues({ ...base, agents: [agent(1, 'Ada', ['github']), agent(2, 'Bob', ['github']), agent(3, 'Cy', ['github']), agent(4, 'Di')] })
  assert.equal(issues.length, 1)
  assert.equal(issues[0].text, 'Ada, Bob and 1 more use GitHub, but this project has no GitHub connection')
  assert.equal(issues[0].href, '/projects/4/settings#connections')
  assert.match(setupIssues({ ...base, agents: [agent(1, 'Ada', ['github'])] })[0].text, /^Ada uses GitHub/)
})

test('a tool that needs a sign in, or has a problem, links to the tools', () => {
  const issues = setupIssues({ ...base, tools: [tool(1, 'notion', 'not_signed_in'), tool(2, 'docs', 'needs_sign_in'), tool(3, 'files', null, 'no command'), tool(4, 'ok', null)] })
  assert.deepEqual(
    issues.map((i) => i.text),
    ['Tool notion needs you to sign in', 'Tool docs needs a new sign in', 'Tool files has a problem: no command'],
  )
  assert.ok(issues.every((i) => i.href === '/projects/4/settings#tools'))
})
