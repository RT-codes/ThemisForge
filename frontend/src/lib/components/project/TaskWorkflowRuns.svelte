<script lang="ts">
	import { api, type RunStatus, type TaskWorkflowRunSummary } from '$lib/api'
	import { dateTime } from '$lib/format'
	import { cn } from '$lib/utils'
	import WorkflowIcon from '@lucide/svelte/icons/workflow'
	import { onMount } from 'svelte'

	let { taskId, projectId, taskStatus }: { taskId: number; projectId: number; taskStatus: string } = $props()

	let runs = $state<TaskWorkflowRunSummary[]>([])

	async function load() {
		try {
			runs = await api.taskWorkflowRuns(taskId)
		} catch {
			// transient: the next poll retries
		}
	}

	const tone: Record<RunStatus, string> = {
		running: 'text-primary',
		succeeded: 'text-emerald-400',
		failed: 'text-destructive',
		cancelled: 'text-muted-foreground',
	}

	onMount(() => {
		load()
		const timer = setInterval(() => !document.hidden && runs[0]?.status === 'running' && load(), 1500)
		return () => clearInterval(timer)
	})

	// the task moved: a workflow may just have started because of it
	let lastStatus: string | undefined
	$effect(() => {
		const status = taskStatus
		if (lastStatus !== undefined && status !== lastStatus) load()
		lastStatus = status
	})
</script>

{#if runs.length}
	<div class="grid gap-1 px-4 pb-3">
		<h4 class="text-xs font-medium tracking-wide text-muted-foreground uppercase">Workflows this task started</h4>
		<ul class="grid gap-1">
			{#each runs as r (r.id)}
				<li>
					<a
						href="/projects/{projectId}/workflows/{r.workflow_id}/runs/{r.id}"
						class="flex items-center gap-2 rounded-lg border bg-card px-3 py-2 text-sm transition-colors hover:border-primary/40"
					>
						<WorkflowIcon class="size-4 shrink-0 text-primary" />
						<span class="min-w-0 flex-1 truncate">{r.workflow_name} <span class="text-muted-foreground">· {dateTime(r.started_at)}</span></span>
						<span class={cn('shrink-0 text-xs capitalize', tone[r.status])}>{r.status}</span>
					</a>
				</li>
			{/each}
		</ul>
	</div>
{/if}
