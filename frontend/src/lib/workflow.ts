export type NodeKind = 'start' | 'trigger' | 'task' | 'agent' | 'condition' | 'end' | 'volume' | 'split' | 'merge'

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
  /** the number of connection points on this side comes from the node's settings (see branchPoints): a Splitter sends
   *  branches out at the bottom, a Merger takes them in at the top */
  branching?: 'out' | 'in'
}

export const NODE_KINDS: NodeKindInfo[] = [
  { kind: 'start', label: 'Start', description: 'A run begins here', hasInput: false, hasOutput: true },
  { kind: 'trigger', label: 'Trigger', description: 'Begins a run when a task moves into a status (schedules are not automatic yet)', hasInput: false, hasOutput: true },
  { kind: 'task', label: 'Task', description: 'Creates, moves or runs a task', hasInput: true, hasOutput: true },
  { kind: 'agent', label: 'Agent', description: 'Runs an agent', hasInput: true, hasOutput: true, mountIn: true },
  { kind: 'condition', label: 'Condition', description: 'Branches on a check: yes or no', hasInput: true, hasOutput: true, outputs: [{ id: 'yes', label: 'Yes' }, { id: 'no', label: 'No' }] },
  { kind: 'split', label: 'Splitter', description: 'Sends the run down several branches that run at the same time', hasInput: true, hasOutput: true, branching: 'out' },
  { kind: 'merge', label: 'Merger', description: 'Waits for its branches, then carries on with all of them together', hasInput: true, hasOutput: true, branching: 'in' },
  { kind: 'end', label: 'End', description: 'Finishes the workflow', hasInput: true, hasOutput: false },
  { kind: 'volume', label: 'Folder', description: 'A shared folder to hand to an Agent node', hasInput: false, hasOutput: false, mountOut: true },
]

export const kindInfo = (kind: NodeKind) => NODE_KINDS.find((k) => k.kind === kind)!

export type NodeConfig = Record<string, string>

export type WorkflowNodeData = { kind: NodeKind; label: string; config: NodeConfig }

export type FieldDef = {
  key: string
  label: string
  /** a toggle is on while its value is empty and off while it is 'off' (so a node saved when it was a select keeps meaning) */
  type: 'text' | 'textarea' | 'select' | 'time' | 'mounts' | 'toggle'
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

// a Splitter and a Merger have 2 to MAX_BRANCHES branches: their settings are listed for every number, and shown for those in use
export const MAX_BRANCHES = 4
const BRANCH_COUNTS = opts(['2', '2 branches'], ['3', '3 branches'], ['4', '4 branches'])
const branchNumbers = Array.from({ length: MAX_BRANCHES }, (_, i) => i + 1)
const forBranch = (n: number): FieldDef['when'] => ({ key: 'branches', oneOf: BRANCH_COUNTS.map((o) => o.value).filter((v) => Number(v) >= n) })

export const NODE_FIELDS: Record<NodeKind, FieldDef[]> = {
  start: [],
  trigger: [
    { key: 'type', label: 'Starts when', type: 'select', options: opts(['manual', 'I run it'], ['schedule', 'On a schedule'], ['task_status', 'A task moves into a status']) },
    { key: 'repeat', label: 'Repeats', type: 'select', options: opts(['day', 'Every day'], ['weekdays', 'Every weekday'], ['week', 'Every week'], ['month', 'Every month']), when: { key: 'type', oneOf: ['schedule'] } },
    { key: 'time', label: 'At', type: 'time', when: { key: 'type', oneOf: ['schedule'] } },
    // the options of status and where are the project's statuses and boards: the panel adds them to these
    { key: 'status', label: 'The status', type: 'select', options: STATUSES, hint: 'Runs when a task is moved into this status, or created in it. Where it came from does not matter. The task that moved is available to the steps after it.', when: { key: 'type', oneOf: ['task_status'] } },
    { key: 'where', label: 'Where', type: 'select', options: opts(['', 'Anywhere in the project']), hint: 'Only watch one workspace or one board. A status of your own belongs to one board and only fires there.', when: { key: 'type', oneOf: ['task_status'] } },
  ],
  task: [
    { key: 'action', label: 'Action', type: 'select', options: opts(['create', 'Create a task'], ['update', 'Update a task (by title)'], ['run', 'Run a task (by title)'], ['move_trigger', 'Move the task that started this run']) },
    { key: 'title', label: 'Task title', type: 'text', placeholder: 'What needs doing', when: { key: 'action', oneOf: ['create', 'update', 'run'] } },
    { key: 'description', label: 'Description', type: 'textarea', when: { key: 'action', oneOf: ['create'] } },
    { key: 'status', label: 'Move to', type: 'select', options: STATUSES, when: { key: 'action', oneOf: ['create', 'update', 'move_trigger'] } },
    // the options of boardId are the project's boards: the panel fills them in
    { key: 'boardId', label: 'On board', type: 'select', options: opts(['', 'Automatic']), hint: 'Automatic is the board of one of your own statuses, or the first board.', when: { key: 'action', oneOf: ['create'] } },
    { key: 'boardId', label: 'Send to board', type: 'select', options: opts(['', 'Stay on its board']), when: { key: 'action', oneOf: ['update', 'move_trigger'] } },
    { key: 'link', label: 'Follow up', type: 'select', options: opts(['', 'A separate task'], ['1', 'Follow up the task that started this run']), hint: 'A follow-up is linked to that task and takes its property values. Needs a Trigger that starts the run.', when: { key: 'action', oneOf: ['create'] } },
    { key: 'workdir', label: 'Working folder', type: 'select', options: opts(['', 'A fresh folder'], ['inherit', 'Continue in the previous folder']), hint: 'Continue lets the new task, and the workflows it plays, work on the files the step before this one left behind.', when: { key: 'action', oneOf: ['create'] } },
  ],
  agent: [
    // the options of agentId are the project's agents: the panel fills them in, this one is always there
    { key: 'agentId', label: 'Agent', type: 'select', options: opts(['', 'No agent: plain Codex']) },
    { key: 'harness', label: 'Runs with', type: 'select', options: opts(['codex', 'Codex agent']), when: { key: 'agentId', oneOf: [''] } },
    { key: 'instructions', label: 'Instructions', type: 'textarea', placeholder: 'What should the agent do?' },
    { key: 'brief', label: 'Include task title and description', type: 'toggle', hint: "Added to this step's instructions. Turn it off for housekeeping steps, like syncing or publishing." },
    { key: 'workdir', label: 'Working folder', type: 'select', options: opts(['', 'A fresh folder'], ['inherit', 'Continue in the previous folder']), hint: 'Continue works in the folder of the step before this one (or of the stage before this workflow), and is told what that step changed. Without anything before it, the agent gets a fresh folder.' },
    // the Advanced tab: most steps should simply stop the workflow
    { key: 'onFailure', label: 'If it fails', type: 'select', advanced: true, options: opts(['stop', 'Stop the workflow'], ['continue', 'Carry on']) },
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
  split: [
    { key: 'branches', label: 'Branches', type: 'select', options: BRANCH_COUNTS, hint: 'They run at the same time. Each gets the result of the step before, and a copy of the working folder when it continues in it.' },
    ...branchNumbers.flatMap((n): FieldDef[] => [
      { key: `name${n}`, label: `Branch ${n} name`, type: 'text', placeholder: `Branch ${n}`, when: forBranch(n) },
      { key: `contains${n}`, label: `Branch ${n}: only when the result contains`, type: 'text', placeholder: 'Always sent', when: forBranch(n) },
      {
        key: `files${n}`,
        label: `Branch ${n}: only these files`,
        type: 'text',
        placeholder: 'All files. For example src, docs/**, *.md',
        hint: n === 1 ? 'Paths in the working folder, separated by commas. A folder name means everything in it.' : undefined,
        when: forBranch(n),
      },
    ]),
  ],
  merge: [
    { key: 'branches', label: 'Branches', type: 'select', options: BRANCH_COUNTS, hint: 'Waits until every branch has finished or can no longer arrive, then carries on once.' },
    ...branchNumbers.map((n): FieldDef => ({
      key: `name${n}`,
      label: `Folder name for branch ${n}`,
      type: 'text',
      placeholder: 'Named after the node that sends it',
      hint: n === 1 ? "Each branch's files are put in a folder of this name, next to the others." : undefined,
      when: forBranch(n),
    })),
    { key: 'onFailure', label: 'If a branch fails', type: 'select', options: opts(['stop', 'Fail the merge'], ['continue', 'Merge the ones that worked']) },
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
      if (c.action === 'move_trigger') return `Move that task to ${statusText('task', c)}${c.boardId ? ' on another board' : ''}`
      return `${optionLabel('task', 'action', c)}${c.title ? `: ${c.title}` : ''}`
    case 'agent':
      return c.instructions.trim() ? c.instructions.trim().split('\n')[0] : 'No instructions yet'
    case 'condition':
      return c.operator === 'empty' ? `${optionLabel('condition', 'source', c)} is empty` : `${optionLabel('condition', 'source', c)} ${optionLabel('condition', 'operator', c)} ${c.value || '...'}`
    case 'end':
      return `Ends as ${c.outcome}`
    case 'volume':
      return c.volumeId ? (c.mode === 'ro' ? 'Read only' : 'Read and write') : 'No folder chosen'
    case 'split':
      return `${branchCount(c)} branches at the same time`
    case 'merge':
      return `Waits for ${branchCount(c)} branches`
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

/** the editor tells its lines which of them share a connection point (see crowdedLines) through this context */
export const CROWDED_LINES = Symbol('crowded-lines')

export const isMountEdge = (e: { sourceHandle?: string | null }) => e.sourceHandle === MOUNT

/** what may be joined to what: a Folder to an Agent through the folder points, and every other line only between steps */
export function canConnect(source: NodeKind | undefined, target: NodeKind | undefined, sourceHandle?: string | null, targetHandle?: string | null): boolean {
  if (sourceHandle === MOUNT || targetHandle === MOUNT) return sourceHandle === MOUNT && targetHandle === MOUNT && source === 'volume' && target === 'agent'
  // the branch points are only on a Splitter (out) and a Merger (in), and those two have nothing else to connect at
  if ((source === 'split') !== /^o\d$/.test(sourceHandle ?? '')) return false
  if ((target === 'merge') !== /^i\d$/.test(targetHandle ?? '')) return false
  return source !== 'volume' && target !== 'volume'
}

// ----- branches: a Splitter sends a run down several, a Merger waits for several -----

/** how many branches a Splitter or Merger has: its setting, 2 to MAX_BRANCHES */
export function branchCount(config: NodeConfig): number {
  const n = Number(config.branches)
  return Number.isInteger(n) ? Math.min(MAX_BRANCHES, Math.max(2, n)) : 2
}

/** the connection points a node's settings give it on its branching side, in order: "o1"... out of a Splitter,
 *  "i1"... into a Merger. A branch is called what the person named it. */
export function branchPoints(kind: NodeKind, config: NodeConfig): { id: string; label: string }[] {
  if (kindInfo(kind).branching === undefined) return []
  const out = kind === 'split'
  return Array.from({ length: branchCount(config) }, (_, i) => {
    const named = config[`name${i + 1}`]?.trim()
    return { id: `${out ? 'o' : 'i'}${i + 1}`, label: named || (out ? `Branch ${i + 1}` : String(i + 1)) }
  })
}

/** The lines that share a connection point with another line. The editor lets a point hold one line, so these come from
 *  workflows made before that rule. They still run, one after the other; they are marked so a Splitter or Merger can
 *  take their place. A folder may feed several agents, and an agent take several folders, so those do not count. */
export function crowdedLines(edges: { id: string; source: string; target: string; sourceHandle?: string | null; targetHandle?: string | null }[]): Set<string> {
  const steps = edges.filter((e) => !isMountEdge(e))
  const ends = (e: (typeof steps)[number]) => [`out:${e.source}:${e.sourceHandle ?? ''}`, `in:${e.target}:${e.targetHandle ?? ''}`]
  const count = new Map<string, number>()
  for (const e of steps) for (const k of ends(e)) count.set(k, (count.get(k) ?? 0) + 1)
  return new Set(steps.filter((e) => ends(e).some((k) => (count.get(k) ?? 0) > 1)).map((e) => e.id))
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

/** Does a Trigger's "where" cover this board? Empty is anywhere, "w:<id>" a workspace, "b:<id>" a board. */
export function coversBoard(where: string, board: { id: number; workspace_id: number }): boolean {
  if (where.startsWith('b:')) return where.slice(2) === String(board.id)
  if (where.startsWith('w:')) return where.slice(2) === String(board.workspace_id)
  return true
}

/** the workflows that start by themselves when a task moves into each status, for the badge on a board column. With a
 *  board, only those that watch that board count. */
export function watchersByStatus(
  workflows: { id: number; name: string; watches: { status: string; where: string }[] }[],
  board?: { id: number; workspace_id: number }
): Record<string, { id: number; name: string }[]> {
  const out: Record<string, { id: number; name: string }[]> = {}
  for (const w of workflows) {
    for (const { status, where } of w.watches) {
      if (board && !coversBoard(where, board)) continue
      const list = (out[status] ??= [])
      if (!list.some((x) => x.id === w.id)) list.push({ id: w.id, name: w.name })
    }
  }
  return out
}

/** the drag payload type used between the palette and the canvas */
export const DRAG_TYPE = 'application/themis-node-kind'
/** the payload of a saved node being dragged: its id (a built-in node is dragged as DRAG_TYPE with its kind) */
export const PRESET_DRAG_TYPE = 'application/themis-node-preset'

// ----- saved nodes -----

type SavedNode = { kind: NodeKind; label: string; config: NodeConfig }

/** the node a saved node places: its name and settings, topped up with the defaults of its kind */
export const presetNodeData = (p: SavedNode): WorkflowNodeData => ({
  kind: p.kind,
  label: p.label || kindInfo(p.kind).label,
  config: { ...defaultConfig(p.kind), ...p.config },
})

/** whether a node is exactly what a saved node holds, so the star on the node reads as saved */
export function isSavedNode(p: SavedNode, node: WorkflowNodeData): boolean {
  const a = presetNodeData(p)
  const b = presetNodeData({ ...node, label: node.label.trim() })
  const keys = (c: NodeConfig) => JSON.stringify(Object.entries(c).sort(([x], [y]) => x.localeCompare(y)))
  return a.kind === b.kind && a.label === b.label && keys(a.config) === keys(b.config)
}

// ----- saving and loading -----

export type GraphNode = { id: string; kind: NodeKind; label: string; config: NodeConfig; position: { x: number; y: number } }
/** how a connection is drawn: organic is a smooth curve, angular only runs straight up, down or sideways */
export type EdgeCurve = 'organic' | 'angular'
export const EDGE_CURVES: { value: EdgeCurve; label: string }[] = [
  { value: 'organic', label: 'Organic' },
  { value: 'angular', label: 'Angular' },
]
export type GraphEdge = { id: string; source: string; target: string; sourceHandle: string | null; targetHandle?: string | null; curve?: EdgeCurve | null }
export type Graph = { nodes: GraphNode[]; edges: GraphEdge[] }

type FlowNodeLike = { id: string; position: { x: number; y: number }; data: Record<string, unknown> }
type FlowEdgeLike = { id: string; source: string; target: string; sourceHandle?: string | null; targetHandle?: string | null; data?: Record<string, unknown> }

/** the style of a line, kept in the edge's data on the canvas and as `curve` in the saved graph (absent: organic) */
const curveOf = (e: { data?: Record<string, unknown> }): EdgeCurve | null => (e.data?.curve === 'angular' ? 'angular' : null)

/** only what is worth saving: no selection, size or other editor state */
export function toGraph(nodes: FlowNodeLike[], edges: FlowEdgeLike[]): Graph {
  return {
    nodes: nodes.map((n) => {
      const d = n.data as WorkflowNodeData
      return { id: n.id, kind: d.kind, label: d.label, config: d.config ?? defaultConfig(d.kind), position: { x: Math.round(n.position.x), y: Math.round(n.position.y) } }
    }),
    edges: edges.map((e) => ({ id: e.id, source: e.source, target: e.target, sourceHandle: e.sourceHandle ?? null, ...(e.targetHandle ? { targetHandle: e.targetHandle } : {}), ...(curveOf(e) ? { curve: curveOf(e) } : {}) })),
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
    edges: graph.edges.map((e) => ({ id: e.id, source: e.source, target: e.target, sourceHandle: e.sourceHandle, ...(e.targetHandle ? { targetHandle: e.targetHandle } : {}), ...(e.curve === 'angular' ? { data: { curve: e.curve } } : {}) })),
  }
}

/** the next free node id after the ones in a loaded graph (ids look like n7) */
export const nextNodeNumber = (ids: string[]) => ids.reduce((max, id) => Math.max(max, Number(id.match(/^n(\d+)$/)?.[1] ?? 0)), 0)

/** the graph a new workflow starts with: just where a run begins */
/** The steps of a graph that are given instructions (its Agent nodes), with who does each: for a ticket to show what its
 * stages tell the agents, in the order the nodes were made. A node with no agent chosen runs plain Codex. */
export function agentSteps(graph: Graph, agents: { id: number; name: string }[]) {
  return graph.nodes
    .filter((n) => n.kind === 'agent')
    .map((n) => ({
      nodeId: n.id,
      label: n.label.trim() || 'Agent',
      agent: agents.find((a) => String(a.id) === (n.config.agentId ?? '').trim())?.name ?? 'Plain Codex',
      instructions: (n.config.instructions ?? '').trim(),
    }))
}

export const seedGraph = (): Graph => ({ nodes: [{ id: 'n1', kind: 'start', label: 'Start', config: {}, position: { x: 0, y: 0 } }], edges: [] })

/** "Workflow 1", "Workflow 2"... the first number nobody uses yet (the server picks the same name) */
export function nextWorkflowName(names: string[]): string {
  const taken = new Set(names.map((n) => n.trim().toLowerCase()))
  let n = 1
  while (taken.has(`workflow ${n}`)) n++
  return `Workflow ${n}`
}
