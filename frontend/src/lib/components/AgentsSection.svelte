<script lang="ts">
	import { api, type Agent } from '$lib/api'
	import { Button } from '$lib/components/ui/button/index.js'
	import { router } from '$lib/router.svelte'
	import BotIcon from '@lucide/svelte/icons/bot'
	import ChevronRightIcon from '@lucide/svelte/icons/chevron-right'
	import PlusIcon from '@lucide/svelte/icons/plus'
	import { onMount, tick } from 'svelte'
	import { slide } from 'svelte/transition'

	// The agents of a project at a glance. A row opens that agent on the Agents page.
	let { projectId }: { projectId: number } = $props()

	let agents = $state<Agent[]>([])
	let loaded = $state(false)
	let error = $state('')
	let section = $state<HTMLElement>()

	async function load() {
		try {
			agents = await api.agents(projectId)
			error = ''
		} catch (e) {
			error = e instanceof Error ? e.message : 'Could not load the agents'
		} finally {
			loaded = true
		}
	}

	onMount(() => {
		load().then(async () => {
			await tick()
			if (router.hash === 'agents') section?.scrollIntoView({ behavior: 'smooth' })
		})
	})

	// "2 skills · 1 tool": what an agent has beyond its words, when it has anything
	const extras = (a: Agent) =>
		[
			a.skills.length ? `${a.skills.length} ${a.skills.length === 1 ? 'skill' : 'skills'}` : '',
			a.mcp_servers.length ? `${a.mcp_servers.length} ${a.mcp_servers.length === 1 ? 'tool' : 'tools'}` : '',
		]
			.filter(Boolean)
			.join(' · ')
</script>

<section bind:this={section} id="agents" class="mt-6 scroll-mt-6 rounded-xl border bg-card">
	<div class="flex items-center gap-3 p-5 pb-3">
		<div class="min-w-0 flex-1">
			<h3 class="text-base font-semibold tracking-tight">Agents</h3>
			<p class="text-sm text-muted-foreground">Who does the work in this project. Open one to see how it works, and edit it there.</p>
		</div>
		<Button size="sm" onclick={() => router.navigate(`/projects/${projectId}/agents/new`)}><PlusIcon /> New agent</Button>
	</div>

	{#if error}<p class="px-5 pb-3 text-sm text-destructive" role="alert">{error}</p>{/if}

	{#if !loaded}
		<p class="px-5 pb-5 text-sm text-muted-foreground">Loading...</p>
	{:else if agents.length === 0}
		<div class="mx-5 mb-5 rounded-lg border border-dashed py-8 text-center">
			<p class="text-sm font-medium">No agents yet</p>
			<p class="mt-1 text-xs text-muted-foreground">An agent has a name, a role, instructions and a harness. Tasks and workflows pick one to do the work.</p>
		</div>
	{:else}
		<ul class="divide-y border-t">
			{#each agents as a (a.id)}
				<li transition:slide={{ duration: 200 }}>
					<a href="/projects/{projectId}/agents/{a.id}" class="group flex items-center gap-3 px-5 py-3 transition-colors hover:bg-accent/40">
						<span class="flex size-8 shrink-0 items-center justify-center rounded-md bg-primary/15 text-primary"><BotIcon class="size-4" /></span>
						<span class="min-w-0 flex-1">
							<span class="block truncate text-sm font-medium">{a.name}</span>
							<span class="block truncate text-xs text-muted-foreground">{a.role || 'No role yet'}</span>
						</span>
						{#if extras(a)}<span class="hidden shrink-0 text-xs text-muted-foreground sm:block">{extras(a)}</span>{/if}
						<ChevronRightIcon class="size-4 shrink-0 text-muted-foreground/50 transition-transform group-hover:translate-x-0.5 group-hover:text-foreground" />
					</a>
				</li>
			{/each}
		</ul>
	{/if}
</section>
