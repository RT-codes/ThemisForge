<script lang="ts">
	import type { Workspace } from '$lib/api'
	import { boardSummary, taskTotal } from '$lib/boards'

	// The project's workspaces on its overview: what each is for and how busy its boards are.
	let { projectId, workspaces }: { projectId: number; workspaces: Workspace[] } = $props()
</script>

<div class="mt-4 grid grid-cols-1 gap-4 lg:grid-cols-2">
	{#each workspaces as w (w.id)}
		<section class="rounded-xl border bg-card p-5">
			<a href="/projects/{projectId}/workspaces/{w.id}" class="group block">
				<h3 class="text-base font-semibold tracking-tight group-hover:text-primary">{w.name}</h3>
				<p class="text-xs text-muted-foreground">{w.purpose || `${w.boards.length} ${w.boards.length === 1 ? 'board' : 'boards'}`}</p>
			</a>
			<ul class="mt-4 grid gap-1 border-t pt-3">
				{#each w.boards as b (b.id)}
					<li>
						<a href="/projects/{projectId}/boards/{b.id}" class="flex items-baseline justify-between gap-3 rounded-md px-2 py-1.5 text-sm transition-colors hover:bg-accent/50">
							<span class="truncate font-medium">{b.name}</span>
							<span class="truncate text-xs text-muted-foreground" title={boardSummary(b)}>{taskTotal(b)} {taskTotal(b) === 1 ? 'task' : 'tasks'}</span>
						</a>
					</li>
				{:else}
					<li class="px-2 py-1.5 text-xs text-muted-foreground">No boards yet</li>
				{/each}
			</ul>
		</section>
	{/each}
</div>
