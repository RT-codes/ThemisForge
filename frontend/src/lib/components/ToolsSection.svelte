<script lang="ts">
	import { api, ApiError, type KeyInfo, type McpServer } from '$lib/api'
	import * as AlertDialog from '$lib/components/ui/alert-dialog/index.js'
	import { Button } from '$lib/components/ui/button/index.js'
	import * as Dialog from '$lib/components/ui/dialog/index.js'
	import McpForm from '$lib/components/McpForm.svelte'
	import { router } from '$lib/router.svelte'
	import { commandLine } from '$lib/tools'
	import GlobeIcon from '@lucide/svelte/icons/globe'
	import PlusIcon from '@lucide/svelte/icons/plus'
	import TerminalIcon from '@lucide/svelte/icons/terminal'
	import Trash2Icon from '@lucide/svelte/icons/trash-2'
	import { onMount, tick } from 'svelte'
	import { slide } from 'svelte/transition'

	// The tool servers (MCP) of a project: extra tools an agent can be given, such as a file system or a search service.
	let { projectId }: { projectId: number } = $props()

	let servers = $state<McpServer[]>([])
	let keys = $state<KeyInfo[]>([])
	let loaded = $state(false)
	let error = $state('')
	let section = $state<HTMLElement>()

	let open = $state(false)
	let editing = $state<McpServer | null>(null)
	let doomed = $state<McpServer | null>(null)
	let confirmOpen = $state(false)

	async function load() {
		try {
			;[servers, keys] = await Promise.all([api.mcpServers(projectId), api.keys()])
			error = ''
		} catch (e) {
			error = e instanceof Error ? e.message : 'Could not load the tools'
		} finally {
			loaded = true
		}
	}
	onMount(() => {
		load().then(async () => {
			await tick()
			if (router.hash === 'tools') section?.scrollIntoView({ behavior: 'smooth' })
		})
	})

	function openForm(server: McpServer | null) {
		editing = server
		open = true
	}

	async function saved() {
		open = false
		await load()
	}

	async function remove() {
		const target = doomed
		confirmOpen = false
		if (!target) return
		try {
			await api.deleteMcpServer(target.id)
			await load()
		} catch (err) {
			error = err instanceof ApiError || err instanceof Error ? err.message : 'Could not delete the tool'
		}
	}
</script>

<section bind:this={section} id="tools" class="mt-6 scroll-mt-6 rounded-xl border bg-card">
	<div class="flex items-center gap-3 p-5 pb-3">
		<div class="min-w-0 flex-1">
			<h3 class="text-base font-semibold tracking-tight">Tools</h3>
			<p class="text-sm text-muted-foreground">Extra tools for agents, as MCP servers: a command that starts one, or the address of one on the web.</p>
		</div>
		<Button size="sm" onclick={() => openForm(null)}><PlusIcon /> New tool</Button>
	</div>

	{#if error}<p class="px-5 pb-3 text-sm text-destructive" role="alert">{error}</p>{/if}

	{#if !loaded}
		<p class="px-5 pb-5 text-sm text-muted-foreground">Loading...</p>
	{:else if servers.length === 0}
		<div class="mx-5 mb-5 rounded-lg border border-dashed py-8 text-center">
			<p class="text-sm font-medium">No tools yet</p>
			<p class="mt-1 text-xs text-muted-foreground">Add one, then give it to the agents that should use it.</p>
		</div>
	{:else}
		<ul class="divide-y border-t">
			{#each servers as s (s.id)}
				<li class="flex items-center gap-3 px-5 py-3 transition-colors hover:bg-accent/40" transition:slide={{ duration: 200 }}>
					<button type="button" class="flex min-w-0 flex-1 items-center gap-3 text-start" onclick={() => openForm(s)}>
						<span class="flex size-8 shrink-0 items-center justify-center rounded-md bg-primary/15 text-primary">
							{#if s.kind === 'http'}<GlobeIcon class="size-4" />{:else}<TerminalIcon class="size-4" />{/if}
						</span>
						<span class="min-w-0 flex-1">
							<span class="block truncate font-mono text-sm font-medium">{s.name}</span>
							<span class="block truncate font-mono text-xs text-muted-foreground">{s.kind === 'http' ? s.url : commandLine(s.command, s.args)}</span>
						</span>
					</button>
					<Button variant="ghost" size="icon-sm" aria-label={`Delete ${s.name}`} class="-me-2 shrink-0 text-muted-foreground/60 transition-colors hover:text-destructive" onclick={() => ((doomed = s), (confirmOpen = true))}>
						<Trash2Icon />
					</Button>
				</li>
			{/each}
		</ul>
	{/if}
</section>

<Dialog.Root bind:open>
	<Dialog.Content class="sm:max-w-xl">
		<Dialog.Header>
			<Dialog.Title>{editing ? `Edit ${editing.name}` : 'New tool'}</Dialog.Title>
			<Dialog.Description>The agent sees the tools this server offers. A command is started inside the agent's container, so the image needs what it runs.</Dialog.Description>
		</Dialog.Header>
		{#key editing?.id ?? 'new'}
			<McpForm {projectId} server={editing} {keys} oncancel={() => (open = false)} onsaved={saved} />
		{/key}
	</Dialog.Content>
</Dialog.Root>

<AlertDialog.Root bind:open={confirmOpen}>
	<AlertDialog.Content>
		<AlertDialog.Header>
			<AlertDialog.Title>Delete this tool?</AlertDialog.Title>
			<AlertDialog.Description>"{doomed?.name}" is removed, and agents that had it lose it.</AlertDialog.Description>
		</AlertDialog.Header>
		<AlertDialog.Footer>
			<AlertDialog.Cancel>Keep it</AlertDialog.Cancel>
			<AlertDialog.Action onclick={remove}>Delete</AlertDialog.Action>
		</AlertDialog.Footer>
	</AlertDialog.Content>
</AlertDialog.Root>
