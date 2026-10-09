import assert from 'node:assert/strict'
import { test } from 'node:test'
import { seedGraph, MOUNT, canConnect, isMountEdge, mountsFromGraph, formatMounts, parseMounts, nextWorkflowName, NODE_FIELDS, NODE_KINDS, defaultConfig, fromGraph, kindInfo, nextNodeNumber, summary, toGraph, visibleFields, watchersByStatus, type NodeKind } from './workflow.ts'

test('every kind has fields, and every select has options', () => {
  for (const { kind } of NODE_KINDS) {
    if (kind !== 'start') assert.ok(NODE_FIELDS[kind].length > 0, kind)
    for (const f of NODE_FIELDS[kind]) if (f.type === 'select') assert.ok(f.options?.length, `${kind}.${f.key}`)
  }
})

test('defaults: selects start on the first option, text starts empty', () => {
  assert.deepEqual(defaultConfig('trigger'), { type: 'manual', repeat: 'day', time: '09:00', status: 'backlog' })
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
  assert.equal(summary('trigger', { type: 'task_status', status: 'review' }), 'A task moves into Review')
  assert.equal(summary('task', { ...defaultConfig('task'), action: 'move_trigger', status: 'done' }), 'Move that task to Done')
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

// ----- folders handed to agents -----

test('a Folder joins an agent only through the folder points', () => {
  assert.ok(canConnect('volume', 'agent', MOUNT, MOUNT))
  for (const [from, to] of [['volume', 'task'], ['volume', 'end'], ['start', 'agent'], ['agent', 'agent']] as const)
    assert.ok(!canConnect(from, to, MOUNT, MOUNT), `${from} -> ${to}`)
  assert.ok(!canConnect('volume', 'agent', MOUNT, null), 'a folder point must meet a folder point')
  assert.ok(!canConnect('volume', 'agent', null, MOUNT))
})

test('nothing else may be joined to a Folder, and steps still connect as before', () => {
  assert.ok(!canConnect('start', 'volume'))
  assert.ok(!canConnect('volume', 'agent'))
  assert.ok(canConnect('start', 'agent'))
  assert.ok(canConnect('condition', 'task', 'yes', null))
  assert.ok(canConnect('agent', 'end'))
})

test('a line from a Folder is recognised as one that hands a folder over', () => {
  assert.ok(isMountEdge({ sourceHandle: MOUNT }))
  assert.ok(!isMountEdge({ sourceHandle: 'yes' }) && !isMountEdge({ sourceHandle: null }) && !isMountEdge({}))
})

const folderNode = (id: string, volumeId: string, mode = 'rw') => ({ id, data: { kind: 'volume', label: id, config: { volumeId, mode } } })

test('an agent is handed the folders that are joined to it, with the access each Folder says', () => {
  const nodes = [folderNode('f1', '3', 'ro'), folderNode('f2', '5'), folderNode('f3', ''), folderNode('f4', '9')]
  const edges = [
    { source: 'f1', target: 'a', sourceHandle: MOUNT },
    { source: 'f2', target: 'a', sourceHandle: MOUNT },
    { source: 'f3', target: 'a', sourceHandle: MOUNT }, // no folder chosen yet: nothing to hand over
    { source: 'f4', target: 'b', sourceHandle: MOUNT }, // another agent's
    { source: 's', target: 'a', sourceHandle: null }, // a step, not a folder
  ]
  assert.deepEqual(mountsFromGraph(nodes, edges, 'a'), [{ volume_id: 3, mode: 'ro' }, { volume_id: 5, mode: 'rw' }])
  assert.deepEqual(mountsFromGraph(nodes, edges, 'b'), [{ volume_id: 9, mode: 'rw' }])
  assert.deepEqual(mountsFromGraph(nodes, edges, 'nobody'), [])
})

test('a Folder node says what it hands over, and starts without a folder', () => {
  assert.equal(summary('volume', defaultConfig('volume')), 'No folder chosen')
  assert.equal(summary('volume', { volumeId: '3', mode: 'ro' }), 'Read only')
  assert.equal(summary('volume', { volumeId: '3', mode: 'rw' }), 'Read and write')
  assert.ok(kindInfo('volume').mountOut && !kindInfo('volume').hasInput && !kindInfo('volume').hasOutput)
  assert.ok(kindInfo('agent').mountIn)
})

test('the folder points survive saving and loading a graph', () => {
  const graph = { nodes: [], edges: [{ id: 'e', source: 'f', target: 'a', sourceHandle: MOUNT, targetHandle: MOUNT }] }
  const flow = fromGraph(graph)
  assert.equal(flow.edges[0].targetHandle, MOUNT)
  assert.deepEqual(toGraph([], flow.edges).edges[0], graph.edges[0])
  assert.ok(!('targetHandle' in toGraph([], [{ id: 'x', source: 'a', target: 'b' }]).edges[0])) // an ordinary line stays as it was
})

test('a status lists the workflows that start when a task moves into it', () => {
  const by = watchersByStatus([
    { id: 1, name: 'Triage', watches: ['backlog'] },
    { id: 2, name: 'By hand', watches: [] },
    { id: 3, name: 'Both', watches: ['backlog', 'review'] },
  ])
  assert.deepEqual(by.backlog, [{ id: 1, name: 'Triage' }, { id: 3, name: 'Both' }])
  assert.deepEqual(by.review, [{ id: 3, name: 'Both' }])
  assert.equal(by.done, undefined)
})
