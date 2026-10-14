<script lang="ts">
	import { api, type AttemptStatus } from '$lib/api'
	import { attemptLabel, dateTime, duration } from '$lib/format'
	import LogPanel from '$lib/components/LogPanel.svelte'
	import FailureNote from './FailureNote.svelte'
	import ResultView from '$lib/components/ResultView.svelte'
	import { cn } from '$lib/utils'
	import CircleCheckIcon from '@lucide/svelte/icons/circle-check'
	import CircleXIcon from '@lucide/svelte/icons/circle-x'
	import LoaderCircleIcon from '@lucide/svelte/icons/loader-circle'
	import WorkflowIcon from '@lucide/svelte/icons/workflow'
	import BanIcon from '@lucide/svelte/icons/ban'
	import { createAttemptHistory, emptyAttemptHistory } from '$lib/attemptHistory'
	import Button from '$lib/components/ui/button/button.svelte'

	let { taskId, taskStatus, projectId }: { taskId: number; taskStatus: string; projectId: number } = $props()

	let history = $state(emptyAttemptHistory())
	let loader: ReturnType<typeof createAttemptHistory> | undefined
	const attempts = $derived(history.attempts)
	const selectedId = $derived(history.selectedId)
	const detail = $derived(history.detail)
	let tick = $state(Date.now())

	const icons: Record<AttemptStatus, typeof CircleCheckIcon> = {
		running: LoaderCircleIcon,
		succeeded: CircleCheckIcon,
		failed: CircleXIcon,
		cancelled: BanIcon,
	}
	const tone: Record<AttemptStatus, string> = {
		running: 'text-primary',
		succeeded: 'text-emerald-400',
		failed: 'text-destructive',
		cancelled: 'text-muted-foreground',
	}

	$effect(() => {
		const id = taskId
		history = emptyAttemptHistory()
		const current = createAttemptHistory(id, api, (state) => {
			history = state
			tick = Date.now()
		})
		loader = current
		current.load()
		const timer = setInterval(() => {
			if (!document.hidden && (taskStatus === 'running' || attempts[0]?.status === 'running')) current.load()
		}, 1500)
		return () => {
			clearInterval(timer)
			current.dispose()
		}
	})

	// a finished run: fetch once more so the final status and log show up
	let lastStatus: string | undefined
	$effect(() => {
		const status = taskStatus
		if (lastStatus !== undefined && status !== lastStatus) loader?.load()
		lastStatus = status
	})
</script>

{#if history.error}
	<div class="mx-4 mb-3 flex flex-wrap items-center gap-3 rounded-lg border border-destructive/30 bg-destructive/5 px-3 py-3">
		<div class="min-w-0 flex-1" role="alert">
			<p class="text-sm font-medium">Could not load history</p>
			<p class="mt-1 text-xs text-muted-foreground">Try again to see this task's attempts.</p>
		</div>
		<Button variant="outline" size="sm" disabled={history.loading} onclick={() => loader?.load()}>
			{history.loading ? 'Retrying...' : 'Retry'}
		</Button>
	</div>
{/if}

{#if !history.loaded && !history.error}
	<p class="px-4 py-6 text-sm text-muted-foreground">Loading...</p>
{:else if history.loaded && !history.error && attempts.length === 0}
	<div class="px-4 py-10 text-center">
		<p class="text-sm font-medium">No attempts yet</p>
		<p class="mt-1 text-xs text-muted-foreground">Each time a cell works on this task, it is recorded here with its log and result.</p>
	</div>
{:else if attempts.length}
	<div class="grid gap-3 px-4 pb-4">
		<ul class="grid gap-1">
			{#each attempts as a (a.id)}
				{@const Icon = icons[a.status]}
				<li>
					<button
						type="button"
						onclick={() => loader?.select(a.id)}
						aria-pressed={selectedId === a.id}
						class={cn(
							'flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-start text-sm transition-colors hover:bg-accent',
							selectedId === a.id && 'bg-accent'
						)}
					>
						<Icon class={cn('size-4 shrink-0', tone[a.status], a.status === 'running' && 'animate-spin')} />
						<span class="font-medium">{attemptLabel[a.status]}</span>
						<span class="truncate text-xs text-muted-foreground">{dateTime(a.started_at)}</span>
						<span class="ms-auto text-xs text-muted-foreground tabular-nums">
							{duration(a.started_at, a.finished_at ?? new Date(tick).toISOString())}
						</span>
					</button>
				</li>
			{/each}
		</ul>

		{#if history.detailLoading}
			<p class="flex items-center gap-2 py-4 text-sm text-muted-foreground" role="status">
				<LoaderCircleIcon class="size-4 animate-spin" /> Loading attempt...
			</p>
		{:else if history.detailError}
			<div class="flex flex-wrap items-center gap-3 rounded-lg border border-destructive/30 bg-destructive/5 px-3 py-3">
				<p class="min-w-0 flex-1 text-sm font-medium" role="alert">Could not load this attempt's result and log</p>
				<Button variant="outline" size="sm" onclick={() => selectedId !== null && loader?.select(selectedId)}>Retry</Button>
			</div>
		{:else if detail}
			{#if detail.workflow_run_id && detail.workflow_id}
				<a
					href="/projects/{projectId}/workflows/{detail.workflow_id}/runs/{detail.workflow_run_id}"
					class="flex items-center gap-2 rounded-lg border bg-card px-3 py-2 text-sm transition-colors hover:border-primary/40"
				>
					<WorkflowIcon class="size-4 shrink-0 text-primary" />
					<span class="min-w-0 flex-1 truncate">Played workflow run #{detail.workflow_run_id}</span>
					<span class="shrink-0 text-xs text-primary">See every node</span>
				</a>
			{/if}
			{#if detail.failure}
				<FailureNote failure={detail.failure} />
			{/if}
			{#if detail.result}
				{#key detail.id}
					<ResultView text={detail.result} />
				{/key}
			{/if}
			<div>
				<h4 class="mb-1 text-xs font-medium tracking-wide text-muted-foreground uppercase">
					Log{detail.exit_code !== null ? ` (exit code ${detail.exit_code})` : ''}
				</h4>
				<LogPanel
					text={detail.log}
					title={`Log - ${attemptLabel[detail.status].toLowerCase()}`}
					subtitle={`${dateTime(detail.started_at)}${detail.exit_code !== null ? ` · exit code ${detail.exit_code}` : ''}`}
				/>
			</div>
		{/if}
	</div>
{/if}
