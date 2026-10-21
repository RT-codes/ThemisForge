<script lang="ts">
	import type { TaskStage } from '$lib/api/tasks'
	import { STAGE_LABEL, STAGE_TONE, cardStages } from '$lib/stageTrack'
	import { cn } from '$lib/utils'
	import RunTrack from './RunTrack.svelte'
	import StageIcon from './StageIcon.svelte'

	// What a board card shows of a task's stages, under a divider: finished ones folded into a count, then the one that
	// is going (with where it is in its workflow), then what is still to come. Kept short so a small card stays small.
	// `expanded`: the card is selected and unfolded, so every stage is listed, finished ones too
	let { stages, expanded = false }: { stages: TaskStage[]; expanded?: boolean } = $props()

	const view = $derived(expanded ? { done: 0, shown: stages, more: 0 } : cardStages(stages))
</script>

<div class="@container/stages mt-2 grid grid-cols-[minmax(0,1fr)] gap-1 border-t pt-2 text-xs" aria-label="Stages">
	{#if view.done > 0}
		<p class="flex items-center gap-1.5 text-muted-foreground">
			<StageIcon status="succeeded" class="size-3.5" />
			<span class="min-w-0 truncate">
				{#if view.shown.length === 0}All {view.done === 1 ? 'stage' : `${view.done} stages`} done{:else}{view.done} done{/if}
			</span>
		</p>
	{/if}
	{#each view.shown as s, i (i)}
		<div class="grid grid-cols-[minmax(0,1fr)] gap-1">
			<p class="flex items-center gap-1.5">
				<!-- still: the card already spins on the task and on the node that is playing, a third one is noise -->
				<StageIcon status={s.status} still class="size-3.5" />
				<span class={cn('min-w-0 flex-1 truncate', s.status === 'pending' && 'text-muted-foreground')} title={s.workflow_name}>
					{s.workflow_name}
				</span>
				<!-- a stage that has not started needs no word: the dashed icon and the dimmed name say it. Little room: no words. -->
				{#if s.status !== 'pending'}
					<span class={cn('shrink-0 @max-[12rem]/stages:hidden', STAGE_TONE[s.status])}>{STAGE_LABEL[s.status]}</span>
				{/if}
			</p>
			{#if s.status === 'running' && s.run_id}
				<div class="ps-5"><RunTrack runId={s.run_id} compact /></div>
			{/if}
		</div>
	{/each}
	{#if view.more > 0}
		<p class="ps-5 text-muted-foreground">+{view.more} more</p>
	{/if}
</div>
