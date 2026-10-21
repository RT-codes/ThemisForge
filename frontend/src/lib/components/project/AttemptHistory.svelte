<script lang="ts">
	import { tasksApi, type AttemptStatus } from '$lib/api/tasks'
	import { attemptLabel, dateTime, duration } from '$lib/format'
	import LogPanel from '$lib/components/LogPanel.svelte'
	import FailureNote from './FailureNote.svelte'
	import ResultView from '$lib/components/ResultView.svelte'
	import { cn } from '$lib/utils'
	import { Button } from '$lib/components/ui/button/index.js'
	import { createAttemptHistory, initialAttemptHistory } from './attemptHistory'
	import CircleCheckIcon from '@lucide/svelte/icons/circle-check'
	import CircleXIcon from '@lucide/svelte/icons/circle-x'
	import LoaderCircleIcon from '@lucide/svelte/icons/loader-circle'
	import WorkflowIcon from '@lucide/svelte/icons/workflow'
	import BanIcon from '@lucide/svelte/icons/ban'
	import { onMount } from 'svelte'

	let { taskId, taskStatus, projectId }: { taskId: number; taskStatus: string; projectId: number } = $props()

	let history = $state(initialAttemptHistory)
	const controller = createAttemptHistory(() => taskId, tasksApi, (next) => (history = next))

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

	onMount(() => {
		controller.load()
		const timer = setInterval(() => {
			if (!document.hidden && (taskStatus === 'running' || history.attempts[0]?.status === 'running')) controller.load()
		}, 1500)
		return () => { clearInterval(timer); controller.dispose() }
	})

	// a finished run: fetch once more so the final status and log show up
	let lastStatus: string | undefined
	$effect(() => {
		const status = taskStatus
		if (lastStatus !== undefined && status !== lastStatus) controller.load()
		lastStatus = status
	})
</script>

{#if !history.loaded}
	<p class="px-4 py-6 text-sm text-muted-foreground">Loading...</p>
{:else if history.listError && history.attempts.length === 0}
	<div class="px-4 py-8 text-center" role="alert">
		<p class="text-sm text-destructive">Could not load attempts.</p>
		<Button variant="outline" size="sm" class="mt-3" disabled={history.listLoading} onclick={() => controller.load()}>Retry</Button>
	</div>
{:else if history.attempts.length === 0}
	<div class="px-4 py-10 text-center">
		<p class="text-sm font-medium">No attempts yet</p>
		<p class="mt-1 text-xs text-muted-foreground">Each time a cell works on this task, it is recorded here with its log and result.</p>
	</div>
{:else}
	<div class="grid gap-3 px-4 pb-4">
		{#if history.listError}
			<div class="flex flex-wrap items-center justify-between gap-2 rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive" role="alert">
				<span>Could not refresh attempts. Showing the last loaded list.</span>
				<Button variant="outline" size="sm" disabled={history.listLoading} onclick={() => controller.load()}>Retry</Button>
			</div>
		{/if}
		<ul class="grid gap-1">
			{#each history.attempts as a (a.id)}
				{@const Icon = icons[a.status]}
				<li>
					<button
						type="button"
						onclick={() => controller.select(a.id)}
						class={cn(
							'flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-start text-sm transition-colors hover:bg-accent',
							history.selectedId === a.id && 'bg-accent'
						)}
					>
						<Icon class={cn('size-4 shrink-0', tone[a.status], a.status === 'running' && 'animate-spin')} />
						<span class="font-medium">{attemptLabel[a.status]}</span>
						<span class="truncate text-xs text-muted-foreground">{dateTime(a.started_at)}</span>
						<span class="ms-auto text-xs text-muted-foreground tabular-nums">
							{duration(a.started_at, a.finished_at ?? new Date(history.tick).toISOString())}
						</span>
					</button>
				</li>
			{/each}
		</ul>

		{#if history.detailLoading && !history.detail}
			<p class="text-sm text-muted-foreground" role="status">Loading attempt...</p>
		{/if}
		{#if history.detailError}
			<div class="flex flex-wrap items-center justify-between gap-2 rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive" role="alert">
				<span>{history.detail ? 'Could not refresh this attempt. Showing the last loaded result.' : 'Could not load this attempt.'}</span>
				<Button variant="outline" size="sm" disabled={history.detailLoading} onclick={() => history.selectedId !== null && controller.select(history.selectedId)}>Retry</Button>
			</div>
		{/if}
		{#if history.detail && history.detail.id === history.selectedId}
			{@const detail = history.detail}
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
