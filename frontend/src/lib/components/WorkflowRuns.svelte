<script lang="ts">
	import { api, ApiError, type NodeRun, type NodeRunStatus, type RunStatus, type WorkflowRunDetail, type WorkflowRunSummary } from '$lib/api'
	import LogPanel from '$lib/components/LogPanel.svelte'
	import { Button } from '$lib/components/ui/button/index.js'
	import { dateTime, duration, relative } from '$lib/format'
	import { cn } from '$lib/utils'
	import { nodeIcons } from '$lib/workflowIcons'
	import BanIcon from '@lucide/svelte/icons/ban'
	import ChevronDownIcon from '@lucide/svelte/icons/chevron-down'
	import CircleCheckIcon from '@lucide/svelte/icons/circle-check'
	import CircleDashedIcon from '@lucide/svelte/icons/circle-dashed'
	import CircleXIcon from '@lucide/svelte/icons/circle-x'
	import LoaderCircleIcon from '@lucide/svelte/icons/loader-circle'
	import { onMount } from 'svelte'
	import { SvelteSet } from 'svelte/reactivity'
	import { slide } from 'svelte/transition'

	let { workflowId, selected = $bindable(null) }: { workflowId: number; selected?: number | null } = $props()

	let runs = $state<WorkflowRunSummary[]>([])
	let loaded = $state(false)
	let detail = $state<WorkflowRunDetail | null>(null)
	let now = $state(Date.now())
	let error = $state('')
	let cancelling = $state(false)
	const open = new SvelteSet<number>() // node records that are unfolded
	let autoOpened = new Set<number>() // failed nodes that were unfolded on their own, so the reader's own folding is left alone
	let autoOpenedFor: number | null = null

	const statusIcon: Record<NodeRunStatus, typeof CircleCheckIcon> = {
		running: LoaderCircleIcon,
		succeeded: CircleCheckIcon,
		failed: CircleXIcon,
		skipped: CircleDashedIcon,
		cancelled: BanIcon,
	}
	const statusTone: Record<NodeRunStatus, string> = {
		running: 'text-primary',
		succeeded: 'text-emerald-400',
		failed: 'text-destructive',
		skipped: 'text-muted-foreground/60',
		cancelled: 'text-muted-foreground',
	}
	const runLabel: Record<RunStatus, string> = { running: 'Running', succeeded: 'Succeeded', failed: 'Failed', cancelled: 'Cancelled' }
	const runTone: Record<RunStatus, string> = {
		running: 'bg-primary/15 text-primary',
		succeeded: 'bg-emerald-500/15 text-emerald-400',
		failed: 'bg-destructive/15 text-destructive',
		cancelled: 'bg-muted text-muted-foreground',
	}
	const runIcon: Record<RunStatus, typeof CircleCheckIcon> = { running: LoaderCircleIcon, succeeded: CircleCheckIcon, failed: CircleXIcon, cancelled: BanIcon }

	async function loadList() {
		try {
			runs = await api.workflowRuns(workflowId)
			if (selected === null && runs.length) selected = runs[0].id
		} catch (e) {
			error = e instanceof Error ? e.message : 'Could not load the runs'
		} finally {
			loaded = true
			now = Date.now()
		}
	}

	async function loadDetail(id: number) {
		try {
			const fresh = await api.workflowRun(id)
			if (selected !== id) return // the reader moved on while this was loading
			detail = fresh
			if (autoOpenedFor !== id) {
				autoOpenedFor = id
				autoOpened = new Set()
				open.clear()
			}
			// unfold what went wrong as soon as it happens, so the reason is right there
			for (const n of fresh.nodes) {
				if (n.status === 'failed' && !autoOpened.has(n.id)) {
					autoOpened.add(n.id)
					open.add(n.id)
				}
			}
		} catch {
			// transient: the next poll retries
		}
	}

	$effect(() => {
		if (selected !== null) loadDetail(selected)
		else detail = null
	})

	onMount(() => {
		loadList()
		const timer = setInterval(() => {
			if (document.hidden) return
			now = Date.now()
			if (runs.some((r) => r.status === 'running') || detail?.status === 'running') {
				loadList()
				if (selected !== null) loadDetail(selected)
			}
		}, 1200)
		return () => clearInterval(timer)
	})

	// a run that was just started is not in the list yet
	$effect(() => {
		if (selected !== null && loaded && !runs.some((r) => r.id === selected)) loadList()
	})

	async function cancel() {
		if (!detail) return
		cancelling = true
		try {
			detail = await api.cancelWorkflowRun(detail.id)
			await loadList()
		} catch (e) {
			error = e instanceof ApiError || e instanceof Error ? e.message : 'Could not cancel'
		} finally {
			cancelling = false
		}
	}

	const toggle = (id: number) => (open.has(id) ? open.delete(id) : open.add(id))
	const end = (n: { finished_at: string | null }) => n.finished_at ?? new Date(now).toISOString()
	const ran = $derived(detail?.nodes.filter((n) => n.status !== 'skipped') ?? [])
	const notRun = $derived(detail?.nodes.filter((n) => n.status === 'skipped') ?? [])

	function reasonTitle(n: NodeRun) {
		return n.status === 'failed' ? 'What went wrong' : n.status === 'skipped' ? 'Why it did not run' : 'What happened'
	}
</script>

<div class="flex min-h-0 flex-1">
	<aside class="flex w-72 shrink-0 flex-col overflow-y-auto border-e p-2">
		<p class="px-2 pb-1.5 text-xs font-medium tracking-wide text-muted-foreground uppercase">Runs</p>
		{#if !loaded}
			<p class="px-2 text-sm text-muted-foreground">Loading...</p>
		{:else if runs.length === 0}
			<div class="px-3 py-8 text-center">
				<p class="text-sm font-medium">No runs yet</p>
				<p class="mt-1 text-xs text-muted-foreground">Press Test run in the editor. Every run is kept here with the log of each node.</p>
			</div>
		{:else}
			<ul class="grid gap-1">
				{#each runs as r (r.id)}
					{@const Icon = runIcon[r.status]}
					<li>
						<button
							type="button"
							onclick={() => (selected = r.id)}
							class={cn('flex w-full items-center gap-2.5 rounded-md px-2.5 py-2 text-start transition-colors hover:bg-accent', selected === r.id && 'bg-accent')}
						>
							<Icon class={cn('size-4 shrink-0', runTone[r.status].split(' ')[1], r.status === 'running' && 'animate-spin')} />
							<div class="min-w-0 flex-1">
								<p class="text-sm font-medium">Run #{r.id}</p>
								<p class="truncate text-xs text-muted-foreground">{relative(r.started_at, now)} · {duration(r.started_at, r.finished_at ?? new Date(now).toISOString())}</p>
							</div>
							<span class="shrink-0 text-xs text-muted-foreground tabular-nums" title="Nodes that succeeded">{r.nodes_succeeded}/{r.nodes_total}</span>
						</button>
					</li>
				{/each}
			</ul>
		{/if}
	</aside>

	<div class="min-w-0 flex-1 overflow-y-auto">
		{#if error}<p class="m-4 text-sm text-destructive" role="alert">{error}</p>{/if}
		{#if detail}
			{#key detail.id}
				<div class="mx-auto grid max-w-3xl gap-5 px-6 py-6">
					<div class="flex flex-wrap items-center gap-3">
						<h3 class="text-lg font-semibold tracking-tight">Run #{detail.id}</h3>
						<span class={cn('rounded-full px-2.5 py-0.5 text-xs font-medium', runTone[detail.status])}>{runLabel[detail.status]}</span>
						<span class="text-sm text-muted-foreground">{dateTime(detail.started_at)} · {duration(detail.started_at, end(detail))}</span>
						{#if detail.status === 'running'}
							<Button variant="outline" size="sm" class="ms-auto" disabled={cancelling} onclick={cancel}>Cancel run</Button>
						{/if}
					</div>
					{#if detail.outcome}
						<p class={cn('rounded-lg border px-3 py-2 text-sm', detail.status === 'failed' ? 'border-destructive/30 bg-destructive/5' : 'bg-card')}>{detail.outcome}</p>
					{/if}

					<ol class="grid gap-1">
						{#each ran as n, i (n.id)}
							{@const Icon = statusIcon[n.status]}
							{@const KindIcon = nodeIcons[n.kind]}
							<li class="relative">
								{#if i < ran.length - 1 || notRun.length}
									<span class="absolute start-[21px] top-10 -bottom-1 w-px bg-border" aria-hidden="true"></span>
								{/if}
								<button
									type="button"
									onclick={() => toggle(n.id)}
									aria-expanded={open.has(n.id)}
									class="flex w-full items-center gap-3 rounded-lg px-2.5 py-2 text-start transition-colors hover:bg-accent/60"
								>
									<Icon class={cn('size-[22px] shrink-0', statusTone[n.status], n.status === 'running' && 'animate-spin')} />
									<span class="flex size-6 shrink-0 items-center justify-center rounded bg-primary/15 text-primary"><KindIcon class="size-3.5" /></span>
									<span class="min-w-0 flex-1">
										<span class="block truncate text-sm font-medium">{n.label}</span>
										<span class="block text-xs text-muted-foreground capitalize">{n.kind}{n.status === 'failed' ? ' · failed' : n.status === 'cancelled' ? ' · cancelled' : ''}</span>
									</span>
									{#if n.started_at}<span class="shrink-0 text-xs text-muted-foreground tabular-nums">{duration(n.started_at, end(n))}</span>{/if}
									<ChevronDownIcon class={cn('size-4 shrink-0 text-muted-foreground transition-transform duration-200', open.has(n.id) && 'rotate-180')} />
								</button>
								{#if open.has(n.id)}
									{@render details(n)}
								{/if}
							</li>
						{/each}
					</ol>

					{#if notRun.length}
						<div>
							<p class="mb-1 px-2.5 text-xs font-medium tracking-wide text-muted-foreground uppercase">Did not run</p>
							<ol class="grid gap-1">
								{#each notRun as n (n.id)}
									{@const KindIcon = nodeIcons[n.kind]}
									<li>
										<button type="button" onclick={() => toggle(n.id)} aria-expanded={open.has(n.id)} class="flex w-full items-center gap-3 rounded-lg px-2.5 py-2 text-start opacity-70 transition-colors hover:bg-accent/60 hover:opacity-100">
											<CircleDashedIcon class="size-[22px] shrink-0 text-muted-foreground/60" />
											<span class="flex size-6 shrink-0 items-center justify-center rounded bg-muted text-muted-foreground"><KindIcon class="size-3.5" /></span>
											<span class="min-w-0 flex-1 truncate text-sm">{n.label}</span>
											<ChevronDownIcon class={cn('size-4 shrink-0 text-muted-foreground transition-transform duration-200', open.has(n.id) && 'rotate-180')} />
										</button>
										{#if open.has(n.id)}
											{@render details(n)}
										{/if}
									</li>
								{/each}
							</ol>
						</div>
					{/if}
				</div>
			{/key}
		{:else if loaded && runs.length}
			<p class="m-6 text-sm text-muted-foreground">Pick a run to see what happened.</p>
		{/if}
	</div>
</div>

{#snippet details(n: NodeRun)}
	<div class="ms-[34px] me-1 grid gap-3 pt-1 pb-3" transition:slide={{ duration: 200 }}>
		{#if n.error}
			<div class={cn('rounded-lg border px-3 py-2 text-sm', n.status === 'skipped' ? 'bg-card' : 'border-destructive/30 bg-destructive/5')}>
				<p class={cn('text-xs font-medium tracking-wide uppercase', n.status === 'skipped' ? 'text-muted-foreground' : 'text-destructive')}>{reasonTitle(n)}</p>
				<p class="mt-0.5 break-words whitespace-pre-wrap">{n.error}</p>
			</div>
		{/if}
		{#if n.result && n.result !== n.log}
			<div>
				<p class="mb-1 text-xs font-medium tracking-wide text-muted-foreground uppercase">Result</p>
				<pre class="max-h-48 overflow-auto rounded-lg border bg-card p-3 text-xs break-words whitespace-pre-wrap">{n.result}</pre>
			</div>
		{/if}
		{#if n.log}
			<div>
				<p class="mb-1 text-xs font-medium tracking-wide text-muted-foreground uppercase">Log{n.task_id ? ` (task #${n.task_id})` : ''}</p>
				<LogPanel text={n.log} title={`${n.label} - log`} subtitle={`${n.kind} node in run #${detail?.id ?? ''}`} class="h-56" />
			</div>
		{:else if !n.error}
			<p class="text-sm text-muted-foreground">No output.</p>
		{/if}
	</div>
{/snippet}
