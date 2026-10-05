<script lang="ts">
	import { auth } from '$lib/auth.svelte'
	import ProjectDialog from '$lib/components/project/ProjectDialog.svelte'
	import { Button } from '$lib/components/ui/button/index.js'
	import { relative } from '$lib/format'
	import { projects } from '$lib/projects.svelte'
	import { router } from '$lib/router.svelte'
	import FolderKanbanIcon from '@lucide/svelte/icons/folder-kanban'
	import PlusIcon from '@lucide/svelte/icons/plus'

	let createOpen = $state(false)
	const now = Date.now()
</script>

<div class="px-6 pt-8 pb-6">
	<h2 class="text-2xl font-semibold tracking-tight">Welcome, {auth.user?.name.split(' ')[0]}</h2>
	<p class="text-sm text-muted-foreground">Each project is its own control room: tasks, schedules and the cells that run them.</p>

	<div class="mt-8 grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
		{#each projects.list as p (p.id)}
			{@const c = p.task_counts}
			<a href="/projects/{p.id}" class="group rounded-xl border bg-card p-5 transition-colors hover:border-primary/40">
				<div class="flex items-center gap-2">
					<FolderKanbanIcon class="size-4 text-primary" />
					<h3 class="truncate font-medium">{p.name}</h3>
				</div>
				<p class="mt-1 line-clamp-2 min-h-8 text-sm text-muted-foreground">{p.description || 'No description'}</p>
				<div class="mt-4 flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
					<span><span class="text-foreground tabular-nums">{c.running ?? 0}</span> running</span>
					<span><span class="text-foreground tabular-nums">{c.ready ?? 0}</span> ready</span>
					<span><span class="text-foreground tabular-nums">{c.done ?? 0}</span> done</span>
					<span class="ms-auto">{p.next_run_at ? `next ${relative(p.next_run_at, now)}` : 'nothing scheduled'}</span>
				</div>
			</a>
		{/each}

		<button
			type="button"
			onclick={() => (createOpen = true)}
			class="flex min-h-36 flex-col items-center justify-center gap-2 rounded-xl border border-dashed text-sm text-muted-foreground transition-colors hover:border-primary/50 hover:text-foreground"
		>
			<PlusIcon class="size-5" />
			New project
		</button>
	</div>

	{#if projects.loaded && projects.list.length === 0}
		<p class="mt-8 max-w-xl text-sm text-muted-foreground">
			Start with a project, then add tasks to its board. Give a task a schedule and move it to Ready: the always-on scheduler picks it up and
			runs it in a fresh cell.
		</p>
	{/if}
</div>

<ProjectDialog bind:open={createOpen} onsaved={async (p) => (await projects.refresh(), router.navigate(`/projects/${p.id}`))} />
