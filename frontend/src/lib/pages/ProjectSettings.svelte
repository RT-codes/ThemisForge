<script lang="ts">
	import { api, ApiError, type Project } from '$lib/api'
	import AgentsSection from '$lib/components/AgentsSection.svelte'
	import ProjectConnections from '$lib/components/ProjectConnections.svelte'
	import SettingsSection from '$lib/components/SettingsSection.svelte'
	import SkillsSection from '$lib/components/SkillsSection.svelte'
	import ToolsSection from '$lib/components/ToolsSection.svelte'
	import VolumesSection from '$lib/components/VolumesSection.svelte'
	import WorkflowLibrary from '$lib/components/WorkflowLibrary.svelte'
	import ProjectCells from '$lib/components/project/ProjectCells.svelte'
	import ProjectDialogs from '$lib/components/project/ProjectDialogs.svelte'
	import ProjectGeneral from '$lib/components/project/ProjectGeneral.svelte'
	import { Button } from '$lib/components/ui/button/index.js'
	import { projects } from '$lib/projects.svelte'
	import { onMount } from 'svelte'
	import { fade } from 'svelte/transition'

	// Everything about how a project is set up, in one place: who it is, how its work runs, who does it, and what they
	// may use. The overview is the other half: what is happening in it.
	let { id }: { id: number } = $props()

	let project = $state<Project | null>(null)
	let loadError = $state('')
	let propsOpen = $state(false)
	let deleteOpen = $state(false)

	async function load() {
		try {
			project = await api.project(id)
			loadError = ''
		} catch (e) {
			loadError = e instanceof ApiError ? e.message : 'Could not load the project'
		}
	}
	// a rename shows in the sidebar and the breadcrumb too
	async function changed() {
		await Promise.all([load(), projects.refresh()])
	}
	onMount(load)

	const cellSummary = $derived(project?.cell_profile || project?.automation ? 'Customised' : 'Uses the defaults from Settings')
	const propertySummary = $derived(
		project?.properties.length ? `${project.properties.length} ${project.properties.length === 1 ? 'property' : 'properties'}` : 'None',
	)
</script>

{#if project}
	<div class="w-full max-w-6xl px-6 pt-8 pb-10" in:fade={{ duration: 350 }}>
		<h2 class="text-2xl font-semibold tracking-tight">Settings</h2>
		<p class="mt-1 text-sm text-muted-foreground">
			How {project.name} is set up: who it is, how its work runs, who does it and what they may use. What is happening in it is on the
			<a class="text-primary hover:underline" href="/projects/{id}">overview</a>.
		</p>

		<div class="mt-8 grid gap-3">
			<h3 class="px-1 text-xs font-medium tracking-wide text-muted-foreground uppercase">Project</h3>
			<SettingsSection id="project-general" title="General" description="Its icon, name and what it is for." summary={project.name} defaultOpen>
				<ProjectGeneral {project} onsaved={changed} />
			</SettingsSection>
			<SettingsSection id="project-cells" title="Cells and automation" description="The container its tasks run in, and the guard against endless automatic moves." summary={cellSummary}>
				<ProjectCells {project} onsaved={changed} />
			</SettingsSection>
			<SettingsSection id="project-properties" title="Task properties" description="Extra fields that every task of this project can have." summary={propertySummary}>
				{#if project.properties.length}
					<ul class="flex flex-wrap gap-2">
						{#each project.properties as p (p.key)}
							<li class="rounded-full border px-3 py-1 text-sm">{p.name} <span class="text-xs text-muted-foreground">{p.type}</span></li>
						{/each}
					</ul>
				{:else}
					<p class="text-sm text-muted-foreground">No custom properties yet.</p>
				{/if}
				<div><Button variant="outline" size="sm" onclick={() => (propsOpen = true)}>Edit properties</Button></div>
			</SettingsSection>
		</div>

		<!-- the sections below are cards of their own, each with its list and its actions; they sit side by side -->
		<div class="settings-cards mt-8 grid gap-3">
			<h3 class="px-1 text-xs font-medium tracking-wide text-muted-foreground uppercase">Work</h3>
			<div class="grid grid-cols-1 gap-4 lg:grid-cols-2">
				<AgentsSection projectId={id} />
				<WorkflowLibrary projectId={id} now={Date.now()} />
			</div>
		</div>

		<div class="settings-cards mt-8 grid gap-3">
			<h3 class="px-1 text-xs font-medium tracking-wide text-muted-foreground uppercase">Access and tools</h3>
			<div class="grid grid-cols-1 gap-4 lg:grid-cols-2">
				<ProjectConnections projectId={id} />
				<ToolsSection projectId={id} />
				<SkillsSection projectId={id} />
				<VolumesSection projectId={id} />
			</div>
		</div>

		<div class="mt-8 grid gap-3">
			<h3 class="px-1 text-xs font-medium tracking-wide text-destructive uppercase">Danger zone</h3>
			<section class="flex flex-wrap items-center gap-4 rounded-xl border border-destructive/30 bg-card px-5 py-4">
				<div class="min-w-0 flex-1">
					<p class="text-sm font-medium">Delete this project</p>
					<p class="text-sm text-muted-foreground">Its tasks and their history are removed for good. Its files on disk are kept.</p>
				</div>
				<Button variant="outline" class="border-destructive/40 text-destructive hover:bg-destructive/10 hover:text-destructive" onclick={() => (deleteOpen = true)}>
					Delete project
				</Button>
			</section>
		</div>
	</div>
	<ProjectDialogs {project} bind:propsOpen bind:deleteOpen onchanged={changed} />
{:else if loadError}
	<p class="m-auto text-sm text-destructive">{loadError}</p>
{/if}

<style>
	/* each section brings a top margin for the page it used to sit on; the grid spaces them now */
	.settings-cards :global(section) {
		margin-top: 0;
	}
</style>
