export type NodeKind = 'start' | 'trigger' | 'task' | 'agent' | 'condition' | 'end' | 'volume'

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
  /** a Folder joins an agent from this point: a line that hands the agent a folder, not a step that follows another */
  mountOut?: boolean
  /** an agent takes folders at this point */
  mountIn?: boolean
}

export const NODE_KINDS: NodeKindInfo[] = [
  { kind: 'start', label: 'Start', description: 'A run begins here', hasInput: false, hasOutput: true },
  { kind: 'trigger', label: 'Trigger', description: 'Begins a run when a task moves into a status (schedules are not automatic yet)', hasInput: false, hasOutput: true },
  { kind: 'task', label: 'Task', description: 'Creates, moves or runs a task', hasInput: true, hasOutput: true },
  { kind: 'agent', label: 'Agent', description: 'Runs an agent', hasInput: true, hasOutput: true, mountIn: true },
  { kind: 'condition', label: 'Condition', description: 'Branches on a check: yes or no', hasInput: true, hasOutput: true, outputs: [{ id: 'yes', label: 'Yes' }, { id: 'no', label: 'No' }] },
  { kind: 'end', label: 'End', description: 'Finishes the workflow', hasInput: true, hasOutput: false },
  { kind: 'volume', label: 'Folder', description: 'A shared folder to hand to an Agent node', hasInput: false, hasOutput: false, mountOut: true },
]

export const kindInfo = (kind: NodeKind) => NODE_KINDS.find((k) => k.kind === kind)!

export type NodeConfig = Record<string, string>

export type WorkflowNodeData = { kind: NodeKind; label: string; config: NodeConfig }

export type FieldDef = {
  key: string
  label: string
  type: 'text' | 'textarea' | 'select' | 'time' | 'mounts'
  options?: { value: string; label: string }[]
  placeholder?: string
  hint?: string
  /** tucked away under "Cell and folders": settings most steps never need */
  advanced?: boolean
  /** only show this field while another field has one of these values */
  when?: { key: string; oneOf: string[] }
}

const opts = (...pairs: [string, string][]) => pairs.map(([value, label]) => ({ value, label }))
const STATUSES = opts(['backlog', 'Backlog'], ['ready', 'Ready'], ['review', 'Review'], ['done', 'Done'], ['failed', 'Failed'])

export const NODE_FIELDS: Record<NodeKind, FieldDef[]> = {
  start: [],
  trigger: [
    { key: 'type', label: 'Starts when', type: 'select', options: opts(['manual', 'I run it'], ['schedule', 'On a schedule'], ['task_status', 'A task moves into a status']) },
    { key: 'repeat', label: 'Repeats', type: 'select', options: opts(['day', 'Every day'], ['weekdays', 'Every weekday'], ['week', 'Every week'], ['month', 'Every month']), when: { key: 'type', oneOf: ['schedule'] } },
    { key: 'time', label: 'At', type: 'time', when: { key: 'type', oneOf: ['schedule'] } },
    { key: 'status', label: 'The status', type: 'select', options: STATUSES, hint: 'Runs when a task is moved into this status, or created in it. Where it came from does not matter. The task that moved is available to the steps after it.', when: { key: 'type', oneOf: ['task_status'] } },
  ],
  task: [
    { key: 'action', label: 'Action', type: 'select', options: opts(['create', 'Create a task'], ['update', 'Update a task (by title)'], ['run', 'Run a task (by title)'], ['move_trigger', 'Move the task that started this run']) },
    { key: 'title', label: 'Task title', type: 'text', placeholder: 'What needs doing', when: { key: 'action', oneOf: ['create', 'update', 'run'] } },
    { key: 'description', label: 'Description', type: 'textarea', when: { key: 'action', oneOf: ['create'] } },
    { key: 'status', label: 'Move to', type: 'select', options: STATUSES, when: { key: 'action', oneOf: ['create', 'update', 'move_trigger'] } },
  ],
  agent: [
    // the options of agentId are the project's agents: the panel fills them in, this one is always there
    { key: 'agentId', label: 'Agent', type: 'select', options: opts(['', 'No agent: plain Codex']) },
    { key: 'harness', label: 'Runs with', type: 'select', options: opts(['codex', 'Codex agent']), when: { key: 'agentId', oneOf: [''] } },
    { key: 'instructions', label: 'Instructions', type: 'textarea', placeholder: 'What should the agent do?' },
    { key: 'onFailure', label: 'If it fails', type: 'select', options: opts(['stop', 'Stop the workflow'], ['continue', 'Carry on'])},
    { key: 'cellCpus', label: 'CPUs', type: 'text', advanced: true, placeholder: 'From the agent or project' },
    { key: 'cellMemory', label: 'Memory (MB)', type: 'text', advanced: true, placeholder: 'From the agent or project' },
    { key: 'cellTimeout', label: 'Time limit (seconds)', type: 'text', advanced: true, placeholder: 'From the agent or project' },
    { key: 'cellImage', label: 'Image', type: 'text', advanced: true, placeholder: 'From the agent or project' },
    { key: 'mounts', label: 'Extra folders for this step', type: 'mounts', advanced: true },
  ],
  condition: [
    { key: 'source', label: 'Check', type: 'select', options: opts(['result', 'The previous result'], ['status', 'The previous status']) },
    { key: 'operator', label: 'Is', type: 'select', options: opts(['contains', 'contains'], ['equals', 'equal to'], ['not_equals', 'not equal to'], ['empty', 'empty']) },
    { key: 'value', label: 'Value', type: 'text', when: { key: 'operator', oneOf: ['contains', 'equals', 'not_equals'] } },
  ],
  volume: [
    // the options of volumeId are the project's folders: the panel fills them in
    { key: 'volumeId', label: 'Folder', type: 'select', options: opts(['', 'Choose a folder']) },
    { key: 'mode', label: 'The agent may', type: 'select', options: opts(['rw', 'Read and write'], ['ro', 'Read only']) },
  ],
  end: [
    { key: 'outcome', label: 'Finishes as', type: 'select', options: opts(['success', 'Success'], ['failed', 'Failed'], ['review', 'Needs review']) },
    { key: 'note', label: 'Note', type: 'text', placeholder: 'Shown with the outcome' },
  ],
}

/** every field starts empty, selects start on their first option */
export function defaultConfig(kind: NodeKind): NodeConfig {
  return Object.fromEntries(NODE_FIELDS[kind].map((f) => [f.key, f.type === 'select' ? f.options![0].value : f.type === 'time' ? '09:00' : '']))
}

export const visibleFields = (kind: NodeKind, config: NodeConfig) =>
  NODE_FIELDS[kind].filter((f) => !f.when || f.when.oneOf.includes(config[f.when.key] ?? ''))

const optionLabel = (kind: NodeKind, key: string, config: NodeConfig) =>
  NODE_FIELDS[kind].find((f) => f.key === key)?.options?.find((o) => o.value === config[key])?.label ?? ''

/** the status a node names; a custom one is a board's own and the canvas does not know its name, so it stays generic */
const statusText = (kind: NodeKind, c: NodeConfig) => optionLabel(kind, 'status', c) || (c.status?.startsWith('custom:') ? 'a custom status' : c.status)

/** one line shown on the node, so a canvas can be read without opening every node */
export function summary(kind: NodeKind, c: NodeConfig): string {
  switch (kind) {
    case 'start':
      return 'Begins a run'
    case 'trigger':
      return c.type === 'schedule' ? `${optionLabel('trigger', 'repeat', c)} at ${c.time || '09:00'}` : c.type === 'task_status' ? `A task moves into ${statusText('trigger', c)}` : 'Run by hand'
    case 'task':
      if (c.action === 'move_trigger') return `Move that task to ${statusText('task', c)}`
      return `${optionLabel('task', 'action', c)}${c.title ? `: ${c.title}` : ''}`
    case 'agent':
      return c.instructions.trim() ? c.instructions.trim().split('\n')[0] : 'No instructions yet'
    case 'condition':
      return c.operator === 'empty' ? `${optionLabel('condition', 'source', c)} is empty` : `${optionLabel('condition', 'source', c)} ${optionLabel('condition', 'operator', c)} ${c.value || '...'}`
    case 'end':
      return `Ends as ${c.outcome}`
    case 'volume':
      return c.volumeId ? (c.mode === 'ro' ? 'Read only' : 'Read and write') : 'No folder chosen'
  }
}

export type MountChoice = { volume_id: number; mode: 'ro' | 'rw' }

/** a node keeps its folders as plain text, "3:rw,5:ro" (volume id and mode), like every other node setting */
export function parseMounts(text: string): MountChoice[] {
  const out: MountChoice[] = []
  for (const part of text.split(',')) {
    const [id, mode] = part.trim().split(':')
    const volume_id = Number(id)
    if (id && Number.isInteger(volume_id) && volume_id > 0 && !out.some((m) => m.volume_id === volume_id)) out.push({ volume_id, mode: mode === 'ro' ? 'ro' : 'rw' })
  }
  return out
}

export const formatMounts = (mounts: MountChoice[]): string => mounts.map((m) => `${m.volume_id}:${m.mode}`).join(',')

// ----- folders handed to agents -----

/** the connection point a Folder uses on both ends of the line that hands a folder to an agent */
export const MOUNT = 'mount'

export const isMountEdge = (e: { sourceHandle?: string | null }) => e.sourceHandle === MOUNT

/** what may be joined to what: a Folder to an Agent through the folder points, and every other line only between steps */
export function canConnect(source: NodeKind | undefined, target: NodeKind | undefined, sourceHandle?: string | null, targetHandle?: string | null): boolean {
  if (sourceHandle === MOUNT || targetHandle === MOUNT) return sourceHandle === MOUNT && targetHandle === MOUNT && source === 'volume' && target === 'agent'
  return source !== 'volume' && target !== 'volume'
}

type MountNodeLike = { id: string; data: Record<string, unknown> }

/** the folders handed to an agent node by lines from Folder nodes (a Folder with none chosen hands over nothing) */
export function mountsFromGraph(nodes: MountNodeLike[], edges: { source: string; target: string; sourceHandle?: string | null }[], agentId: string): MountChoice[] {
  const out: MountChoice[] = []
  for (const e of edges) {
    if (e.target !== agentId || !isMountEdge(e)) continue
    const config = (nodes.find((n) => n.id === e.source)?.data as WorkflowNodeData | undefined)?.config
    const volume_id = Number(config?.volumeId)
    if (Number.isInteger(volume_id) && volume_id > 0) out.push({ volume_id, mode: config?.mode === 'ro' ? 'ro' : 'rw' })
  }
  return out
}

/** the workflows that start by themselves when a task moves into each status, for the badge on a board column */
export function watchersByStatus(workflows: { id: number; name: string; watches: string[] }[]): Record<string, { id: number; name: string }[]> {
  const out: Record<string, { id: number; name: string }[]> = {}
  for (const w of workflows) for (const status of w.watches) (out[status] ??= []).push({ id: w.id, name: w.name })
  return out
}

/** the drag payload type used between the palette and the canvas */
export const DRAG_TYPE = 'application/themis-node-kind'

// ----- saving and loading -----

export type GraphNode = { id: string; kind: NodeKind; label: string; config: NodeConfig; position: { x: number; y: number } }
export type GraphEdge = { id: string; source: string; target: string; sourceHandle: string | null; targetHandle?: string | null }
export type Graph = { nodes: GraphNode[]; edges: GraphEdge[] }

type FlowNodeLike = { id: string; position: { x: number; y: number }; data: Record<string, unknown> }
type FlowEdgeLike = { id: string; source: string; target: string; sourceHandle?: string | null; targetHandle?: string | null }

/** only what is worth saving: no selection, size or other editor state */
export function toGraph(nodes: FlowNodeLike[], edges: FlowEdgeLike[]): Graph {
  return {
    nodes: nodes.map((n) => {
      const d = n.data as WorkflowNodeData
      return { id: n.id, kind: d.kind, label: d.label, config: d.config ?? defaultConfig(d.kind), position: { x: Math.round(n.position.x), y: Math.round(n.position.y) } }
    }),
    edges: edges.map((e) => ({ id: e.id, source: e.source, target: e.target, sourceHandle: e.sourceHandle ?? null, ...(e.targetHandle ? { targetHandle: e.targetHandle } : {}) })),
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
    edges: graph.edges.map((e) => ({ id: e.id, source: e.source, target: e.target, sourceHandle: e.sourceHandle, ...(e.targetHandle ? { targetHandle: e.targetHandle } : {}) })),
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
