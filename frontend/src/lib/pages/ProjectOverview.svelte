<script lang="ts">
	import { api, ApiError, type Project, type ScheduledRun, type Task } from '$lib/api'
	import { attentionTasks } from '$lib/attention'
	import { destinationLabel, findBoard } from '$lib/boards'
	import AgentsSection from '$lib/components/AgentsSection.svelte'
	import ProjectConnections from '$lib/components/ProjectConnections.svelte'
	import HistoryList from '$lib/components/project/HistoryList.svelte'
	import WorkspaceDialog from '$lib/components/project/WorkspaceDialog.svelte'
	import WorkspaceCards from '$lib/components/WorkspaceCards.svelte'
	import DynamicIcon from '$lib/components/DynamicIcon.svelte'
	import FolderKanbanIcon from '@lucide/svelte/icons/folder-kanban'
	import ProjectDialogs from '$lib/components/project/ProjectDialogs.svelte'
	import { Button } from '$lib/components/ui/button/index.js'
	import * as DropdownMenu from '$lib/components/ui/dropdown-menu/index.js'
	import EllipsisIcon from '@lucide/svelte/icons/ellipsis'
	import { router } from '$lib/router.svelte'
	import { structure } from '$lib/structure.svelte'
	import SkillsSection from '$lib/components/SkillsSection.svelte'
	import ToolsSection from '$lib/components/ToolsSection.svelte'
	import VolumesSection from '$lib/components/VolumesSection.svelte'
	import WorkflowLibrary from '$lib/components/WorkflowLibrary.svelte'
	import { projects } from '$lib/projects.svelte'
	import { countScheduled } from '$lib/schedule'
	import { onMount } from 'svelte'
	import { fade } from 'svelte/transition'

	let { id }: { id: number } = $props()

	let project = $state<Project | null>(null)
	let runs = $state<ScheduledRun[]>([])
	let now = $state(Date.now())
	let loadError = $state('')
	let tasks = $state<Task[] | null>(null)
	let attentionError = $state('')
	let allAttention = $state(false)
	let workspaceOpen = $state(false)
	let editOpen = $state(false)
	let propsOpen = $state(false)
	let deleteOpen = $state(false)
	let revision = $state(0)
	let allActivity = $state(false)
	const workspaces = $derived(structure.get(id) ?? [])
	const attention = $derived(attentionTasks(tasks ?? [], allAttention ? tasks?.length : 5))

	async function loadAttention() {
		try {
			tasks = await api.tasks(id)
			attentionError = ''
		} catch (e) {
			attentionError = e instanceof ApiError ? e.message : 'Could not load tasks needing attention'
		}
	}

	async function load() {
		try {
			const [loaded, upcoming] = await Promise.all([api.project(id), api.schedule(id, 168), structure.refresh(id), loadAttention()])
			project = loaded
			runs = upcoming
			revision++
			loadError = ''
		} catch (e) {
			loadError = e instanceof ApiError ? e.message : 'Could not load the project'
		}
	}

	onMount(() => {
		load()
		const timer = setInterval(() => {
			if (document.hidden) return
			now = Date.now()
			load()
		}, 10_000)
		return () => clearInterval(timer)
	})

	// the sidebar store refreshes on its own, so the counts stay live without extra requests
	const counts = $derived(projects.get(id)?.task_counts ?? {})
	const scheduled = $derived(countScheduled(runs, now))
	const stats = $derived([
		{ label: 'Ready', value: counts.ready ?? 0 },
		{ label: 'Running', value: counts.running ?? 0 },
		{ label: 'Scheduled today', value: scheduled.today },
		{ label: 'Next 7 days', value: scheduled.week },
	])
</script>

{#if project}
	<div class="px-6 pt-8 pb-6" in:fade={{ duration: 350 }}>
		<header class="flex flex-wrap items-start justify-between gap-3">
			<div class="flex min-w-0 items-start gap-3">
				<DynamicIcon name={project.icon} fallback={FolderKanbanIcon} class="mt-1 size-7 shrink-0 text-primary" />
				<div class="min-w-0">
					<h2 class="text-2xl font-semibold tracking-tight">{project.name}</h2>
					{#if project.purpose}<p class="mt-0.5 text-sm">{project.purpose}</p>{/if}
					{#if project.description}
						<p class="mt-1 text-sm whitespace-pre-line text-muted-foreground">{project.description}</p>
					{/if}
				</div>
			</div>
			<div class="flex items-center gap-2">
				<Button variant="outline" size="sm" onclick={() => (workspaceOpen = true)}>New workspace</Button>
				<DropdownMenu.Root>
					<DropdownMenu.Trigger>
						{#snippet child({ props })}
							<Button variant="outline" size="icon-sm" aria-label="Project menu" {...props}><EllipsisIcon /></Button>
						{/snippet}
					</DropdownMenu.Trigger>
					<DropdownMenu.Content align="end" class="w-48">
						<DropdownMenu.Item onSelect={() => (editOpen = true)}>Edit project</DropdownMenu.Item>
						<DropdownMenu.Item onSelect={() => (propsOpen = true)}>Custom properties</DropdownMenu.Item>
						<DropdownMenu.Separator />
						<DropdownMenu.Item class="text-destructive focus:text-destructive" onSelect={() => (deleteOpen = true)}>Delete project</DropdownMenu.Item>
					</DropdownMenu.Content>
				</DropdownMenu.Root>
			</div>
		</header>

		<div class="mt-6 block rounded-xl border bg-card p-5">
			<div class="flex flex-wrap items-center justify-between gap-3">
				<div>
					<h3 class="text-base font-semibold tracking-tight">Tasks</h3>
					<p class="text-xs text-muted-foreground">A quick pulse on work in this project</p>
				</div>
			</div>
			<div class="mt-5 grid grid-cols-2 gap-4 border-t pt-4 sm:grid-cols-4">
				{#each stats as s (s.label)}
					<div>
						<div class="text-2xl font-semibold tabular-nums">{s.value}</div>
						<div class="text-xs text-muted-foreground">{s.label}</div>
					</div>
				{/each}
			</div>
		</div>

		<section class="mt-4 rounded-xl border bg-card p-5" aria-labelledby="attention-title">
			<div class="flex items-center justify-between gap-3">
				<div>
					<h3 id="attention-title" class="text-base font-semibold tracking-tight">Needs attention{attentionError || tasks === null ? '' : ` (${attention.total})`}</h3>
					<p class="text-xs text-muted-foreground">Review results and check failures across all boards.</p>
				</div>
				{#if !attentionError && attention.total > 5}
					<Button variant="ghost" size="sm" onclick={() => (allAttention = !allAttention)}>{allAttention ? 'Show less' : 'Show everything'}</Button>
				{/if}
			</div>
			{#if attentionError}
				<p class="mt-3 text-sm text-destructive" role="alert">Could not refresh tasks needing attention: {attentionError}. Retrying automatically.</p>
			{:else if tasks === null}
				<p class="mt-3 text-sm text-muted-foreground">Loading tasks needing attention...</p>
			{:else if attention.total === 0}
				<p class="mt-3 text-sm text-muted-foreground">No tasks need attention.</p>
			{:else}
				<ul class="mt-3 divide-y border-t">
					{#each attention.items as { task, reason } (task.id)}
						{@const board = findBoard(workspaces, task.board_id)}
						<li>
							<a href="/projects/{id}/boards/{task.board_id}" class="flex flex-wrap items-center justify-between gap-x-4 gap-y-1 rounded-md px-2 py-3 text-sm transition-colors hover:bg-accent/50">
								<div class="min-w-0 flex-1">
									<p class="truncate font-medium" title={task.title}>{task.title}</p>
									<p class="truncate text-xs text-muted-foreground">{board ? destinationLabel(workspaces, board) : 'Open board'}</p>
								</div>
								<span class={reason === 'Last run failed' ? 'text-destructive' : 'text-muted-foreground'}>{reason}</span>
							</a>
						</li>
					{/each}
				</ul>
				{#if attention.items.length < attention.total}
					<p class="mt-2 text-xs text-muted-foreground">Showing {attention.items.length} of {attention.total} tasks.</p>
				{/if}
			{/if}
		</section>

		<WorkspaceCards projectId={id} {workspaces} />

		<section class="mt-4 rounded-xl border bg-card p-5">
			<div class="mb-3 flex items-center justify-between gap-3">
				<div>
					<h3 class="text-base font-semibold tracking-tight">Recent activity</h3>
					<p class="text-xs text-muted-foreground">What was done across all workspaces and boards. Each board and workspace has its own history too.</p>
				</div>
				<Button variant="ghost" size="sm" onclick={() => (allActivity = !allActivity)}>{allActivity ? 'Show less' : 'Show everything'}</Button>
			</div>
			{#key allActivity}
				<HistoryList projectId={id} {workspaces} {now} {revision} compact={!allActivity} />
			{/key}
		</section>

		<div class="overview-grid mt-4 grid grid-cols-1 gap-4 lg:grid-cols-12">
			<div class="lg:col-span-7"><WorkflowLibrary projectId={id} {now} /></div>
			<div class="lg:col-span-5"><ProjectConnections projectId={id} /></div>
			<div class="lg:col-span-6"><AgentsSection projectId={id} /></div>
			<div class="lg:col-span-6"><VolumesSection projectId={id} /></div>
			<div class="lg:col-span-6"><SkillsSection projectId={id} /></div>
			<div class="lg:col-span-6"><ToolsSection projectId={id} /></div>
		</div>
	</div>
	<ProjectDialogs {project} bind:editOpen bind:propsOpen bind:deleteOpen onchanged={async () => (await load(), await projects.refresh())} />
	<WorkspaceDialog
		bind:open={workspaceOpen}
		projectId={id}
		onsaved={(w) => router.navigate(`/projects/${id}/workspaces/${w.id}`)}
	/>
{:else if loadError}
	<p class="m-auto text-sm text-destructive">{loadError}</p>
{/if}

<style>
	.overview-grid :global(section) {
		margin-top: 0;
	}
</style>
