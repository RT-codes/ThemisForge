import assert from 'node:assert/strict'
import { test } from 'node:test'
import type { ConnectionProvider } from './api.ts'
import { catalog, filterCatalog, groupByCategory } from './connections.ts'

const github = {
  id: 'github',
  name: 'GitHub',
  description: 'Repositories, issues and pull requests.',
  icon: 'git-branch',
  category: 'service',
} as ConnectionProvider

test('the list has Codex first, then the providers', () => {
  assert.deepEqual(
    catalog([github]).map((e) => e.id),
    ['codex', 'github'],
  )
})

test('a search matches name, description and the kind of service, all words at once', () => {
  const all = catalog([github])
  assert.deepEqual(filterCatalog(all, 'git').map((e) => e.id), ['github'])
  assert.deepEqual(filterCatalog(all, 'pull REQUESTS').map((e) => e.id), ['github'])
  assert.deepEqual(filterCatalog(all, 'ai models').map((e) => e.id), ['codex'])
  assert.deepEqual(filterCatalog(all, 'git chatgpt'), [])
  assert.equal(filterCatalog(all, '  ').length, 2)
})

test('groups come in a fixed order and empty ones are left out', () => {
  const all = catalog([github, { ...github, id: 'odd', name: 'Odd', description: 'Something else.', category: 'weird' } as ConnectionProvider])
  assert.deepEqual(
    groupByCategory(all).map((g) => [g.label, g.entries.map((e) => e.id)]),
    [
      ['AI models', ['codex']],
      ['Services', ['github']],
      ['Other', ['odd']],
    ],
  )
  assert.deepEqual(groupByCategory(filterCatalog(all, 'github')).map((g) => g.id), ['service'])
})
