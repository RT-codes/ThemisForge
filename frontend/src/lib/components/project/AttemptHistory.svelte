<script lang="ts">
	import { api, type Attempt, type AttemptDetail, type AttemptStatus } from '$lib/api'
	import { attemptLabel, dateTime, duration } from '$lib/format'
	import LogPanel from '$lib/components/LogPanel.svelte'
	import { cn } from '$lib/utils'
	import CircleCheckIcon from '@lucide/svelte/icons/circle-check'
	import CircleXIcon from '@lucide/svelte/icons/circle-x'
	import LoaderCircleIcon from '@lucide/svelte/icons/loader-circle'
	import BanIcon from '@lucide/svelte/icons/ban'
	import { onMount } from 'svelte'

	let { taskId, taskStatus }: { taskId: number; taskStatus: string } = $props()

	let attempts = $state<Attempt[]>([])
	let loaded = $state(false)
	let selectedId = $state<number | null>(null)
	let detail = $state<AttemptDetail | null>(null)
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

	async function load() {
		try {
			attempts = await api.attempts(taskId)
			if (selectedId === null && attempts.length) selectedId = attempts[0].id
			if (selectedId !== null) detail = await api.attempt(selectedId)
		} catch {
			// transient: the next poll retries
		} finally {
			loaded = true
			tick = Date.now()
		}
	}

	onMount(() => {
		load()
		const timer = setInterval(() => {
			if (!document.hidden && (taskStatus === 'running' || attempts[0]?.status === 'running')) load()
		}, 1500)
		return () => clearInterval(timer)
	})

	// a finished run: fetch once more so the final status and log show up
	let lastStatus: string | undefined
	$effect(() => {
		const status = taskStatus
		if (lastStatus !== undefined && status !== lastStatus) load()
		lastStatus = status
	})

	async function select(id: number) {
		selectedId = id
		detail = await api.attempt(id)
	}
</script>

{#if !loaded}
	<p class="px-4 py-6 text-sm text-muted-foreground">Loading...</p>
{:else if attempts.length === 0}
	<div class="px-4 py-10 text-center">
		<p class="text-sm font-medium">No attempts yet</p>
		<p class="mt-1 text-xs text-muted-foreground">Each time a cell works on this task, it is recorded here with its log and result.</p>
	</div>
{:else}
	<div class="grid gap-3 px-4 pb-4">
		<ul class="grid gap-1">
			{#each attempts as a (a.id)}
				{@const Icon = icons[a.status]}
				<li>
					<button
						type="button"
						onclick={() => select(a.id)}
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

		{#if detail}
			{#if detail.result}
				<div>
					<h4 class="mb-1 text-xs font-medium tracking-wide text-muted-foreground uppercase">Result</h4>
					<pre class="max-h-48 overflow-auto rounded-lg border bg-card p-3 text-xs break-words whitespace-pre-wrap">{detail.result}</pre>
				</div>
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
