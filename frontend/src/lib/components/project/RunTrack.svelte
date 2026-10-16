<script lang="ts">
	import { api, type WorkflowRunDetail } from '$lib/api'
	import { stageTrack, type TrackNode, type TrackState } from '$lib/stageTrack'
	import { cn } from '$lib/utils'
	import BanIcon from '@lucide/svelte/icons/ban'
	import ChevronRightIcon from '@lucide/svelte/icons/chevron-right'
	import CircleCheckIcon from '@lucide/svelte/icons/circle-check'
	import CircleXIcon from '@lucide/svelte/icons/circle-x'
	import HourglassIcon from '@lucide/svelte/icons/hourglass'
	import LoaderCircleIcon from '@lucide/svelte/icons/loader-circle'
	import { onMount, untrack } from 'svelte'

	// Where one workflow run is: the node before, the node now, and what may come next (one under the other when it
	// branches). It fetches the run itself and keeps it fresh while it is going, so a card or a panel only names the run.
	// `compact` is for a board card: smaller chips, and it wraps and drops the node before when there is little room.
	let {
		runId,
		compact = false,
		detail = $bindable(),
	}: { runId: number; compact?: boolean; detail?: WorkflowRunDetail | null } = $props()

	const chip: Record<TrackState, string> = {
		done: 'border-emerald-400/40',
		running: 'border-primary bg-primary/10 ring-1 ring-primary/40',
		waiting: 'border-amber-400/60 bg-amber-500/10',
		failed: 'border-destructive/60 text-destructive',
		cancelled: 'text-muted-foreground',
		upcoming: 'border-dashed text-muted-foreground',
		skipped: 'border-dashed text-muted-foreground opacity-40',
	}
	const chipIcon: Partial<Record<TrackState, typeof CircleCheckIcon>> = {
		done: CircleCheckIcon,
		running: LoaderCircleIcon,
		waiting: HourglassIcon,
		failed: CircleXIcon,
		cancelled: BanIcon,
	}
	const chipTone: Partial<Record<TrackState, string>> = { done: 'text-emerald-400', running: 'text-primary', waiting: 'text-amber-400' }

	async function load(id: number) {
		try {
			const fresh = await api.workflowRun(id)
			if (id === runId) detail = fresh // a slow answer for a run that is no longer the one shown is dropped
		} catch {
			// transient: the next poll retries
		}
	}

	// A new run is a new track. But the board hands its tasks over as new objects every few seconds, and that re-runs
	// this effect with the same run: starting over then would swap the track for the loading state for a moment, and
	// the card would flinch. So only a different run resets what is shown.
	let shownRun: number | null = null
	$effect(() => {
		const id = runId
		untrack(() => {
			if (id === shownRun) return
			shownRun = id
			detail = null
			load(id)
		})
	})
	onMount(() => {
		const timer = setInterval(() => {
			if (!document.hidden && (!detail || detail.status === 'running')) load(runId)
		}, 1000)
		return () => clearInterval(timer)
	})

	const track = $derived(detail ? stageTrack(detail.graph, detail.nodes, detail.status) : null)
	const multi = $derived((track?.next.length ?? 0) > 1)
</script>

{#snippet node(n: TrackNode, iconOnly = false)}
	{@const Icon = chipIcon[n.state]}
	{#if iconOnly && Icon}
		<!-- on a card the node before is only a dot: it is done and out of the way, the name is on hover -->
		<span class={cn('inline-flex shrink-0 rounded-full border bg-card p-0.5', chip[n.state])} title="{n.label} ({n.state})">
			<Icon class={cn('size-3', chipTone[n.state])} />
		</span>
	{:else}
	<span
		class={cn(
			'inline-flex min-w-0 items-center gap-1 rounded-md border bg-card',
			compact ? 'max-w-28 px-1.5 py-0.5 text-[0.7rem]' : 'max-w-40 px-2 py-1 text-xs',
			chip[n.state]
		)}
		title="{n.label} ({n.state})"
	>
		{#if Icon}<Icon class={cn('size-3 shrink-0', chipTone[n.state], n.state === 'running' && 'animate-spin')} />{/if}
		<span class="truncate">{n.label}</span>
	</span>
	{/if}
{/snippet}

{#snippet sep()}<ChevronRightIcon class="size-3 shrink-0 text-muted-foreground" />{/snippet}

{#if track}
	<!-- Each part carries its own separator, so when the row wraps in a narrow card nothing dangles at a line end. -->
	<div class="@container/track flex flex-wrap items-center gap-x-1 gap-y-1">
		{#if track.previous}
			<span class="inline-flex max-w-full min-w-0 @max-[11rem]/track:hidden">{@render node(track.previous, compact)}</span>
		{/if}
		{#if track.current}
			<span class="inline-flex max-w-full min-w-0 items-center gap-1">
				{#if track.previous}<span class="@max-[11rem]/track:hidden">{@render sep()}</span>{/if}
				{@render node(track.current)}
			</span>
		{/if}
		{#if track.next.length}
			<span class="inline-flex max-w-full min-w-0 items-center gap-1">
				{#if track.current}{@render sep()}{/if}
				<!-- one way on: just the node. Several: one under the other, each tied to a rail with the answer that leads there -->
				<span class={cn('flex max-w-full min-w-0 flex-col gap-1', multi && 'border-s ps-2')}>
					{#each track.next as o (o.node.id)}
						<span
							class={cn(
								'relative flex max-w-full min-w-0 items-center gap-1',
								multi && 'before:absolute before:top-1/2 before:-start-2 before:h-px before:w-2 before:bg-border'
							)}
						>
							{#if o.via}<span class="shrink-0 text-[0.6rem] text-muted-foreground uppercase">{o.via}</span>{/if}
							{@render node(o.node)}
						</span>
					{/each}
				</span>
			</span>
		{/if}
	</div>
{:else}
	<!-- while the run is fetched: a chip of the same size as the track's, so nothing below it moves when it arrives -->
	<div class="flex items-center gap-1">
		{@render node({ id: 'loading', label: '...', kind: 'start', state: 'upcoming' })}
	</div>
{/if}
