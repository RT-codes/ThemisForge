import assert from 'node:assert/strict'
import { test } from 'node:test'
import type { NodeRun, NodeRunStatus } from './api.ts'
import { cardStages, stageTrack } from './stageTrack.ts'
import type { Graph, NodeKind } from './workflow.ts'

const node = (id: string, kind: NodeKind, label = id) => ({ id, kind, label, config: {}, position: { x: 0, y: 0 } })
const edge = (source: string, target: string, sourceHandle: string | null = null) => ({ id: `${source}-${target}-${sourceHandle}`, source, target, sourceHandle })
let seq = 0
const ran = (node_id: string, status: NodeRunStatus, result = ''): NodeRun =>
  ({ id: ++seq, node_id, kind: 'task', label: node_id, seq, status, started_at: null, finished_at: null, log: '', result, error: '', task_id: null, attempt_id: null }) as NodeRun

// start -> research -> check -(yes)-> publish -> end
//                        \-(no)--> rework
const graph: Graph = {
  nodes: [node('s', 'start'), node('r', 'agent', 'Research'), node('c', 'condition', 'Good?'), node('p', 'agent', 'Publish'), node('w', 'agent', 'Rework'), node('e', 'end')],
  edges: [edge('s', 'r'), edge('r', 'c'), edge('c', 'p', 'yes'), edge('c', 'w', 'no'), edge('p', 'e')],
}
const ids = (t: ReturnType<typeof stageTrack>) => [t.previous?.id ?? null, t.current?.id ?? null, t.next.map((o) => `${o.node.id}:${o.node.state}`)]

test('before anything ran, the way in is the Start node', () => {
  const t = stageTrack(graph, [], 'running')
  assert.deepEqual(ids(t), [null, null, ['s:upcoming']])
})

test('a node that is playing sits between the one before it and the one after', () => {
  seq = 0
  const t = stageTrack(graph, [ran('s', 'succeeded'), ran('r', 'running')], 'running')
  assert.deepEqual(ids(t), ['s', 'r', ['c:upcoming']])
  assert.equal(t.current?.state, 'running')
  assert.equal(t.previous?.state, 'done')
})

test('a condition that has not answered lists both ways, with the line each one takes', () => {
  seq = 0
  const t = stageTrack(graph, [ran('s', 'succeeded'), ran('r', 'succeeded'), ran('c', 'running')], 'running')
  assert.deepEqual(ids(t), ['r', 'c', ['p:upcoming', 'w:upcoming']])
  assert.deepEqual(t.next.map((o) => o.via), ['Yes', 'No'])
})

test('once a condition answered, the way not taken is dimmed and the taken one is playing', () => {
  seq = 0
  const answered = [ran('s', 'succeeded'), ran('r', 'succeeded'), ran('c', 'succeeded', 'no')]
  assert.deepEqual(ids(stageTrack(graph, answered, 'running')), ['r', 'c', ['p:skipped', 'w:upcoming']])
  seq = 0
  const taken = [...answered, ran('w', 'running')]
  assert.deepEqual(ids(stageTrack(graph, taken, 'running')), ['c', 'w', []])
})

test('a failed node stops the track: what came after it will not run', () => {
  seq = 0
  const t = stageTrack(graph, [ran('s', 'succeeded'), ran('r', 'failed')], 'failed')
  assert.deepEqual(ids(t), ['s', 'r', ['c:skipped']])
  assert.equal(t.current?.state, 'failed')
})

test('a finished run ends on its last node', () => {
  seq = 0
  const done = [ran('s', 'succeeded'), ran('r', 'succeeded'), ran('c', 'succeeded', 'yes'), ran('p', 'succeeded'), ran('e', 'succeeded'), ran('w', 'skipped')]
  const t = stageTrack(graph, done, 'succeeded')
  assert.deepEqual(ids(t), ['p', 'e', []])
})

test('Folder nodes and their lines are not steps', () => {
  seq = 0
  const withFolder: Graph = {
    nodes: [node('s', 'start'), node('a', 'agent'), node('f', 'volume')],
    edges: [edge('s', 'a'), edge('f', 'a', 'mount')],
  }
  const t = stageTrack(withFolder, [ran('s', 'succeeded'), ran('a', 'running')], 'running')
  assert.deepEqual(ids(t), ['s', 'a', []])
})

test('a card folds finished stages into a count and lists only the first few that are still open', () => {
  const stage = (status: string) => ({ status })
  const all = ['succeeded', 'succeeded', 'running', 'pending', 'pending', 'pending', 'pending'].map(stage)
  const c = cardStages(all)
  assert.equal(c.done, 2)
  assert.deepEqual(c.shown.map((s) => s.status), ['running', 'pending', 'pending'])
  assert.equal(c.more, 2)
  assert.deepEqual(cardStages([stage('succeeded'), stage('succeeded')]), { done: 2, shown: [], more: 0 })
  assert.deepEqual(cardStages([stage('failed'), stage('pending')]).shown.map((s) => s.status), ['failed', 'pending'])
})
