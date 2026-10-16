<script lang="ts">
	import { auth } from '$lib/auth.svelte'
	import ProjectDialog from '$lib/components/project/ProjectDialog.svelte'
	import { Button } from '$lib/components/ui/button/index.js'
	import { relative } from '$lib/format'
	import { projects } from '$lib/projects.svelte'
	import { router } from '$lib/router.svelte'
	import CircleAlertIcon from '@lucide/svelte/icons/circle-alert'
	import ClipboardCheckIcon from '@lucide/svelte/icons/clipboard-check'
	import ClockIcon from '@lucide/svelte/icons/clock'
	import FolderKanbanIcon from '@lucide/svelte/icons/folder-kanban'
	import PlusIcon from '@lucide/svelte/icons/plus'

	let createOpen = $state(false)
	const now = Date.now()
</script>

<div class="px-6 pt-8 pb-6">
	<h2 class="text-2xl font-semibold tracking-tight">Welcome, {auth.user?.name.split(' ')[0]}</h2>
	<p class="text-sm text-muted-foreground">Each project is its own control room: tasks, schedules and the cells that run them.</p>

	<div class="mt-8 grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
		{#each projects.list as p (p.id)}
			{@const c = p.task_counts}
			<a href="/projects/{p.id}" class="group flex min-w-0 flex-col rounded-xl border bg-card p-5 transition-colors hover:border-primary/40">
				<div class="flex items-center gap-2">
					<FolderKanbanIcon class="size-4 shrink-0 text-primary" />
					<h3 class="min-w-0 truncate font-medium">{p.name}</h3>
				</div>
				{#if p.description}
					<p class="mt-1 line-clamp-2 text-sm text-muted-foreground">{p.description}</p>
				{/if}
				<!-- always at the bottom, so the numbers line up from card to card -->
				<div class="mt-auto pt-4">
					{#if (c.review ?? 0) > 0 || (c.failed ?? 0) > 0}
						<div class="mb-3 flex flex-wrap gap-2 text-xs font-medium">
							{#if (c.review ?? 0) > 0}
								<span class="inline-flex items-center gap-1 rounded-full border border-violet-500/30 bg-violet-500/10 px-2.5 py-1 text-violet-700 dark:text-violet-300">
									<ClipboardCheckIcon class="size-3.5 shrink-0" aria-hidden="true" />
									<span class="tabular-nums">{c.review}</span> to review
								</span>
							{/if}
							{#if (c.failed ?? 0) > 0}
								<span class="inline-flex items-center gap-1 rounded-full border border-destructive/30 bg-destructive/10 px-2.5 py-1 text-destructive">
									<CircleAlertIcon class="size-3.5 shrink-0" aria-hidden="true" />
									<span class="tabular-nums">{c.failed}</span> failed
								</span>
							{/if}
						</div>
					{/if}
					<div class="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
						<span><span class="text-foreground tabular-nums">{c.running ?? 0}</span> running</span>
						<span><span class="text-foreground tabular-nums">{c.ready ?? 0}</span> ready</span>
						<span><span class="text-foreground tabular-nums">{c.done ?? 0}</span> done</span>
					</div>
					<p class="mt-2 flex items-center gap-1.5 text-xs text-muted-foreground">
						<ClockIcon class="size-3 shrink-0" />
						{p.next_run_at ? `Next run ${relative(p.next_run_at, now)}` : 'Nothing scheduled'}
					</p>
				</div>
			</a>
		{/each}

		<button
			type="button"
			onclick={() => (createOpen = true)}
			class="flex min-h-[10.25rem] flex-col items-center justify-center gap-2 rounded-xl border border-dashed text-sm text-muted-foreground transition-colors hover:border-primary/50 hover:text-foreground"
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
