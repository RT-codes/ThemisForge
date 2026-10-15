import type { Attempt, AttemptDetail } from '$lib/api'

export interface AttemptHistoryState {
	attempts: Attempt[]
	loaded: boolean
	listLoading: boolean
	listError: boolean
	selectedId: number | null
	detail: AttemptDetail | null
	detailLoading: boolean
	detailError: boolean
	tick: number
}

export const initialAttemptHistory: AttemptHistoryState = {
	attempts: [],
	loaded: false,
	listLoading: false,
	listError: false,
	selectedId: null,
	detail: null,
	detailLoading: false,
	detailError: false,
	tick: Date.now(),
}

export function createAttemptHistory(
	taskId: () => number,
	requests: { attempts: (taskId: number) => Promise<Attempt[]>; attempt: (id: number) => Promise<AttemptDetail> },
	onChange: (state: AttemptHistoryState) => void,
) {
	let state = { ...initialAttemptHistory }
	let listRequest = 0
	let detailRequest = 0
	let active = true

	function update(patch: Partial<AttemptHistoryState>) {
		if (!active) return
		state = { ...state, ...patch }
		onChange(state)
	}

	async function select(id: number) {
		const request = ++detailRequest
		// A refresh can keep the selected result visible; a different selection cannot.
		update({ selectedId: id, detail: state.selectedId === id ? state.detail : null, detailLoading: true, detailError: false })
		try {
			const detail = await requests.attempt(id)
			if (active && request === detailRequest && state.selectedId === id) {
				update({ detail, detailLoading: false })
			}
		} catch {
			if (active && request === detailRequest && state.selectedId === id) {
				update({ detailLoading: false, detailError: true })
			}
		}
	}

	async function load() {
		if (state.listLoading) return
		const request = ++listRequest
		update({ listLoading: true, listError: false })
		try {
			const attempts = await requests.attempts(taskId())
			if (!active || request !== listRequest) return
			const selectedId = attempts.some((attempt) => attempt.id === state.selectedId)
				? state.selectedId
				: (attempts[0]?.id ?? null)
			update({ attempts, loaded: true, listLoading: false, tick: Date.now() })
			if (selectedId === null) {
				++detailRequest
				update({ selectedId: null, detail: null, detailLoading: false, detailError: false })
			} else {
				await select(selectedId)
			}
		} catch {
			if (active && request === listRequest) {
				update({ loaded: true, listLoading: false, listError: true, tick: Date.now() })
			}
		}
	}

	return {
		get state() { return state },
		load,
		select,
		dispose() { active = false; ++listRequest; ++detailRequest },
	}
}
