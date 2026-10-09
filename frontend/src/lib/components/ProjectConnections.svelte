<script lang="ts">
	import { api, type McpServer } from '$lib/api'
	import { Button } from '$lib/components/ui/button/index.js'
	import { relative } from '$lib/format'
	import { router } from '$lib/router.svelte'
	import ArrowUpRightIcon from '@lucide/svelte/icons/arrow-up-right'
	import CircleCheckIcon from '@lucide/svelte/icons/circle-check'
	import CircleHelpIcon from '@lucide/svelte/icons/circle-help'
	import CircleXIcon from '@lucide/svelte/icons/circle-x'
	import GlobeIcon from '@lucide/svelte/icons/globe'
	import TerminalIcon from '@lucide/svelte/icons/terminal'
	import { onMount } from 'svelte'

	let { projectId }: { projectId: number } = $props()

	let servers = $state<McpServer[]>([])
	let loaded = $state(false)
	let error = $state('')

	async function load() {
		try {
			servers = await api.mcpServers(projectId)
			error = ''
		} catch (e) {
			error = e instanceof Error ? e.message : 'Could not load project connections'
		} finally {
			loaded = true
		}
	}

	onMount(load)

	function status(server: McpServer) {
		if (server.config_error) return { label: 'Configuration issue', tone: 'text-destructive' }
		if (server.last_test?.ok) return { label: 'Last test passed', tone: 'text-emerald-400' }
		if (server.last_test) return { label: 'Last test failed', tone: 'text-destructive' }
		return { label: 'Not tested', tone: 'text-muted-foreground' }
	}
</script>

<section id="connections" class="mt-6 scroll-mt-6 rounded-xl border bg-card">
	<div class="flex items-center gap-3 p-5 pb-3">
		<div class="min-w-0 flex-1">
			<h3 class="text-base font-semibold tracking-tight">Connections</h3>
			<p class="text-sm text-muted-foreground">Project MCP tools and their latest test result, not live health.</p>
		</div>
		<Button variant="outline" size="sm" onclick={() => router.navigate(`/projects/${projectId}#tools`)}>
			Manage <ArrowUpRightIcon />
		</Button>
	</div>

	{#if error}
		<p class="px-5 pb-5 text-sm text-destructive" role="alert">{error}</p>
	{:else if !loaded}
		<p class="px-5 pb-5 text-sm text-muted-foreground">Loading connections...</p>
	{:else if servers.length === 0}
		<div class="mx-5 mb-5 rounded-lg border border-dashed py-7 text-center">
			<p class="text-sm font-medium">No connections yet</p>
			<p class="mt-1 text-xs text-muted-foreground">Add MCP tools below and assign them to agents.</p>
		</div>
	{:else}
		<ul class="divide-y border-t">
			{#each servers as server (server.id)}
				{@const result = status(server)}
				<li class="flex items-center gap-3 px-5 py-3">
					<span class="flex size-8 shrink-0 items-center justify-center rounded-md bg-primary/15 text-primary">
						{#if server.kind === 'http'}<GlobeIcon class="size-4" />{:else}<TerminalIcon class="size-4" />{/if}
					</span>
					<span class="min-w-0 flex-1">
						<span class="block truncate text-sm font-medium">{server.name}</span>
						<span class="block truncate text-xs text-muted-foreground">
							{#if server.config_error}
								{server.config_error}
							{:else if server.last_test?.message}
								{server.last_test.message}
							{:else}
								{server.kind === 'http' ? server.url : server.command}
							{/if}
						</span>
					</span>
					<span class="flex shrink-0 items-center gap-1.5 text-xs {result.tone}">
						{#if server.config_error || server.last_test && !server.last_test.ok}
							<CircleXIcon class="size-3.5" />
						{:else if server.last_test?.ok}
							<CircleCheckIcon class="size-3.5" />
						{:else}
						<CircleHelpIcon class="size-3.5" />
						{/if}
						<span class="hidden sm:inline">{result.label}</span>
						{#if server.last_test}<span title={server.last_test.at}>· {relative(server.last_test.at)}</span>{/if}
					</span>
				</li>
			{/each}
		</ul>
	{/if}
</section>
