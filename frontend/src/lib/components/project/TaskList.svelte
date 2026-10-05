<script lang="ts">
	import type { PropertyDef, Task } from '$lib/api'
	import StatusBadge from '$lib/components/StatusBadge.svelte'
	import { describeCron, relative } from '$lib/format'

	let { tasks, defs, now, onopen }: { tasks: Task[]; defs: PropertyDef[]; now: number; onopen: (task: Task) => void } = $props()

	const order = ['running', 'ready', 'review', 'inbox', 'blocked', 'failed', 'done']
	const sorted = $derived([...tasks].sort((a, b) => order.indexOf(a.status) - order.indexOf(b.status) || a.position - b.position))

	function schedule(t: Task) {
		if (t.schedule_kind === 'cron') return describeCron(t.cron)
		if (t.schedule_kind === 'once') return 'One-off'
		return 'Manual'
	}
</script>

{#if tasks.length === 0}
	<p class="rounded-xl border border-dashed py-12 text-center text-sm text-muted-foreground">No tasks yet.</p>
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
				{#each sorted as t (t.id)}
					<tr class="cursor-pointer border-b last:border-0 hover:bg-accent/40" onclick={() => onopen(t)}>
						<td class="max-w-72 truncate px-4 py-2.5 font-medium">
							<button type="button" class="truncate text-start" onclick={(e) => (e.stopPropagation(), onopen(t))}>{t.title}</button>
						</td>
						<td class="px-4 py-2.5"><StatusBadge status={t.status} /></td>
						<td class="px-4 py-2.5 text-muted-foreground">{schedule(t)}</td>
						<td class="px-4 py-2.5 text-muted-foreground">{t.status === 'ready' && t.next_run_at ? relative(t.next_run_at, now) : '-'}</td>
						<td class="px-4 py-2.5 text-muted-foreground">{t.last_run_at ? relative(t.last_run_at, now) : '-'}</td>
						{#each defs as d (d.key)}
							<td class="px-4 py-2.5 text-muted-foreground">{t.properties[d.key] === undefined ? '-' : d.type === 'checkbox' ? 'Yes' : t.properties[d.key]}</td>
						{/each}
					</tr>
				{/each}
			</tbody>
		</table>
	</div>
{/if}
