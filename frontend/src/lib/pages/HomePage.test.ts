import assert from 'node:assert/strict'
import { after, before, test } from 'node:test'
import { createServer, type ViteDevServer } from 'vite'
import type { ProjectSummary } from '../api'

let server: ViteDevServer
let renderHome: (items: ProjectSummary[]) => string

const project = (id: number, task_counts: ProjectSummary['task_counts'], name = `Project ${id}`): ProjectSummary => ({
  id,
  name,
  purpose: '',
  description: '',
  icon: '',
  properties: [],
  cell_profile: null,
  automation: null,
  halted_at: null,
  created_at: '2026-01-01T00:00:00Z',
  task_counts,
  next_run_at: null,
})

before(async () => {
  Object.assign(globalThis, {
    window: { location: { pathname: '/', hash: '' }, addEventListener() {} },
    document: { addEventListener() {} },
  })
  server = await createServer({
    server: { middlewareMode: true },
    appType: 'custom',
    optimizeDeps: { noDiscovery: true },
    ssr: { optimizeDeps: { noDiscovery: true } },
  })
  const { render } = await server.ssrLoadModule('svelte/server')
  const { default: HomePage } = await server.ssrLoadModule('/src/lib/pages/HomePage.svelte')
  const { projects } = await server.ssrLoadModule('/src/lib/projects.svelte.ts')
  const { auth } = await server.ssrLoadModule('/src/lib/auth.svelte.ts')
  auth.user = { id: 1, name: 'Sam Example', email: 'sam@example.com', is_admin: false }
  renderHome = (items) => {
    projects.list = items
    return render(HomePage).body
  }
})

after(async () => { await server?.close() })

test('review and failed counts appear on the matching project card and preserve its link and normal counts', () => {
  const html = renderHome([
    project(1, { review: 2, running: 1, ready: 3, done: 4 }),
    project(2, { failed: 1, running: 0, ready: 2, done: 0 }),
  ])
  const cards = [...html.matchAll(/<a href="\/projects\/\d+"[\s\S]*?<\/a>/g)].map(([card]) => card)
  assert.equal(cards.length, 2)
  assert.match(cards[0], /2<\/span> to review/)
  assert.doesNotMatch(cards[0], /failed/)
  assert.match(cards[0], /1<\/span> running/)
  assert.match(cards[0], /3<\/span> ready/)
  assert.match(cards[0], /4<\/span> done/)
  assert.match(cards[1], /1<\/span> failed/)
  assert.doesNotMatch(cards[1], /to review/)
})

test('zero and missing follow-up counts do not show badges', () => {
  const html = renderHome([project(1, { review: 0, failed: 0 }), project(2, {})])
  assert.doesNotMatch(html, /to review|<\/span> failed/)
  assert.match(html, /0<\/span> running/)
})

test('both badges wrap on one card and a long project name remains in the linked card', () => {
  const html = renderHome([project(7, { review: 12, failed: 3 }, 'A very long project name with many details')])
  assert.match(html, /href="\/projects\/7"/)
  assert.match(html, /<h3 class="min-w-0 truncate font-medium">A very long project name with many details<\/h3>/)
  assert.match(html, /class="mb-3 flex flex-wrap gap-2 text-xs font-medium"/)
  assert.match(html, /12<\/span> to review/)
  assert.match(html, /3<\/span> failed/)
})
