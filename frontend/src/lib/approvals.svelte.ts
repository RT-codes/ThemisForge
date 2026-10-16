import { api, type Approval } from './api'
import { announce, headline } from './approvals'
import { toasts } from './toasts.svelte'

/** The approvals waiting for the signed-in person: workflow runs parked at an Approval node. Polled while the app is
 * open; a new one pops up as a toast that opens the panel on it (see ApprovalsPanel). */
class Approvals {
  list = $state<Approval[]>([])
  loaded = $state(false)
  /** the panel is open, and which approval it opens on */
  open = $state(false)
  focus = $state<number | null>(null)
  // the ids already announced; one is forgotten once it is answered, so it can never come back and be announced twice
  #seen = new Set<number>()

  async refresh() {
    let pending: Approval[]
    try {
      pending = await api.approvals()
    } catch {
      return // transient: the next poll retries
    }
    // with the panel open the person is looking at the list, which updates under them: a toast would only repeat it
    const news = this.open ? null : announce(this.#seen, pending)
    this.#seen = new Set(pending.map((a) => a.id))
    this.list = pending
    this.loaded = true
    if (news?.kind === 'one') {
      const a = news.approval
      toasts.push({
        title: 'Approval needed',
        body: headline(a),
        meta: `${a.project_name} · ${a.workflow_name}`,
        tone: 'attention',
        onSelect: () => this.show(a.id),
      })
    } else if (news?.kind === 'many') {
      toasts.push({
        title: `${news.count} approvals waiting`,
        body: 'Runs are parked until you approve or reject them.',
        tone: 'attention',
        onSelect: () => this.show(),
      })
    }
  }

  /** opens the panel, on one approval when given */
  show(id: number | null = null) {
    this.focus = id
    this.open = true
    toasts.dismissTone('attention') // the panel shows what they said
  }

  /** forget everything (signing out) */
  reset() {
    this.list = []
    this.loaded = false
    this.open = false
    this.focus = null
    this.#seen = new Set()
  }
}

export const approvals = new Approvals()
