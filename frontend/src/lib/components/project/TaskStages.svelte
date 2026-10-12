<script lang="ts">
	import type { TaskStage, WorkflowRunDetail } from '$lib/api'
	import { duration } from '$lib/format'
	import { STAGE_LABEL, STAGE_TONE } from '$lib/stageTrack'
	import { cn } from '$lib/utils'
	import ChevronRightIcon from '@lucide/svelte/icons/chevron-right'
	import RunTrack from './RunTrack.svelte'
	import StageIcon from './StageIcon.svelte'

	// The workflows a task plays, in order, each with where it is. A stage that has started unfolds into its track.
	let { stages, projectId }: { stages: TaskStage[]; projectId: number } = $props()

	// what the person chose to open or close; a stage nobody touched is open while it is running
	let chosen = $state<Record<number, boolean>>({})
	// the run each open stage is showing, for its duration (RunTrack fetches and refreshes it)
	let details = $state<Record<number, WorkflowRunDetail | null>>({})

	const isOpen = (i: number) => chosen[i] ?? stages[i].status === 'running'
	// a loaded run is fresher than the task, which only changes when the board next refreshes
	const statusOf = (s: TaskStage) => (s.run_id && details[s.run_id]?.status) || s.status
</script>

<div class="grid grid-cols-[minmax(0,1fr)] gap-1 px-4 pb-4">
	<h4 class="text-xs font-medium tracking-wide text-muted-foreground uppercase">Stages</h4>
	<ol class="grid grid-cols-[minmax(0,1fr)] gap-1">
		{#each stages as s, i (i)}
			{@const status = statusOf(s)}
			{@const detail = s.run_id ? details[s.run_id] : null}
			<li class={cn('rounded-lg border bg-card text-sm', status === 'running' && 'border-primary/40')}>
				{#snippet head()}
					<StageIcon {status} class="size-4" />
					<span class={cn('min-w-0 flex-1 truncate', status === 'pending' && 'text-muted-foreground')}>{s.workflow_name}</span>
					<span class={cn('shrink-0 text-xs', STAGE_TONE[status])}>
						{STAGE_LABEL[status]}{detail?.finished_at ? ` · ${duration(detail.started_at, detail.finished_at)}` : ''}
					</span>
				{/snippet}
				<!-- a stage that has not started has nothing to unfold, so it is not a button -->
				{#if s.run_id}
					<button
						type="button"
						aria-expanded={isOpen(i)}
						class="flex w-full cursor-pointer items-center gap-2 px-3 py-2 text-start"
						onclick={() => (chosen[i] = !isOpen(i))}
					>
						{@render head()}
						<ChevronRightIcon class={cn('size-4 shrink-0 text-muted-foreground transition-transform', isOpen(i) && 'rotate-90')} />
					</button>
				{:else}
					<div class="flex w-full items-center gap-2 px-3 py-2">{@render head()}</div>
				{/if}

				{#if s.run_id}
					<!-- always mounted so the run is known (and its duration shown) while the stage is folded; hidden then -->
					<div class={cn('border-t px-3 py-2', !isOpen(i) && 'hidden')}>
						<RunTrack runId={s.run_id} bind:detail={details[s.run_id]} />
						<a
							href="/projects/{projectId}/workflows/{s.workflow_id}/runs/{s.run_id}"
							class="mt-1 inline-block text-xs text-muted-foreground hover:text-primary hover:underline"
						>
							Run details
						</a>
					</div>
				{/if}
			</li>
		{/each}
	</ol>
</div>
