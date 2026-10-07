import { api, type WorkflowRunDetail } from './api'

// What the canvas shows while a test run plays: which nodes are done, which one is playing, which are still to come.
//
// The server tells us what has happened; this shows it at a pace the eye can follow. Nodes are revealed one at a time:
// when a node starts, a glow first travels along the connections from the nodes that finished into it, and only then does
// the node itself light up as playing. A run that finishes in a blink is replayed the same way, in the order it ran.
// The look is only there while the run is going: when it ends, everything fades back to normal.

export const RUN_VIEW = Symbol('workflow-run-view')

/** how long the glow takes to travel along one connection */
export const GLOW_MS = 800
const POLL_MS = 700
const SETTLE_MS = 900 // after the last node, long enough to see it finish before the look fades away

export type Phase = 'playing' | 'done' | 'failed'
type Step = { id: string; source: string; target: string }

const sleep = (ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms))

export class RunView {
  /** a run is going: the canvas shows where it is */
  active = $state(false)
  /** how each node that has been revealed looks; a node missing here is still waiting its turn */
  shown = $state<Partial<Record<string, Phase>>>({})
  /** counters that go up every time a node finishes (it pulses) or a glow should travel along a connection */
  nodePulses = $state<Record<string, number>>({})
  edgePulses = $state<Record<string, number>>({})

  #edges: () => Step[]
  #real: Record<string, string> = {} // what the server says about each node: running, succeeded, failed, cancelled
  #queue: string[] = [] // nodes that started, waiting to be revealed in order
  #seen = new Set<string>()
  #working = false
  #token = 0 // changes when another run is followed or following stops: old loops notice and quit

  constructor(edges: () => Step[]) {
    this.#edges = edges
  }

  stop() {
    this.#token++
    this.#queue = []
    this.#seen.clear()
    this.#real = {}
    this.#working = false
    this.active = false
  }

  /** Follows a run until it is over and its look has faded; false if following was stopped or replaced before that. */
  async follow(runId: number): Promise<boolean> {
    this.stop()
    const token = this.#token
    this.shown = {}
    this.nodePulses = {}
    this.edgePulses = {}
    this.active = true
    while (token === this.#token) {
      let detail: WorkflowRunDetail | null = null
      try {
        detail = await api.workflowRun(runId)
      } catch {
        // transient: the next round asks again
      }
      if (token !== this.#token) return false
      if (detail) {
        this.#apply(detail)
        if (detail.status !== 'running') break
      }
      await sleep(POLL_MS)
    }
    while ((this.#working || this.#queue.length) && token === this.#token) await sleep(100)
    await sleep(SETTLE_MS)
    if (token !== this.#token) return false
    this.active = false
    return true
  }

  #apply(detail: WorkflowRunDetail) {
    for (const n of [...detail.nodes].sort((a, b) => a.seq - b.seq)) {
      if (n.status === 'skipped') continue // never reached: it simply stays as it was
      this.#real[n.node_id] = n.status
      if (!this.#seen.has(n.node_id)) {
        this.#seen.add(n.node_id)
        this.#queue.push(n.node_id)
      } else if (this.shown[n.node_id]) {
        this.#update(n.node_id)
      }
    }
    void this.#reveal()
  }

  /** a node that is already on screen changed (it finished): it takes its new look, with a pulse */
  #update(id: string) {
    const phase = this.#phase(id)
    if (this.shown[id] === phase) return
    this.shown[id] = phase
    if (phase !== 'playing') this.nodePulses[id] = (this.nodePulses[id] ?? 0) + 1
  }

  #phase(id: string): Phase {
    const status = this.#real[id]
    return status === 'running' ? 'playing' : status === 'succeeded' ? 'done' : 'failed'
  }

  /** shows the queued nodes one at a time, each after the glow along the connections that lead into it */
  async #reveal() {
    if (this.#working) return
    this.#working = true
    const token = this.#token
    while (this.#queue.length && token === this.#token) {
      const id = this.#queue.shift()!
      const incoming = this.#edges().filter((e) => e.target === id && this.#real[e.source] !== undefined && e.source !== id)
      if (incoming.length) {
        for (const e of incoming) this.edgePulses[e.id] = (this.edgePulses[e.id] ?? 0) + 1
        await sleep(GLOW_MS)
        if (token !== this.#token) return
      }
      this.shown[id] = this.#phase(id) // the latest word from the server, which may be "done" already
      if (this.shown[id] !== 'playing') this.nodePulses[id] = (this.nodePulses[id] ?? 0) + 1
    }
    if (token === this.#token) this.#working = false
  }
}
