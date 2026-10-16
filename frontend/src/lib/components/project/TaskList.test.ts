import assert from 'node:assert/strict'
import { after, before, test } from 'node:test'
import { createServer, type ViteDevServer } from 'vite'
import type { Board, Task } from '../../api.ts'
import { emptyView, type BoardView } from '../../boardView.ts'

const task = (overrides: Partial<Task> = {}): Task => ({
  id: 1, project_id: 1, board_id: 1, origin_task_id: null, title: 'Daily report', description: '',
  status: 'ready', position: 1, properties: {}, schedule_kind: 'cron', cron: '0 9 * * *', run_at: null,
  next_run_at: '2026-10-17T09:00:00Z', last_run_at: '2026-10-16T09:00:00Z', review_on_success: false,
  harness: 'codex', agent_id: null, internal: false, stages: [], hops: 0, cooldown_seconds: null, max_hops: null,
  created_at: '2026-10-01T00:00:00Z', updated_at: '2026-10-16T09:00:00Z',
  last_attempt_status: 'failed', last_failure_reason: 'Connection needs signing in.', workflow_run: null,
  ...overrides,
})
const board: Board = {
  id: 1, project_id: 1, workspace_id: 1, name: 'Tasks', purpose: '', position: 0,
  columns: [], task_counts: {}, halted_at: null, created_at: '2026-10-01T00:00:00Z',
}
let server: ViteDevServer
let list: (tasks: Task[], view?: BoardView, selectedId?: number) => string

before(async () => {
  server = await createServer({
    server: { middlewareMode: true, hmr: false },
    appType: 'custom',
    optimizeDeps: { noDiscovery: true },
    ssr: { optimizeDeps: { noDiscovery: true } },
  })
  const { render } = await server.ssrLoadModule('svelte/server')
  const { default: TaskList } = await server.ssrLoadModule('/src/lib/components/project/TaskList.svelte')
  list = (tasks, view = emptyView(), selectedId) => render(TaskList, {
    props: { tasks, board, defs: [], view, now: Date.parse('2026-10-16T10:00:00Z'), selectedId, onopen: () => {} },
  }).body
})

after(async () => { await server?.close() })

test('a failed recurring run stays visible alongside Ready and its next run', () => {
  const html = list([task()])
  assert.match(html, /Last run failed/)
  assert.match(html, /Connection needs signing in\./)
  assert.match(html, />Ready<|>\s*Ready\s*</)
  assert.match(html, /Every day/)
  assert.match(html, /aria-describedby="task-last-failure-1"/)
  assert.match(html, /id="task-last-failure-1"/)
})

test('failed one-off tasks show a warning even without a reason', () => {
  const html = list([task({ status: 'failed', schedule_kind: 'once', cron: null, last_failure_reason: '' })])
  assert.match(html, /Last run failed/)
  assert.match(html, />Failed<|>\s*Failed\s*</)
  assert.doesNotMatch(html, /title=""/)
})

test('running tasks and latest attempts that did not fail have no stale warning', () => {
  assert.doesNotMatch(list([task({ status: 'running' })]), /Last run failed|aria-describedby/)
  for (const last_attempt_status of ['succeeded', 'cancelled', 'running', null] as const) {
    assert.doesNotMatch(list([task({ last_attempt_status })]), /Last run failed|Connection needs|aria-describedby/)
  }
})

test('long reasons remain complete in accessible text and escaped in the tooltip', () => {
  const reason = 'Could not finish. '.repeat(40) + '<script>"unsafe"</script>'
  const html = list([task({ last_failure_reason: reason })])
  assert.match(html, /line-clamp-2/)
  assert.ok(html.includes('Could not finish. '.repeat(40)))
  assert.match(html, /title="[^"]*&lt;script>&quot;unsafe&quot;&lt;\/script>"/)
  assert.match(html, /&lt;script>"unsafe"&lt;\/script>/)
  assert.doesNotMatch(html, /<script>/)
})

test('warnings preserve search, filtering, ordering and the selected row', () => {
  const tasks = [task({ id: 2, title: 'Zebra' }), task({ id: 3, title: 'Alpha' }), task({ id: 4, title: 'Manual', schedule_kind: 'none' })]
  const view = emptyView()
  view.sort = 'title'
  view.filters.schedule = ['cron']
  const html = list(tasks, view, 3)
  assert.ok(html.indexOf('Alpha') < html.indexOf('Zebra'))
  assert.doesNotMatch(html, />Manual</)
  assert.match(html, /bg-primary\/10/)
  view.search = 'zebra'
  const searched = list(tasks, view)
  assert.match(searched, /Zebra/)
  assert.doesNotMatch(searched, /Alpha/)
})
