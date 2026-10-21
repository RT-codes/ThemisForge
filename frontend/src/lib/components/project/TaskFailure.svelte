<script lang="ts">
	import { tasksApi, type AttemptFailure } from '$lib/api/tasks'
	import FailureNote from './FailureNote.svelte'

	// Why the task's latest attempt failed, shown above the tabs of the details so it is the first thing seen on a failed
	// card. The card only carries the one-line reason; this fetches the rest (what to do, the end of the log).
	let { taskId, attemptStatus, reason }: { taskId: number; attemptStatus: string | null; reason: string } = $props()

	let failure = $state<AttemptFailure | null>(null)

	$effect(() => {
		// reason is read so a new failure of the same task is fetched again
		reason
		failure = null
		if (attemptStatus !== 'failed') return
		let current = true
		tasksApi.attempts(taskId)
			.then((list) => (list.length ? tasksApi.attempt(list[0].id) : null))
			.then((detail) => {
				if (current && detail?.status === 'failed') failure = detail.failure
			})
			.catch(() => {
				// the card still has the reason, and the History tab has the log
			})
		return () => (current = false)
	})
</script>

{#if failure}
	<div class="mx-4 mb-3"><FailureNote {failure} /></div>
{/if}
