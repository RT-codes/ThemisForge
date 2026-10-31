import type { NodeRun, RunStatus } from './api/workflows'
import type { Graph, NodeKind } from './workflow'

// What the task panel shows for the workflow a stage is playing: the node before, the node now, and what comes next.
// This is only the shape; the panel draws it. It works from the graph the run began with and the nodes that have run
// so far, so the same function serves a run in progress and one that has ended.

/** done/running/failed/cancelled are nodes that ran; waiting is an approval gate nobody has answered yet; upcoming may
 *  still run; skipped will not (or did not) */
export type TrackState = 'done' | 'running' | 'waiting' | 'failed' | 'cancelled' | 'upcoming' | 'skipped'

export interface TrackNode {
  id: string
  label: string
  kind: NodeKind
  state: TrackState
}

/** a node that can follow the current one; `via` names the line leading to it when the current node branches */
export interface TrackOption {
  node: TrackNode
  via: string | null
}

export interface Track {
  previous: TrackNode | null
  current: TrackNode | null
  /** more than one when the node branches (a condition) or fans out: shown one under the other */
  next: TrackOption[]
}

// a Folder node and its lines are not steps (see the workflow engine), so they never take part in a run
const MOUNT = 'mount'
const START_KINDS: NodeKind[] = ['start', 'trigger']

/** a Splitter branch ("o2") by the name the person gave it, or "Branch 2" */
const branchLabel = (config: Record<string, string>, handle: string | null | undefined) => {
  const n = /^o(\d)$/.exec(handle ?? '')?.[1]
  return n ? config[`name${n}`]?.trim() || `Branch ${n}` : null
}

const FINISHED: Record<string, TrackState> = { succeeded: 'done', failed: 'failed', cancelled: 'cancelled' }

export function stageTrack(graph: Graph, runs: NodeRun[], runStatus: RunStatus): Track {
  const steps = new Map(graph.nodes.filter((n) => n.kind !== 'volume').map((n) => [n.id, n]))
  const edges = graph.edges.filter((e) => e.sourceHandle !== MOUNT && steps.has(e.source) && steps.has(e.target))
  const records = new Map(runs.map((r) => [r.node_id, r]))
  const ran = runs.filter((r) => r.status !== 'skipped').sort((a, b) => a.seq - b.seq)

  const stateOf = (id: string): TrackState => {
    const record = records.get(id)
    if (record?.status === 'running') return 'running'
    if (record?.status === 'waiting') return 'waiting'
    if (record && record.status !== 'skipped') return FINISHED[record.status] ?? 'done'
    return record || runStatus !== 'running' ? 'skipped' : 'upcoming'
  }
  const trackNode = (id: string, state = stateOf(id)): TrackNode => {
    const n = steps.get(id)!
    return { id, label: n.label || n.kind, kind: n.kind, state }
  }

  // the node playing now; between two nodes (or once the run has ended) the last one that ran
  const live = [...ran].reverse().find((r) => r.status === 'running' || r.status === 'waiting') ?? ran[ran.length - 1]
  if (!live || !steps.has(live.node_id)) {
    // nothing has run yet: the way in is the Start (or Trigger) nodes
    const starts = [...steps.values()].filter((n) => START_KINDS.includes(n.kind) || !edges.some((e) => e.target === n.id))
    return { previous: null, current: null, next: starts.map((n) => ({ node: trackNode(n.id), via: null })) }
  }

  // the node that fed it: of the lines leading in, the one whose source ran last
  const feeder = edges
    .filter((e) => e.target === live.node_id)
    .map((e) => records.get(e.source))
    .filter((r): r is NodeRun => !!r && r.status !== 'skipped')
    .sort((a, b) => b.seq - a.seq)[0]

  const current = trackNode(live.node_id)
  // a condition that has answered sends the run down one line only
  const answered = steps.get(live.node_id)!.kind === 'condition' && live.status === 'succeeded' ? live.result : null
  const stopped = current.state === 'failed' || current.state === 'cancelled'
  const seen = new Set<string>()
  const next: TrackOption[] = []
  for (const e of edges.filter((e) => e.source === live.node_id)) {
    if (seen.has(e.target)) continue
    seen.add(e.target)
    const handle = e.sourceHandle ?? 'yes'
    const wrongBranch = answered !== null && handle !== answered
    const ranAlready = records.get(e.target) && records.get(e.target)!.status !== 'skipped'
    const state = ranAlready ? stateOf(e.target) : wrongBranch || stopped ? 'skipped' : stateOf(e.target)
    const kind = steps.get(live.node_id)!.kind
    // the line says which way it leaves: a condition's Yes or No, or the name of a Splitter's branch
    const via = kind === 'condition' ? (handle === 'no' ? 'No' : 'Yes') : kind === 'split' ? branchLabel(steps.get(live.node_id)!.config, e.sourceHandle) : null
    next.push({ node: trackNode(e.target, state), via })
  }
  return { previous: feeder ? trackNode(feeder.node_id) : null, current, next }
}

/** the word for a stage's status, and the colour of its icon and word */
export const STAGE_LABEL: Record<'pending' | RunStatus, string> = {
  pending: 'Not started',
  running: 'Running',
  succeeded: 'Done',
  failed: 'Failed',
  cancelled: 'Cancelled',
}
export const STAGE_TONE: Record<'pending' | RunStatus, string> = {
  pending: 'text-muted-foreground',
  running: 'text-primary',
  succeeded: 'text-tone-green',
  failed: 'text-destructive',
  cancelled: 'text-muted-foreground',
}

/**
 * What a board card lists of a task's stages. A card is small and a task may have many stages, so the ones that are
 * done fold into a count, and only the first few that are not (the one running or failed, then those still to come)
 * are listed, with how many more there are.
 */
export function cardStages<T extends { status: string }>(stages: T[], limit = 3): { done: number; shown: T[]; more: number } {
  const open = stages.filter((s) => s.status !== 'succeeded')
  return { done: stages.length - open.length, shown: open.slice(0, limit), more: Math.max(0, open.length - limit) }
}
