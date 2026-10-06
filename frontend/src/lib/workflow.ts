export type NodeKind = 'start' | 'trigger' | 'task' | 'agent' | 'condition' | 'end'

export type NodeKindInfo = {
  kind: NodeKind
  label: string
  description: string
  /** a trigger starts a workflow, so nothing connects into it */
  hasInput: boolean
  /** an end finishes a workflow, so nothing connects out of it */
  hasOutput: boolean
  /** named outputs, for nodes that branch (a condition answers yes or no) */
  outputs?: { id: string; label: string }[]
}

export const NODE_KINDS: NodeKindInfo[] = [
  { kind: 'start', label: 'Start', description: 'A run begins here', hasInput: false, hasOutput: true },
  { kind: 'trigger', label: 'Trigger', description: 'Also begins a run: on a schedule or event (not automatic yet)', hasInput: false, hasOutput: true },
  { kind: 'task', label: 'Task', description: 'Creates or updates a task', hasInput: true, hasOutput: true },
  { kind: 'agent', label: 'Agent', description: 'Runs an agent', hasInput: true, hasOutput: true },
  { kind: 'condition', label: 'Condition', description: 'Branches on a check: yes or no', hasInput: true, hasOutput: true, outputs: [{ id: 'yes', label: 'Yes' }, { id: 'no', label: 'No' }] },
  { kind: 'end', label: 'End', description: 'Finishes the workflow', hasInput: true, hasOutput: false },
]

export const kindInfo = (kind: NodeKind) => NODE_KINDS.find((k) => k.kind === kind)!

export type NodeConfig = Record<string, string>

export type WorkflowNodeData = { kind: NodeKind; label: string; config: NodeConfig }

export type FieldDef = {
  key: string
  label: string
  type: 'text' | 'textarea' | 'select'
  options?: { value: string; label: string }[]
  placeholder?: string
  hint?: string
  /** only show this field while another field has one of these values */
  when?: { key: string; oneOf: string[] }
}

const opts = (...pairs: [string, string][]) => pairs.map(([value, label]) => ({ value, label }))
const STATUSES = opts(['inbox', 'Inbox'], ['ready', 'Ready'], ['review', 'Review'], ['done', 'Done'], ['failed', 'Failed'])

export const NODE_FIELDS: Record<NodeKind, FieldDef[]> = {
  start: [],
  trigger: [
    { key: 'type', label: 'Starts when', type: 'select', options: opts(['manual', 'I run it'], ['schedule', 'On a schedule'], ['task_status', 'A task changes status']) },
    { key: 'cron', label: 'Schedule', type: 'text', placeholder: '0 9 * * *', hint: 'minute hour day month weekday', when: { key: 'type', oneOf: ['schedule'] } },
    { key: 'status', label: 'Status', type: 'select', options: STATUSES, when: { key: 'type', oneOf: ['task_status'] } },
  ],
  task: [
    { key: 'action', label: 'Action', type: 'select', options: opts(['create', 'Create a task'], ['update', 'Update a task'], ['run', 'Run a task']) },
    { key: 'title', label: 'Task title', type: 'text', placeholder: 'What needs doing', when: { key: 'action', oneOf: ['create', 'update', 'run'] } },
    { key: 'description', label: 'Description', type: 'textarea', when: { key: 'action', oneOf: ['create'] } },
    { key: 'status', label: 'Move to', type: 'select', options: STATUSES, when: { key: 'action', oneOf: ['create', 'update'] } },
  ],
  agent: [
    { key: 'harness', label: 'Agent', type: 'select', options: opts(['codex', 'Codex agent']) },
    { key: 'instructions', label: 'Instructions', type: 'textarea', placeholder: 'What should the agent do?' },
    { key: 'onFailure', label: 'If it fails', type: 'select', options: opts(['stop', 'Stop the workflow'], ['continue', 'Carry on'])},
  ],
  condition: [
    { key: 'source', label: 'Check', type: 'select', options: opts(['result', 'The previous result'], ['status', 'The previous status']) },
    { key: 'operator', label: 'Is', type: 'select', options: opts(['contains', 'contains'], ['equals', 'equal to'], ['not_equals', 'not equal to'], ['empty', 'empty']) },
    { key: 'value', label: 'Value', type: 'text', when: { key: 'operator', oneOf: ['contains', 'equals', 'not_equals'] } },
  ],
  end: [
    { key: 'outcome', label: 'Finishes as', type: 'select', options: opts(['success', 'Success'], ['failed', 'Failed'], ['review', 'Needs review']) },
    { key: 'note', label: 'Note', type: 'text', placeholder: 'Shown with the outcome' },
  ],
}

/** every field starts empty, selects start on their first option */
export function defaultConfig(kind: NodeKind): NodeConfig {
  return Object.fromEntries(NODE_FIELDS[kind].map((f) => [f.key, f.type === 'select' ? f.options![0].value : '']))
}

export const visibleFields = (kind: NodeKind, config: NodeConfig) =>
  NODE_FIELDS[kind].filter((f) => !f.when || f.when.oneOf.includes(config[f.when.key] ?? ''))

const optionLabel = (kind: NodeKind, key: string, config: NodeConfig) =>
  NODE_FIELDS[kind].find((f) => f.key === key)?.options?.find((o) => o.value === config[key])?.label ?? ''

/** one line shown on the node, so a canvas can be read without opening every node */
export function summary(kind: NodeKind, c: NodeConfig): string {
  switch (kind) {
    case 'start':
      return 'Begins a run'
    case 'trigger':
      return c.type === 'schedule' ? `Cron ${c.cron || 'not set'}` : c.type === 'task_status' ? `Task becomes ${c.status}` : 'Run by hand'
    case 'task':
      return `${optionLabel('task', 'action', c)}${c.title ? `: ${c.title}` : ''}`
    case 'agent':
      return c.instructions.trim() ? c.instructions.trim().split('\n')[0] : 'No instructions yet'
    case 'condition':
      return c.operator === 'empty' ? `${optionLabel('condition', 'source', c)} is empty` : `${optionLabel('condition', 'source', c)} ${optionLabel('condition', 'operator', c)} ${c.value || '...'}`
    case 'end':
      return `Ends as ${c.outcome}`
  }
}

/** the drag payload type used between the palette and the canvas */
export const DRAG_TYPE = 'application/themis-node-kind'

// ----- saving and loading -----

export type GraphNode = { id: string; kind: NodeKind; label: string; config: NodeConfig; position: { x: number; y: number } }
export type GraphEdge = { id: string; source: string; target: string; sourceHandle: string | null }
export type Graph = { nodes: GraphNode[]; edges: GraphEdge[] }

type FlowNodeLike = { id: string; position: { x: number; y: number }; data: Record<string, unknown> }
type FlowEdgeLike = { id: string; source: string; target: string; sourceHandle?: string | null }

/** only what is worth saving: no selection, size or other editor state */
export function toGraph(nodes: FlowNodeLike[], edges: FlowEdgeLike[]): Graph {
  return {
    nodes: nodes.map((n) => {
      const d = n.data as WorkflowNodeData
      return { id: n.id, kind: d.kind, label: d.label, config: d.config ?? defaultConfig(d.kind), position: { x: Math.round(n.position.x), y: Math.round(n.position.y) } }
    }),
    edges: edges.map((e) => ({ id: e.id, source: e.source, target: e.target, sourceHandle: e.sourceHandle ?? null })),
  }
}

export function fromGraph(graph: Graph) {
  return {
    nodes: graph.nodes.map((n) => ({
      id: n.id,
      type: 'workflow',
      position: n.position,
      data: { kind: n.kind, label: n.label, config: { ...defaultConfig(n.kind), ...n.config } } satisfies WorkflowNodeData,
    })),
    edges: graph.edges.map((e) => ({ id: e.id, source: e.source, target: e.target, sourceHandle: e.sourceHandle })),
  }
}

/** the next free node id after the ones in a loaded graph (ids look like n7) */
export const nextNodeNumber = (ids: string[]) => ids.reduce((max, id) => Math.max(max, Number(id.match(/^n(\d+)$/)?.[1] ?? 0)), 0)

/** the graph a new workflow starts with: just where a run begins */
export const seedGraph = (): Graph => ({ nodes: [{ id: 'n1', kind: 'start', label: 'Start', config: {}, position: { x: 0, y: 0 } }], edges: [] })

/** "Workflow 1", "Workflow 2"... the first number nobody uses yet (the server picks the same name) */
export function nextWorkflowName(names: string[]): string {
  const taken = new Set(names.map((n) => n.trim().toLowerCase()))
  let n = 1
  while (taken.has(`workflow ${n}`)) n++
  return `Workflow ${n}`
}
