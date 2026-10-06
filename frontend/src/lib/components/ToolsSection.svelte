<script lang="ts">
	import { api, ApiError, type KeyInfo, type McpInput, type McpServer } from '$lib/api'
	import { auth } from '$lib/auth.svelte'
	import * as AlertDialog from '$lib/components/ui/alert-dialog/index.js'
	import { Button } from '$lib/components/ui/button/index.js'
	import * as Dialog from '$lib/components/ui/dialog/index.js'
	import { Input } from '$lib/components/ui/input/index.js'
	import { Label } from '$lib/components/ui/label/index.js'
	import * as Select from '$lib/components/ui/select/index.js'
	import { Textarea } from '$lib/components/ui/textarea/index.js'
	import { router } from '$lib/router.svelte'
	import { commandLine, formatEnv, isVariableName, parseEnv } from '$lib/tools'
	import GlobeIcon from '@lucide/svelte/icons/globe'
	import PlusIcon from '@lucide/svelte/icons/plus'
	import TerminalIcon from '@lucide/svelte/icons/terminal'
	import Trash2Icon from '@lucide/svelte/icons/trash-2'
	import XIcon from '@lucide/svelte/icons/x'
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
	let name = $state('')
	let kind = $state<'stdio' | 'http'>('stdio')
	let command = $state('')
	let url = $state('')
	let envText = $state('')
	let secretRows = $state<{ env: string; id: number | null }[]>([])
	let bearer = $state<number | null>(null)
	let saving = $state(false)
	let formError = $state('')
	let doomed = $state<McpServer | null>(null)
	let confirmOpen = $state(false)

	const isAdmin = $derived(!!auth.user?.is_admin)
	const keyName = (id: number | null) => keys.find((k) => k.id === id)?.name ?? (id === null ? 'No key' : 'A key that was deleted')

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
		name = server?.name ?? ''
		kind = server?.kind ?? 'stdio'
		command = server ? commandLine(server.command, server.args) : ''
		url = server?.url ?? ''
		envText = formatEnv(server?.env ?? {})
		secretRows = Object.entries(server?.secret_env ?? {}).map(([env, id]) => ({ env, id }))
		bearer = server?.bearer_secret_id ?? null
		formError = ''
		open = true
	}

	async function save(e: SubmitEvent) {
		e.preventDefault()
		formError = ''
		const secret_env: Record<string, number> = {}
		for (const row of secretRows) {
			if (!row.env.trim() && row.id === null) continue
			if (!isVariableName(row.env.trim()) || row.id === null) {
				formError = 'Each key needs a variable name (letters, digits and underscores) and a key to put in it'
				return
			}
			secret_env[row.env.trim()] = row.id
		}
		const body: McpInput = {
			name,
			kind,
			command: kind === 'stdio' ? command : '',
			args: [],
			url: kind === 'http' ? url : '',
			env: kind === 'stdio' ? parseEnv(envText) : {},
			secret_env: kind === 'stdio' ? secret_env : {},
			bearer_secret_id: kind === 'http' ? bearer : null,
		}
		saving = true
		try {
			if (editing) await api.updateMcpServer(editing.id, body)
			else await api.createMcpServer(projectId, body)
			open = false
			await load()
		} catch (err) {
			formError = err instanceof ApiError || err instanceof Error ? err.message : 'Could not save the tool'
		} finally {
			saving = false
		}
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

{#snippet keyPicker(value: number | null, onpick: (id: number) => void, label: string, disabled: boolean)}
	<Select.Root type="single" value={value === null ? '' : String(value)} onValueChange={(v) => onpick(Number(v))} {disabled}>
		<Select.Trigger class="w-full" aria-label={label}>{value === null ? 'Choose a key' : keyName(value)}</Select.Trigger>
		<Select.Content>
			{#each keys as k (k.id)}<Select.Item value={String(k.id)} label={k.name}>{k.name}</Select.Item>{/each}
		</Select.Content>
	</Select.Root>
{/snippet}

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
		<form onsubmit={save} class="grid gap-4">
			<div class="grid gap-4 sm:grid-cols-2">
				<div class="grid gap-1.5">
					<Label for="tool-name">Name</Label>
					<Input id="tool-name" bind:value={name} required maxlength={40} placeholder="e.g. files" class="font-mono" />
				</div>
				<div class="grid gap-1.5">
					<Label for="tool-kind">Starts</Label>
					<Select.Root type="single" bind:value={kind}>
						<Select.Trigger id="tool-kind" class="w-full">{kind === 'stdio' ? 'With a command' : 'At a web address'}</Select.Trigger>
						<Select.Content>
							<Select.Item value="stdio" label="With a command">With a command</Select.Item>
							<Select.Item value="http" label="At a web address">At a web address</Select.Item>
						</Select.Content>
					</Select.Root>
				</div>
			</div>

			{#if kind === 'stdio'}
				<div class="grid gap-1.5" transition:slide={{ duration: 160 }}>
					<Label for="tool-command">Command</Label>
					<Input id="tool-command" bind:value={command} required placeholder="npx -y @modelcontextprotocol/server-filesystem /workspace" class="font-mono" />
				</div>
				<div class="grid gap-1.5">
					<Label for="tool-env">Settings</Label>
					<Textarea id="tool-env" bind:value={envText} rows={3} placeholder={'One per line: NAME=value'} class="font-mono text-sm" spellcheck={false} />
					<p class="text-xs text-muted-foreground">Passed to the tool as environment variables. For anything secret, use a key below instead.</p>
				</div>
				<div class="grid gap-2">
					<Label>Keys</Label>
					{#each secretRows as row, i (i)}
						<div class="flex items-center gap-2">
							<Input bind:value={row.env} placeholder="VARIABLE" class="w-40 font-mono" aria-label="Variable name" disabled={!isAdmin} />
							<div class="min-w-0 flex-1">{@render keyPicker(row.id, (id) => (row.id = id), 'Key', !isAdmin)}</div>
							<Button type="button" variant="ghost" size="icon-sm" aria-label="Remove this key" disabled={!isAdmin} onclick={() => (secretRows = secretRows.filter((_, j) => j !== i))}><XIcon /></Button>
						</div>
					{/each}
					{#if isAdmin}
						<Button type="button" variant="outline" size="sm" class="justify-self-start" disabled={keys.length === 0} onclick={() => (secretRows = [...secretRows, { env: '', id: null }])}>
							<PlusIcon /> Give it a key
						</Button>
						{#if keys.length === 0}<p class="text-xs text-muted-foreground">Add keys under Settings, Keys first.</p>{/if}
					{:else}
						<p class="text-xs text-muted-foreground">Only an administrator can give a tool keys.</p>
					{/if}
				</div>
			{:else}
				<div class="grid gap-1.5" transition:slide={{ duration: 160 }}>
					<Label for="tool-url">Address</Label>
					<Input id="tool-url" bind:value={url} required placeholder="https://example.com/mcp" class="font-mono" />
				</div>
				<div class="grid gap-1.5">
					<Label>Key sent with every request</Label>
					<div class="flex items-center gap-2">
						<div class="min-w-0 flex-1">{@render keyPicker(bearer, (id) => (bearer = id), 'Key', !isAdmin)}</div>
						{#if bearer !== null && isAdmin}<Button type="button" variant="ghost" size="icon-sm" aria-label="Send no key" onclick={() => (bearer = null)}><XIcon /></Button>{/if}
					</div>
					<p class="text-xs text-muted-foreground">{isAdmin ? 'Optional: sent as a bearer token.' : 'Only an administrator can choose a key.'}</p>
				</div>
			{/if}

			{#if formError}<p class="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive" role="alert">{formError}</p>{/if}
			<Dialog.Footer>
				<Button type="button" variant="ghost" onclick={() => (open = false)}>Cancel</Button>
				<Button type="submit" disabled={saving || !name.trim()}>{editing ? 'Save' : 'Create tool'}</Button>
			</Dialog.Footer>
		</form>
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
