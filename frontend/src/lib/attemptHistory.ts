import type { Attempt, AttemptDetail } from './api.ts'

export interface AttemptHistoryState {
  attempts: Attempt[]
  loaded: boolean
  loading: boolean
  error: boolean
  selectedId: number | null
  detail: AttemptDetail | null
  detailLoading: boolean
  detailError: boolean
}

export function emptyAttemptHistory(): AttemptHistoryState {
  return {
    attempts: [], loaded: false, loading: false, error: false,
    selectedId: null, detail: null, detailLoading: false, detailError: false,
  }
}

export function createAttemptHistory(
  taskId: number,
  api: { attempts: (id: number) => Promise<Attempt[]>; attempt: (id: number) => Promise<AttemptDetail> },
  update: (state: AttemptHistoryState) => void,
) {
  let state = emptyAttemptHistory()
  let active = true
  let detailRequest = 0

  function set(patch: Partial<AttemptHistoryState>) {
    if (!active) return
    state = { ...state, ...patch }
    update(state)
  }

  async function select(id: number) {
    if (!active) return
    const request = ++detailRequest
    set({ selectedId: id, detail: null, detailLoading: true, detailError: false })
    await fetchDetail(id, request)
  }

  async function fetchDetail(id: number, request: number) {
    try {
      const detail = await api.attempt(id)
      if (request === detailRequest) set({ detail, detailError: false })
    } catch {
      if (request === detailRequest) set({ detail: null, detailError: true })
    } finally {
      if (request === detailRequest) set({ detailLoading: false })
    }
  }

  async function load() {
    if (!active || state.loading) return
    set({ loading: true })
    try {
      const attempts = await api.attempts(taskId)
      if (!active) return
      set({ attempts, loaded: true, error: false })
      if (state.selectedId === null && attempts.length) {
        await select(attempts[0].id)
      } else if (state.selectedId !== null && !state.detailLoading) {
        // Polls keep the current result visible, but cannot replace a newer selection.
        await fetchDetail(state.selectedId, ++detailRequest)
      }
    } catch {
      set({ error: true })
    } finally {
      set({ loading: false })
    }
  }

  return { load, select, dispose: () => { active = false; detailRequest++ } }
}
