<script lang="ts">
	import { api, type Agent, type CellDefaults, type HarnessInfo, type KeyInfo, type McpServer, type Project, type Skill, type Volume } from '$lib/api'
	import AgentDetail from '$lib/components/AgentDetail.svelte'
	import * as Tabs from '$lib/components/ui/tabs/index.js'
	import type { AgentCounts, AgentTab } from '$lib/agentTabs'
	import AgentForm from '$lib/components/AgentForm.svelte'
	import { Button } from '$lib/components/ui/button/index.js'
	import { router } from '$lib/router.svelte'
	import { cn } from '$lib/utils'
	import ArrowLeftIcon from '@lucide/svelte/icons/arrow-left'
	import AlertTriangleIcon from '@lucide/svelte/icons/triangle-alert'
	import BotIcon from '@lucide/svelte/icons/bot'
	import PlusIcon from '@lucide/svelte/icons/plus'
	import { onMount } from 'svelte'

	// The agents of a project: a list on the left, and on the right the chosen agent. Choosing one only shows it (an
	// overview); Edit opens the editor, where skills and tools can be read, changed and switched on or off.
	let { projectId, agentId, isNew, editing }: { projectId: number; agentId: number | null; isNew: boolean; editing: boolean } = $props()

	let agents = $state<Agent[]>([])
	let harnesses = $state<HarnessInfo[]>([])
	let project = $state<Project | null>(null)
	let skills = $state<Skill[]>([])
	let servers = $state<McpServer[]>([])
	let keys = $state<KeyInfo[]>([])
	let volumes = $state<Volume[]>([])
	let defaults = $state<CellDefaults | null>(null)
	let loaded = $state(false)
	let loadError = $state('')

	let tab = $state<AgentTab>('general')
	let counts = $state<AgentCounts>({ skills: 0, tools: 0, hasSkills: true, hasTools: true })
	// every agent (and every visit to the editor) starts on the first tab
	$effect(() => {
		void [agentId, editing]
		tab = 'general'
	})

	const current = $derived(agents.find((a) => a.id === agentId) ?? null)
	const byName = (a: Agent, b: Agent) => a.name.localeCompare(b.name)

	async function load() {
		try {
			;[agents, harnesses, project, defaults, skills, servers, keys, volumes] = await Promise.all([
				api.agents(projectId),
				api.harnesses(),
				api.project(projectId),
				api.systemStatus().then((s) => s.cell_defaults),
				api.skills(projectId),
				api.mcpServers(projectId),
				api.keys(),
				api.volumes(projectId),
			])
			loadError = ''
		} catch (e) {
			loadError = e instanceof Error ? e.message : 'Could not load the agents'
		} finally {
			loaded = true
		}
	}
	onMount(load)

	// the list address on its own opens the first agent, so the page always shows an agent
	$effect(() => {
		if (loaded && !isNew && agentId === null && agents.length > 0) router.replace(`/projects/${projectId}/agents/${agents[0].id}`)
	})

	function saved(agent: Agent, created: boolean) {
		agents = (created ? [...agents, agent] : agents.map((a) => (a.id === agent.id ? agent : a))).sort(byName)
		if (created) router.navigate(`/projects/${projectId}/agents/${agent.id}/edit`) // go on with its skills and tools
	}

	function deleted() {
		agents = agents.filter((a) => a.id !== agentId)
		router.navigate(`/projects/${projectId}/agents`)
	}

	const show = () => router.navigate(agentId === null ? `/projects/${projectId}/agents` : `/projects/${projectId}/agents/${agentId}`)
</script>

<div class="flex w-full flex-1 flex-col px-5 py-5">
	<h2 class="text-xl font-semibold tracking-tight">Agents</h2>
	<p class="mt-0.5 text-sm text-muted-foreground">Who does the work in this project: what each one is for, how it runs, and what it can reach.</p>

	{#if loadError}
		<p class="mt-6 text-sm text-destructive" role="alert">{loadError}</p>
	{:else if !loaded}
		<p class="mt-6 text-sm text-muted-foreground">Loading...</p>
	{:else}
		<!-- fills what is left of the window, so both columns run to the bottom of the page, and grows when the editor is longer -->
		<div class="mt-4 grid flex-1 gap-4 lg:grid-cols-[17rem_minmax(0,1fr)]">
			<!-- the column of agents: the button that makes one is at its top, where the list begins -->
			<!-- same panel as the one beside it: it starts level with it (under the tabs row) and is as tall as it -->
			<nav aria-label="Agents" class="grid content-start gap-1 rounded-xl border bg-background/40 p-2.5 lg:mt-10">
				<Button size="sm" class="w-full" disabled={isNew} onclick={() => router.navigate(`/projects/${projectId}/agents/new`)}><PlusIcon /> New agent</Button>
				<div class="my-1.5 border-t"></div>
				{#each agents as a (a.id)}
					<a
						href="/projects/{projectId}/agents/{a.id}"
						class={cn('flex items-center gap-2.5 rounded-lg border border-transparent px-2.5 py-2 transition-colors hover:bg-accent/40', a.id === agentId && 'border-primary/40 bg-accent/60')}
						aria-current={a.id === agentId ? 'page' : undefined}
					>
						<span class="flex size-7 shrink-0 items-center justify-center rounded-md bg-primary/15 text-primary"><BotIcon class="size-3.5" /></span>
						<span class="min-w-0 flex-1">
							<span class="block truncate text-sm font-medium">{a.name}</span>
							<span class="block truncate text-xs text-muted-foreground">{a.role || 'No role yet'}</span>
						</span>
						{#if a.config_error}<AlertTriangleIcon class="size-4 shrink-0 text-yellow-300" aria-label="Its file has a problem" />{/if}
					</a>
				{/each}
				{#if isNew}
					<div class="flex items-center gap-2.5 rounded-lg border border-dashed border-primary/40 px-2.5 py-2 text-sm text-muted-foreground">
						<PlusIcon class="size-4" /> New agent
					</div>
				{:else if agents.length === 0}
					<p class="px-2 py-4 text-center text-xs text-muted-foreground">No agents yet</p>
				{/if}
			</nav>

			<!-- the chosen agent, on a background of its own so the two columns read as two panels; its sections fill the width -->
			<div class="flex min-w-0 flex-col">
				<!-- above the panel: the tabs of the editor on the left, what is shown (and the way back) on the right. The row is
				     always there so the agents column beside it can start level with the panel -->
				<div class="mb-2 flex h-8 items-center gap-2">
					{#if editing && (isNew || current)}
						<Tabs.Root bind:value={tab}>
							<Tabs.List>
								<Tabs.Trigger value="general">General</Tabs.Trigger>
								{#if counts.hasSkills}<Tabs.Trigger value="skills">Skills{counts.skills ? ` (${counts.skills})` : ''}</Tabs.Trigger>{/if}
								{#if counts.hasTools}<Tabs.Trigger value="tools">Tools{counts.tools ? ` (${counts.tools})` : ''}</Tabs.Trigger>{/if}
							</Tabs.List>
						</Tabs.Root>
					{/if}
					{#if isNew || current}
						<h3 class="ms-auto text-sm font-medium text-muted-foreground">{isNew ? 'New agent' : editing ? 'Edit agent' : 'Agent details'}</h3>
						{#if editing && !isNew}
							<Button variant="outline" size="sm" onclick={show}><ArrowLeftIcon /> Back to details</Button>
						{/if}
					{/if}
				</div>
			<div class="flex min-w-0 flex-1 flex-col rounded-xl border bg-background/40 p-4">
				{#if isNew}
					{#key 'new'}
						<AgentForm {projectId} agent={null} {harnesses} {project} {defaults} {keys} bind:skills bind:servers bind:tab bind:counts onsaved={saved} onclose={show} ondeleted={deleted} onchanged={load} />
					{/key}
				{:else if agents.length === 0}
					<div class="rounded-xl border border-dashed px-6 py-10 text-center">
						<BotIcon class="mx-auto size-8 text-muted-foreground" />
						<p class="mt-3 text-sm font-medium">No agents in this project yet</p>
						<p class="mx-auto mt-1 max-w-md text-xs text-muted-foreground">
							An agent has a name, a role, instructions and a harness such as Codex. Tasks and workflows pick one to do the work. Press <span class="font-medium text-foreground">New agent</span> to make the first one.
						</p>
					</div>
				{:else if !current}
					<div class="rounded-xl border border-dashed px-6 py-10 text-center">
						<BotIcon class="mx-auto size-8 text-muted-foreground" />
						<p class="mt-3 text-sm font-medium">That agent does not exist</p>
						<p class="mx-auto mt-1 max-w-sm text-xs text-muted-foreground">It may have been deleted. Pick another one from the list.</p>
					</div>
				{:else if editing}
					{#key current.id}
						<AgentForm {projectId} agent={current} {harnesses} {project} {defaults} {keys} bind:skills bind:servers bind:tab bind:counts onsaved={saved} onclose={show} ondeleted={deleted} onchanged={load} />
					{/key}
				{:else}
					{#key current.id}
						<AgentDetail agent={current} {harnesses} {skills} {servers} {keys} {volumes} {project} {defaults} onedit={() => router.navigate(`/projects/${projectId}/agents/${current.id}/edit`)} />
					{/key}
				{/if}
			</div>
			</div>
		</div>
	{/if}
</div>
