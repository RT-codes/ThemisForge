<script lang="ts">
	import { api, ApiError, type Project, type ScheduledRun } from '$lib/api'
	import AgentsSection from '$lib/components/AgentsSection.svelte'
	import ProjectConnections from '$lib/components/ProjectConnections.svelte'
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

	async function load() {
		try {
			;[project, runs] = await Promise.all([api.project(id), api.schedule(id, 168)])
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
		<header>
			<h2 class="text-2xl font-semibold tracking-tight">{project.name}</h2>
			{#if project.description}
				<p class="mt-1 text-sm text-muted-foreground">{project.description}</p>
			{/if}
		</header>

		<a href="/projects/{id}/tasks" class="mt-6 block rounded-xl border bg-card p-5 transition-colors hover:border-primary/40">
			<div class="flex flex-wrap items-center justify-between gap-3">
				<div>
					<h3 class="text-base font-semibold tracking-tight">Tasks</h3>
					<p class="text-xs text-muted-foreground">A quick pulse on work in this project</p>
				</div>
				<span class="text-xs font-medium text-primary">Open task board <span aria-hidden="true">↗</span></span>
			</div>
			<div class="mt-5 grid grid-cols-2 gap-4 border-t pt-4 sm:grid-cols-4">
				{#each stats as s (s.label)}
					<div>
						<div class="text-2xl font-semibold tabular-nums">{s.value}</div>
						<div class="text-xs text-muted-foreground">{s.label}</div>
					</div>
				{/each}
			</div>
		</a>

		<div class="overview-grid mt-4 grid grid-cols-1 gap-4 lg:grid-cols-12">
			<div class="lg:col-span-7"><WorkflowLibrary projectId={id} {now} /></div>
			<div class="lg:col-span-5"><ProjectConnections projectId={id} /></div>
			<div class="lg:col-span-6"><AgentsSection projectId={id} /></div>
			<div class="lg:col-span-6"><VolumesSection projectId={id} /></div>
			<div class="lg:col-span-6"><SkillsSection projectId={id} /></div>
			<div class="lg:col-span-6"><ToolsSection projectId={id} /></div>
		</div>
	</div>
{:else if loadError}
	<p class="m-auto text-sm text-destructive">{loadError}</p>
{/if}

<style>
	.overview-grid :global(section) {
		margin-top: 0;
	}
</style>
