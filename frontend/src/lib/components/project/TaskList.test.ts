import assert from 'node:assert/strict'
import { after, before, test } from 'node:test'
import { createServer, type ViteDevServer } from 'vite'
import type { Board, Task } from '../../api.ts'
import { emptyView } from '../../boardView.ts'

let server: ViteDevServer
let list: (overrides?: Partial<Task>) => string

before(async () => {
  server = await createServer({
    server: { middlewareMode: true },
    appType: 'custom',
    optimizeDeps: { noDiscovery: true },
    ssr: { optimizeDeps: { noDiscovery: true } },
  })
  const { render } = await server.ssrLoadModule('svelte/server')
  const { default: TaskList } = await server.ssrLoadModule('/src/lib/components/project/TaskList.svelte')
  const board: Board = {
    id: 1, project_id: 1, workspace_id: 1, name: 'Tasks', purpose: '', position: 0,
    columns: [], task_counts: {}, halted_at: null, created_at: '2026-01-01T00:00:00Z',
  }
  list = (overrides = {}) => {
    const task: Task = {
      id: 1, project_id: 1, board_id: 1, origin_task_id: null, title: 'Publish report', description: '',
      status: 'failed', position: 0, properties: {}, schedule_kind: 'none', cron: null, run_at: null,
      next_run_at: null, last_run_at: null, review_on_success: false, harness: '', agent_id: null,
      internal: false, stages: [], hops: 0, cooldown_seconds: null, max_hops: null,
      created_at: '2026-01-01T00:00:00Z', updated_at: '2026-01-01T00:00:00Z',
      last_attempt_status: 'failed', last_failure_reason: 'Publishing key is missing.', workflow_run: null,
      ...overrides,
    }
    return render(TaskList, {
      props: { tasks: [task], board, defs: [], view: emptyView(), now: Date.parse(task.created_at), onopen: () => {} },
    }).body
  }
})

after(async () => { await server?.close() })

test('failed one-off and Ready recurring tasks show their latest failure beneath the title', () => {
  for (const overrides of [{}, { status: 'ready', schedule_kind: 'cron', cron: '0 9 * * *' }] as Partial<Task>[]) {
    const html = list(overrides)
    assert.match(html, /<button[^>]*>Publish report<\/button>[\s\S]*<p[^>]*>Last run failed: Publishing key is missing\.<\/p>/)
    assert.match(html, /title="Publishing key is missing\."/)
  }
})

test('running retries and latest attempts that did not fail hide old failure reasons', () => {
  assert.doesNotMatch(list({ status: 'running' }), /Last run failed:/)
  for (const last_attempt_status of ['succeeded', 'cancelled', 'running', null] as const) {
    assert.doesNotMatch(list({ last_attempt_status }), /Last run failed:/)
  }
  assert.doesNotMatch(list({ last_failure_reason: '' }), /Last run failed:/)
})

test('long failure reasons stay available in full and render as safe text', () => {
  const reason = '<script>alert(1)</script> ' + 'Missing permission for the shared folder. '.repeat(20)
  const html = list({ last_failure_reason: reason })
  assert.match(html, /line-clamp-2/)
  assert.match(html, /Last run failed: &lt;script>alert\(1\)&lt;\/script>/)
  assert.ok(html.includes('Missing permission for the shared folder. '.repeat(20)))
  assert.doesNotMatch(html, /<script>/)
})
