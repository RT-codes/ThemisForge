<script lang="ts">
	import { api, type ScheduledRun } from '$lib/api'
	import { relative, timeOnly } from '$lib/format'
	import { cn } from '$lib/utils'
	import CalendarClockIcon from '@lucide/svelte/icons/calendar-clock'
	import { onMount } from 'svelte'

	let { projectId, now, timezone, revision }: { projectId: number; now: number; timezone: string; revision: number } = $props()

	let hours = $state(24)
	let runs = $state<ScheduledRun[]>([])
	let loaded = $state(false)

	async function load() {
		try {
			runs = await api.schedule(projectId, hours)
		} finally {
			loaded = true
		}
	}

	$effect(() => {
		hours
		revision // reload when tasks change
		load()
	})
	onMount(() => {
		const timer = setInterval(() => !document.hidden && load(), 30_000)
		return () => clearInterval(timer)
	})

	const span = $derived(hours * 3600_000)
	const rows = $derived.by(() => {
		const map = new Map<number, { id: number; title: string; recurring: boolean; at: string[] }>()
		for (const r of runs) {
			const row = map.get(r.task_id) ?? { id: r.task_id, title: r.title, recurring: r.recurring, at: [] }
			row.at.push(r.at)
			map.set(r.task_id, row)
		}
		return [...map.values()].sort((a, b) => a.at[0].localeCompare(b.at[0]))
	})
	const pct = (iso: string) => Math.min(100, Math.max(0, ((new Date(iso).getTime() - now) / span) * 100))

	const ticks = $derived.by(() => {
		const step = hours <= 24 ? 3 * 3600_000 : 24 * 3600_000
		const first = Math.ceil(now / step) * step
		const out: { left: number; label: string }[] = []
		for (let t = first; t < now + span; t += step) {
			const d = new Date(t)
			const left = ((t - now) / span) * 100
			if (left < 5 || left > 95) continue // keep the labels inside the card
			out.push({
				left,
				label: hours <= 24 ? d.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' }) : d.toLocaleDateString(undefined, { weekday: 'short', day: 'numeric' }),
			})
		}
		return out
	})
	const upNext = $derived(runs.slice(0, 6))
</script>

<div class="grid gap-6 lg:grid-cols-[1fr_16rem]">
	<section class="min-w-0 rounded-xl border bg-card/40 p-4">
		<div class="mb-4 flex flex-wrap items-center gap-3">
			<h3 class="text-sm font-medium">Timeline</h3>
			<span class="text-xs text-muted-foreground">times in your local time, recurring tasks follow {timezone}</span>
			<div class="ms-auto flex gap-1 rounded-lg bg-muted p-1" role="radiogroup" aria-label="Time window">
				{#each [{ h: 24, label: '24 hours' }, { h: 168, label: '7 days' }] as w (w.h)}
					<button
						type="button"
						role="radio"
						aria-checked={hours === w.h}
						onclick={() => (hours = w.h)}
						class={cn(
							'rounded-md px-2.5 py-1 text-xs font-medium transition-colors',
							hours === w.h ? 'bg-background text-foreground shadow-sm' : 'text-muted-foreground hover:text-foreground'
						)}>{w.label}</button
					>
				{/each}
			</div>
		</div>

		{#if !loaded}
			<div class="h-40"></div>
		{:else if rows.length === 0}
			<div class="flex flex-col items-center gap-2 py-14 text-center">
				<CalendarClockIcon class="size-8 text-muted-foreground" />
				<p class="text-sm font-medium">Nothing scheduled in this window</p>
				<p class="max-w-sm text-xs text-muted-foreground">
					Give a task a recurring or one-off schedule and move it to Ready. It will show up here and run on its own.
				</p>
			</div>
		{:else}
			<div class="grid grid-cols-[minmax(6rem,12rem)_1fr] gap-x-4 gap-y-1">
				<div></div>
				<div class="relative h-5 text-[11px] text-muted-foreground">
					{#each ticks as t (t.left)}
						<span class="absolute -translate-x-1/2 whitespace-nowrap tabular-nums" style:left="{t.left}%">{t.label}</span>
					{/each}
				</div>
				{#each rows as row (row.id)}
					<div class="truncate py-2 text-sm" title={row.title}>{row.title}</div>
					<div class="relative my-1 h-8 rounded-md bg-muted/40">
						{#each ticks as t (t.left)}
							<span class="absolute inset-y-0 w-px bg-border" style:left="{t.left}%"></span>
						{/each}
						{#each row.at as at (at)}
							<span
								class={cn(
								'absolute top-1/2 -translate-x-1/2 -translate-y-1/2 rounded-full',
								row.at.length > 30 ? 'h-4 w-0.5' : 'h-5 w-1.5', // dense schedules get thinner marks
								row.recurring ? 'bg-primary' : 'bg-sky-400'
							)}
								style:left="{pct(at)}%"
								title="{row.title}: {timeOnly(at)}"
							></span>
						{/each}
					</div>
				{/each}
				<div></div>
				<div class="flex items-center gap-4 pt-2 text-xs text-muted-foreground">
					<span class="flex items-center gap-1.5"><span class="h-3 w-1.5 rounded-full bg-primary"></span> Recurring</span>
					<span class="flex items-center gap-1.5"><span class="h-3 w-1.5 rounded-full bg-sky-400"></span> One-off</span>
					<span class="ms-auto">Left edge is now</span>
				</div>
			</div>
		{/if}
	</section>

	<aside class="rounded-xl border bg-card/40 p-4">
		<h3 class="mb-3 text-sm font-medium">Up next</h3>
		{#if upNext.length === 0}
			<p class="text-xs text-muted-foreground">No runs coming up.</p>
		{:else}
			<ol class="grid gap-3">
				{#each upNext as r (r.task_id + r.at)}
					<li class="min-w-0">
						<p class="truncate text-sm">{r.title}</p>
						<p class="text-xs text-muted-foreground">{relative(r.at, now)} · {timeOnly(r.at)}</p>
					</li>
				{/each}
			</ol>
		{/if}
	</aside>
</div>
