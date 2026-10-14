import assert from 'node:assert/strict'
import { after, before, test } from 'node:test'
import { createServer, type ViteDevServer } from 'vite'
import type { ProjectSummary } from '../api.ts'

let server: ViteDevServer
let home: (counts: ProjectSummary['task_counts']) => string
let refresh: (counts: ProjectSummary['task_counts']) => Promise<string>

before(async () => {
  server = await createServer({
    plugins: [{
      name: 'home-test-router',
      enforce: 'pre',
      load(id) {
        if (id.endsWith('/src/lib/router.svelte.ts')) return 'export const router = { navigate() {} }'
      },
    }],
    server: { middlewareMode: true },
    appType: 'custom',
    optimizeDeps: { noDiscovery: true },
    ssr: { optimizeDeps: { noDiscovery: true } },
  })
  const { render } = await server.ssrLoadModule('svelte/server')
  const { default: HomePage } = await server.ssrLoadModule('/src/lib/pages/HomePage.svelte')
  const { projects } = await server.ssrLoadModule('/src/lib/projects.svelte.ts')
  const { api } = await server.ssrLoadModule('/src/lib/api.ts')
  const project: ProjectSummary = {
    id: 7, name: 'Reports', purpose: '', description: '', icon: '', properties: [],
    cell_profile: null, automation: null, halted_at: null, created_at: '2026-01-01T00:00:00Z',
    task_counts: {}, next_run_at: null,
  }
  home = (task_counts) => {
    projects.list = [{ ...project, task_counts }]
    return render(HomePage).body
  }
  refresh = async (task_counts) => {
    api.projects = async () => [{ ...project, task_counts }]
    await projects.refresh()
    return render(HomePage).body
  }
})

after(async () => { await server?.close() })

test('project cards show separate Review and Failed counts and retain overview navigation', () => {
  const html = home({ review: 3, failed: 2, running: 1, ready: 4, done: 9 })
  assert.match(html, /href="\/projects\/7"/)
  assert.match(html, /tabular-nums">3<\/span> Review/)
  assert.match(html, /tabular-nums">2<\/span> Failed/)
  assert.match(html, /tabular-nums">1<\/span> running/)
  assert.match(html, /tabular-nums">4<\/span> ready/)
  assert.match(html, /tabular-nums">9<\/span> done/)
})

test('zero and absent counts produce no attention indicators', () => {
  for (const counts of [{}, { review: 0, failed: 0 }, { ready: 5 }]) {
    assert.doesNotMatch(home(counts), /<\/span> (Review|Failed)/)
  }
  assert.doesNotMatch(home({ review: 1 }), /<\/span> Failed/)
  assert.doesNotMatch(home({ failed: 1 }), /<\/span> Review/)
})

test('refreshed counts replace old indicators, including large counts', async () => {
  home({ review: 2, failed: 1 })
  const html = await refresh({ review: 12345, failed: 0 })
  assert.match(html, /tabular-nums">12345<\/span> Review/)
  assert.doesNotMatch(html, /<\/span> Failed/)
})
