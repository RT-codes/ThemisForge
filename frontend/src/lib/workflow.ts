export type NodeKind = 'trigger' | 'task' | 'agent' | 'condition' | 'end'

export type NodeKindInfo = {
  kind: NodeKind
  label: string
  description: string
  /** a trigger starts a workflow, so nothing connects into it */
  hasInput: boolean
  /** an end finishes a workflow, so nothing connects out of it */
  hasOutput: boolean
}

export const NODE_KINDS: NodeKindInfo[] = [
  { kind: 'trigger', label: 'Trigger', description: 'Starts the workflow', hasInput: false, hasOutput: true },
  { kind: 'task', label: 'Task', description: 'Creates or updates a task', hasInput: true, hasOutput: true },
  { kind: 'agent', label: 'Agent', description: 'Runs an agent', hasInput: true, hasOutput: true },
  { kind: 'condition', label: 'Condition', description: 'Branches on a check', hasInput: true, hasOutput: true },
  { kind: 'end', label: 'End', description: 'Finishes the workflow', hasInput: true, hasOutput: false },
]

export const kindInfo = (kind: NodeKind) => NODE_KINDS.find((k) => k.kind === kind)!

export type WorkflowNodeData = { kind: NodeKind; label: string }

/** the drag payload type used between the palette and the canvas */
export const DRAG_TYPE = 'application/themis-node-kind'
