import { api } from './api'

/** Things waiting for the administrator (shown as a badge in the sidebar). */
class Inbox {
  pendingAccess = $state(0)

  async refresh() {
    try {
      this.pendingAccess = (await api.systemStatus()).pending_access_requests
    } catch {
      // transient: the next poll retries
    }
  }
}

export const inbox = new Inbox()
