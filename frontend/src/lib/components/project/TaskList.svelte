<script lang="ts">
	import type { Board, PropertyDef, Task } from '$lib/api'
	import StatusBadge from '$lib/components/StatusBadge.svelte'
	import { chipStyle } from '$lib/colors'
	import { dateTime, relative } from '$lib/format'
	import { describeSchedule } from '$lib/recurrence'
	import { applyView, type BoardView } from '$lib/boardView'
	import { cn } from '$lib/utils'
	import CircleAlertIcon from '@lucide/svelte/icons/circle-alert'

	let { tasks, board, defs, view, now, selectedId = null, onopen }: { tasks: Task[]; board: Board; defs: PropertyDef[]; view: BoardView; now: number; selectedId?: number | null; onopen: (task: Task) => void } = $props()

	const order = ['running', 'ready', 'review', 'backlog', 'blocked', 'failed', 'done']
	// a custom status is a parking column like Backlog, so its tasks are listed with the backlog
	const rank = (status: string) => (order.includes(status) ? order.indexOf(status) : order.indexOf('backlog') + 0.5)
	const statuses = $derived([...new Set(tasks.map((t) => t.status))].sort((a, b) => rank(a) - rank(b)))
	const shown = $derived(statuses.flatMap((status) => applyView(tasks.filter((t) => t.status === status), view).shown))

	function schedule(t: Task) {
		if (t.schedule_kind === 'cron') return describeSchedule(t.cron)
		if (t.schedule_kind === 'once') return t.run_at ? dateTime(t.run_at) : 'One-off'
		return 'Manual'
	}
</script>

{#if tasks.length === 0}
	<p class="rounded-xl border border-dashed py-12 text-center text-sm text-muted-foreground">No tasks yet.</p>
{:else if shown.length === 0}
	<p class="rounded-xl border border-dashed py-12 text-center text-sm text-muted-foreground">No tasks match these search and filter settings.</p>
{:else}
	<div class="overflow-x-auto rounded-xl border bg-card/40">
		<table class="w-full min-w-[40rem] text-sm">
			<thead class="border-b text-start text-xs text-muted-foreground">
				<tr>
					<th class="px-4 py-2.5 text-start font-medium">Task</th>
					<th class="px-4 py-2.5 text-start font-medium">Status</th>
					<th class="px-4 py-2.5 text-start font-medium">Schedule</th>
					<th class="px-4 py-2.5 text-start font-medium">Next run</th>
					<th class="px-4 py-2.5 text-start font-medium">Last run</th>
					{#each defs as d (d.key)}
						<th class="px-4 py-2.5 text-start font-medium">{d.name}</th>
					{/each}
				</tr>
			</thead>
			<tbody>
				{#each shown as t (t.id)}
					<tr class={cn('cursor-pointer border-b last:border-0 hover:bg-accent/40', t.id === selectedId && 'bg-primary/10 hover:bg-primary/10')} onclick={() => onopen(t)}>
						<td class="max-w-72 px-4 py-2.5 font-medium">
							<button type="button" class="block max-w-full truncate text-start" aria-describedby={t.last_attempt_status === 'failed' && t.status !== 'running' ? `task-last-failure-${t.id}` : undefined} onclick={(e) => (e.stopPropagation(), onopen(t))}>{t.title}</button>
							{#if t.last_attempt_status === 'failed' && t.status !== 'running'}
								<div id={`task-last-failure-${t.id}`} class="mt-1 text-xs font-normal text-destructive">
									<p class="flex items-center gap-1 font-medium"><CircleAlertIcon class="size-3.5 shrink-0" aria-hidden="true" />Last run failed</p>
									{#if t.last_failure_reason}
										<p class="mt-0.5 line-clamp-2 [overflow-wrap:anywhere]" title={t.last_failure_reason}>{t.last_failure_reason}</p>
									{/if}
								</div>
							{/if}
						</td>
						<td class="px-4 py-2.5"><StatusBadge status={t.status} {board} /></td>
						<td class="px-4 py-2.5 text-muted-foreground">{schedule(t)}</td>
						<td class="px-4 py-2.5 text-muted-foreground">{t.status === 'ready' && t.next_run_at ? relative(t.next_run_at, now) : '-'}</td>
						<td class="px-4 py-2.5 text-muted-foreground">{t.last_run_at ? relative(t.last_run_at, now) : '-'}</td>
						{#each defs as d (d.key)}
							<td class="px-4 py-2.5 text-muted-foreground">
								{#if t.properties[d.key] === undefined}-{:else if d.type === 'checkbox'}Yes{:else if d.type === 'select' && chipStyle(d.colors?.[String(t.properties[d.key])])}
									<span class="rounded-md border border-transparent px-1.5 py-0.5 text-xs" style={chipStyle(d.colors?.[String(t.properties[d.key])])}>{t.properties[d.key]}</span>
								{:else}{t.properties[d.key]}{/if}
							</td>
						{/each}
					</tr>
				{/each}
			</tbody>
		</table>
	</div>
{/if}
