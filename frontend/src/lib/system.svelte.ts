import { api, type SystemStatus } from './api'

/** What the server says about itself, polled for every signed-in user: what waits for the administrator (a badge in the
 * sidebar), and whether runs are paused because Docker is not working (a banner on every page). */
class System {
  status = $state<SystemStatus | null>(null)

  pendingAccess = $derived(this.status?.pending_access_requests ?? 0)
  // null until the first answer, so the banner never flashes while the page loads
  cellsReady = $derived(this.status === null ? true : this.status.cells_ready)
  problems = $derived(this.status?.problems ?? [])

  async refresh() {
    try {
      this.status = await api.systemStatus()
    } catch {
      // transient: the next poll retries
    }
  }
}

export const system = new System()
