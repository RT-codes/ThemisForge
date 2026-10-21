<script lang="ts">
	import type { Workspace } from '$lib/api/projects'
	import type { Task } from '$lib/api/tasks'
	import { statusLabel, statusTone, taskTotal, workspaceTasks } from '$lib/boards'
	import DynamicIcon from '$lib/components/DynamicIcon.svelte'
	import IconTile from '$lib/components/IconTile.svelte'
	import SectionBanner from '$lib/components/SectionBanner.svelte'
	import { taskHref, workspaceBoardHref } from '$lib/routes'
	import LayersIcon from '@lucide/svelte/icons/layers'

	// The project's workspaces on its overview: what each is for, its boards as tags that land on them, and its latest
	// tasks with where they stand. `tasks` is null until the project's tasks have loaded.
	let { projectId, workspaces, tasks }: { projectId: number; workspaces: Workspace[]; tasks: Task[] | null } = $props()

	const VISIBLE = 8
</script>

<div class="grid grid-cols-1 gap-4 lg:grid-cols-2">
	{#each workspaces as w (w.id)}
		{@const shown = workspaceTasks(w, tasks ?? [], VISIBLE)}
		<section class="overflow-hidden glow-card rounded-xl border bg-card">
			<SectionBanner tone="sky">
				<a href="/projects/{projectId}/workspaces/{w.id}" class="group flex min-w-0 items-center gap-3">
					<IconTile tone="sky"><DynamicIcon name={w.icon} fallback={LayersIcon} /></IconTile>
					<span class="min-w-0">
						<h3 class="truncate text-base font-semibold tracking-tight group-hover:text-primary">{w.name}</h3>
						{#if w.purpose}<p class="truncate text-xs text-muted-foreground">{w.purpose}</p>{/if}
					</span>
				</a>
				<!-- each board is a way in that lands on it: the workspace page opens with that board unfolded and the rest folded -->
				{#if w.boards.length}
					<ul class="mt-3 flex flex-wrap gap-1.5" aria-label="Boards in {w.name}">
						{#each w.boards as b (b.id)}
							<li>
								<a
									href={workspaceBoardHref(projectId, w.id, b.id)}
									class="inline-flex max-w-48 items-center gap-1.5 rounded-full border bg-background/50 px-2.5 py-0.5 text-xs transition-colors hover:border-primary/40 hover:bg-accent/60"
									title="Open {b.name}"
								>
									<span class="truncate">{b.name}</span>
									<span class="text-muted-foreground tabular-nums">{taskTotal(b)}</span>
								</a>
							</li>
						{/each}
					</ul>
				{:else}
					<p class="mt-2 text-xs text-muted-foreground">No boards yet</p>
				{/if}
			</SectionBanner>

			<div class="p-3">
				{#if tasks === null}
					<p class="px-2 py-1.5 text-sm text-muted-foreground">Loading tasks...</p>
				{:else if shown.total === 0}
					<p class="px-2 py-1.5 text-sm text-muted-foreground">No tasks yet.</p>
				{:else}
					<ul class="grid gap-0.5">
						{#each shown.items as t (t.id)}
							{@const board = w.boards.find((b) => b.id === t.board_id)}
							{@const column = board?.columns.find((c) => c.key === t.status)}
							<li>
								<!-- the whole row opens the task on its own board -->
								<a
									href={taskHref(projectId, t.board_id, t.id)}
									class="flex items-center gap-3 rounded-md px-2 py-1.5 text-sm transition-colors hover:bg-accent/60 focus-visible:bg-accent/60 focus-visible:outline-none"
								>
									<span class="min-w-0 flex-1 truncate font-medium" title={t.title}>{t.title}</span>
									{#if board && w.boards.length > 1}
										<span class="hidden max-w-[30%] shrink-0 truncate text-xs text-muted-foreground sm:block">{board.name}</span>
									{/if}
									<span class="inline-flex shrink-0 items-center gap-1.5 rounded-full border px-2 py-0.5 text-xs">
										<!-- a built-in status has its own dot colour; a status of the board's own brings its colour -->
										<span
											class="size-1.5 rounded-full {column && !column.builtin && column.color ? '' : statusTone(t.status).dot}"
											style={column && !column.builtin && column.color ? `background-color: ${column.color}` : undefined}
										></span>
										{statusLabel(t.status, board)}
									</span>
								</a>
							</li>
						{/each}
					</ul>
					{#if shown.total > shown.items.length}
						<a
							href="/projects/{projectId}/workspaces/{w.id}"
							class="mt-1 block rounded-md px-2 py-1.5 text-xs text-muted-foreground transition-colors hover:bg-accent/60 hover:text-foreground"
						>
							And {shown.total - shown.items.length} more {shown.total - shown.items.length === 1 ? 'task' : 'tasks'} in {w.name}
						</a>
					{/if}
				{/if}
			</div>
		</section>
	{/each}
</div>
