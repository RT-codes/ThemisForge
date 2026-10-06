import assert from 'node:assert/strict'
import { test } from 'node:test'
import { seedGraph, formatMounts, parseMounts, nextWorkflowName, NODE_FIELDS, NODE_KINDS, defaultConfig, fromGraph, kindInfo, nextNodeNumber, summary, toGraph, visibleFields, type NodeKind } from './workflow.ts'

test('every kind has fields, and every select has options', () => {
  for (const { kind } of NODE_KINDS) {
    if (kind !== 'start') assert.ok(NODE_FIELDS[kind].length > 0, kind)
    for (const f of NODE_FIELDS[kind]) if (f.type === 'select') assert.ok(f.options?.length, `${kind}.${f.key}`)
  }
})

test('defaults: selects start on the first option, text starts empty', () => {
  assert.deepEqual(defaultConfig('trigger'), { type: 'manual', repeat: 'day', time: '09:00', status: 'inbox' })
  assert.equal(defaultConfig('task').title, '')
})

test('fields appear only when they apply', () => {
  const keys = (kind: NodeKind, c: Record<string, string>) => visibleFields(kind, c).map((f) => f.key)
  assert.deepEqual(keys('trigger', { type: 'manual' }), ['type'])
  assert.deepEqual(keys('trigger', { type: 'schedule' }), ['type', 'repeat', 'time'])
  assert.deepEqual(keys('task', { action: 'run' }), ['action', 'title'])
  assert.deepEqual(keys('task', { action: 'create' }), ['action', 'title', 'description', 'status'])
  assert.deepEqual(keys('condition', { operator: 'empty' }), ['source', 'operator'])
})

test('a visible field never depends on a field that does not exist', () => {
  for (const { kind } of NODE_KINDS) {
    const keys = new Set(NODE_FIELDS[kind].map((f) => f.key))
    for (const f of NODE_FIELDS[kind]) if (f.when) assert.ok(keys.has(f.when.key), `${kind}.${f.key}`)
  }
})

test('summaries read well', () => {
  assert.equal(summary('trigger', { type: 'schedule', repeat: 'weekdays', time: '08:30' }), 'Every weekday at 08:30')
  assert.equal(summary('task', { ...defaultConfig('task'), title: 'Write report' }), 'Create a task: Write report')
  assert.equal(summary('agent', { ...defaultConfig('agent'), instructions: ' Fix it\nthen test ' }), 'Fix it')
  assert.equal(summary('condition', { source: 'result', operator: 'contains', value: 'ok' }), 'The previous result contains ok')
  assert.equal(summary('end', { outcome: 'failed' }), 'Ends as failed')
})

test('a start node has no input, and a condition answers yes or no', () => {
  assert.equal(kindInfo('start').hasInput, false)
  assert.deepEqual(kindInfo('condition').outputs?.map((o) => o.id), ['yes', 'no'])
  assert.equal(summary('start', {}), 'Begins a run')
})

test('a graph survives saving and loading, minus editor state', () => {
  const flow = {
    nodes: [
      { id: 'n1', type: 'workflow', position: { x: 10.4, y: 20.6 }, selected: true, measured: { width: 1 }, data: { kind: 'start', label: 'Go', config: {} } },
      { id: 'n2', type: 'workflow', position: { x: 300, y: 20 }, data: { kind: 'condition', label: 'Ok?', config: { operator: 'empty' } } },
    ],
    edges: [{ id: 'e1', source: 'n1', target: 'n2', selected: true }, { id: 'e2', source: 'n2', target: 'n1', sourceHandle: 'no' }],
  }
  const graph = toGraph(flow.nodes, flow.edges)
  assert.deepEqual(graph.nodes[0], { id: 'n1', kind: 'start', label: 'Go', config: {}, position: { x: 10, y: 21 } })
  assert.deepEqual(graph.edges, [{ id: 'e1', source: 'n1', target: 'n2', sourceHandle: null }, { id: 'e2', source: 'n2', target: 'n1', sourceHandle: 'no' }])
  const back = fromGraph(JSON.parse(JSON.stringify(graph)))
  assert.equal(back.nodes[1].data.config.operator, 'empty')
  assert.equal(back.nodes[1].data.config.source, 'result') // defaults fill in what an older save lacks
  const again = toGraph(back.nodes, back.edges)
  assert.deepEqual(again.edges, graph.edges)
  const twice = fromGraph(again)
  assert.deepEqual(toGraph(twice.nodes, twice.edges), again) // saving is stable once defaults are filled in
})

test('new node ids continue after the loaded ones', () => {
  assert.equal(nextNodeNumber([]), 0)
  assert.equal(nextNodeNumber(['n3', 'n12', 'x']), 12)
})

test('a new workflow gets the first free numbered name', () => {
  assert.equal(nextWorkflowName([]), 'Workflow 1')
  assert.equal(nextWorkflowName(['Workflow 1', 'Workflow 2']), 'Workflow 3')
  assert.equal(nextWorkflowName(['Nightly', 'Workflow 2']), 'Workflow 1') // gaps are reused
  assert.equal(nextWorkflowName(['WORKFLOW 1', ' workflow 2 ']), 'Workflow 3') // case and spacing do not matter
})

test('a new workflow begins with a Start node only', () => {
  const g = seedGraph()
  assert.deepEqual(g.nodes.map((n) => n.kind), ['start'])
  assert.deepEqual(g.edges, [])
  assert.notEqual(seedGraph().nodes, g.nodes) // never shared between workflows
})

test('an agent node shows the harness only while no agent is chosen', () => {
  const none = visibleFields('agent', { ...defaultConfig('agent'), agentId: '' }).map((f) => f.key)
  const chosen = visibleFields('agent', { ...defaultConfig('agent'), agentId: '4' }).map((f) => f.key)
  assert.ok(none.includes('harness') && !chosen.includes('harness'))
  assert.ok(chosen.includes('agentId') && chosen.includes('instructions'))
})

test('an old agent node without an agent keeps working: it starts on "no agent"', () => {
  const config = { ...defaultConfig('agent'), harness: 'codex', instructions: 'x' }
  assert.equal(config.agentId, '')
})

test('folders on a node are kept as plain text and read back the same', () => {
  const mounts = [{ volume_id: 3, mode: 'rw' as const }, { volume_id: 5, mode: 'ro' as const }]
  assert.equal(formatMounts(mounts), '3:rw,5:ro')
  assert.deepEqual(parseMounts('3:rw,5:ro'), mounts)
  assert.deepEqual(parseMounts(''), [])
})

test('folder text that is damaged is read as far as it makes sense', () => {
  assert.deepEqual(parseMounts('3, x:rw, 0:rw, 3:ro, 7:odd'), [{ volume_id: 3, mode: 'rw' }, { volume_id: 7, mode: 'rw' }])
})
