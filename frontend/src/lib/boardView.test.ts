import assert from 'node:assert/strict'
import { test } from 'node:test'
import type { Task } from './api.ts'
import { applyView, emptyColumn, emptyView, filterCount, isDefaultView, parseStored, sortTasks, toggled } from './boardView.ts'

let n = 0
const task = (over: Partial<Task>): Task =>
  ({
    id: ++n, project_id: 1, title: `Task ${n}`, description: '', status: 'backlog', position: n, properties: {}, schedule_kind: 'none',
    cron: null, run_at: null, next_run_at: null, last_run_at: null, review_on_success: false, harness: '', workflow_id: null,
    created_at: `2026-01-0${n % 9 || 1}T00:00:00Z`, updated_at: '', last_attempt_status: null, workflow_run: null, ...over,
  }) as Task

const ids = (tasks: Task[]) => tasks.map((t) => t.title)

test('with nothing set, every task shows in the order it was arranged', () => {
  const tasks = [task({ title: 'b', position: 2 }), task({ title: 'a', position: 1 })]
  const r = applyView(tasks, emptyView())
  assert.deepEqual(ids(r.shown), ['a', 'b'])
  assert.deepEqual([r.filtered, r.reorderable], [false, true])
})

test('search looks at titles and descriptions, ignoring case', () => {
  const tasks = [task({ title: 'Fix login' }), task({ title: 'Docs', description: 'about the LOGIN page' }), task({ title: 'Other' })]
  const r = applyView(tasks, { ...emptyView(), search: ' login ' })
  assert.deepEqual(ids(r.shown), ['Fix login', 'Docs'])
  assert.deepEqual([r.filtered, r.reorderable], [true, false])
})

test('filters narrow by schedule, by what runs the task, and by select properties', () => {
  const tasks = [
    task({ title: 'daily', schedule_kind: 'cron' }),
    task({ title: 'once', schedule_kind: 'once' }),
    task({ title: 'agent', harness: 'codex', properties: { priority: 'High' } }),
    task({ title: 'flow', harness: 'workflow', properties: { priority: 'Low' } }),
    task({ title: 'plain' }),
  ]
  const view = (f: Partial<ReturnType<typeof emptyView>['filters']>) => ({ ...emptyView(), filters: { ...emptyView().filters, ...f } })
  assert.deepEqual(ids(applyView(tasks, view({ schedule: ['cron', 'once'] })).shown), ['daily', 'once'])
  assert.deepEqual(ids(applyView(tasks, view({ harness: ['codex', 'workflow'] })).shown), ['agent', 'flow'])
  assert.deepEqual(ids(applyView(tasks, view({ props: { priority: ['High'] } })).shown), ['agent'])
  assert.deepEqual(ids(applyView(tasks, view({ props: { priority: [''] } })).shown), ['daily', 'once', 'plain']) // no value
  assert.deepEqual(ids(applyView(tasks, view({ props: { priority: [] } })).shown), ids(tasks)) // nothing chosen: no filter
  assert.deepEqual(ids(applyView(tasks, view({ schedule: ['none'], harness: [''] })).shown), ['plain']) // together
})

test('a column adds its own filters on top of the board, and its own order', () => {
  const tasks = [task({ title: 'b', schedule_kind: 'cron' }), task({ title: 'a', schedule_kind: 'cron' }), task({ title: 'c' })]
  const board = { ...emptyView(), search: '' }
  const column = { sort: 'title' as const, filters: { ...emptyColumn().filters, schedule: ['cron' as const] } }
  assert.deepEqual(ids(applyView(tasks, board, column).shown), ['a', 'b'])
  const both = applyView(tasks, { ...board, filters: { ...board.filters, harness: ['codex' as const] } }, column)
  assert.deepEqual(both.shown, []) // board and column filters both apply
})

test('the board order is followed unless the column has its own', () => {
  const tasks = [task({ title: 'b', position: 1 }), task({ title: 'a', position: 2 })]
  assert.deepEqual(ids(applyView(tasks, { ...emptyView(), sort: 'title' }).shown), ['a', 'b'])
  assert.deepEqual(ids(applyView(tasks, { ...emptyView(), sort: 'title' }, { ...emptyColumn(), sort: 'manual' }).shown), ['b', 'a'])
})

test('only the arranged order can be reordered by dragging', () => {
  const tasks = [task({}), task({})]
  assert.equal(applyView(tasks, emptyView()).reorderable, true)
  assert.equal(applyView(tasks, { ...emptyView(), sort: 'title' }).reorderable, false)
  assert.equal(applyView(tasks, emptyView(), { ...emptyColumn(), sort: 'newest' }).reorderable, false)
})

test('every order', () => {
  const a = task({ title: 'beta', position: 3, created_at: '2026-01-02T00:00:00Z', next_run_at: '2026-05-02T00:00:00Z' })
  const b = task({ title: 'Alpha', position: 2, created_at: '2026-01-03T00:00:00Z', next_run_at: '2026-05-01T00:00:00Z' })
  const c = task({ title: 'gamma', position: 1, created_at: '2026-01-01T00:00:00Z' })
  const all = [a, b, c]
  assert.deepEqual(ids(sortTasks(all, 'manual')), ['gamma', 'Alpha', 'beta'])
  assert.deepEqual(ids(sortTasks(all, 'newest')), ['Alpha', 'beta', 'gamma'])
  assert.deepEqual(ids(sortTasks(all, 'oldest')), ['gamma', 'beta', 'Alpha'])
  assert.deepEqual(ids(sortTasks(all, 'title')), ['Alpha', 'beta', 'gamma'])
  assert.deepEqual(ids(sortTasks(all, 'next_run')), ['Alpha', 'beta', 'gamma']) // soonest first, unscheduled last
  assert.deepEqual(ids(all), ['beta', 'Alpha', 'gamma']) // the input is never reordered in place
})

test('counting what is filtered', () => {
  assert.equal(filterCount({ schedule: ['cron'], harness: [], props: { a: ['x', 'y'], b: [] } }), 2)
  assert.ok(isDefaultView(emptyView()))
  assert.ok(!isDefaultView({ ...emptyView(), search: 'x' }))
  assert.deepEqual(toggled(['a'], 'b'), ['a', 'b'])
  assert.deepEqual(toggled(['a', 'b'], 'a'), ['b'])
})

test('what was remembered is read safely', () => {
  const ok = parseStored(JSON.stringify({ board: { search: 'x', sort: 'title', filters: { schedule: ['cron', 'bogus'], props: { p: ['A'], q: [] } } }, columns: { ready: { sort: 'newest', filters: { harness: ['codex'] } } } }))
  assert.deepEqual([ok.board.search, ok.board.sort, ok.board.filters.schedule, ok.board.filters.props], ['x', 'title', ['cron'], { p: ['A'] }])
  assert.deepEqual([ok.columns.ready.sort, ok.columns.ready.filters.harness], ['newest', ['codex']])
  assert.deepEqual(parseStored(JSON.stringify({ hidden: ['done', 5, 'failed'] })).hidden, ['done', 'failed'])
  assert.deepEqual(parseStored('{"hidden":"done"}').hidden, [])
  for (const junk of [null, '', 'not json', '{"board": 5, "columns": "x"}', '{"board":{"sort":"sideways"}}']) {
    assert.ok(isDefaultView(parseStored(junk).board), String(junk))
  }
})
