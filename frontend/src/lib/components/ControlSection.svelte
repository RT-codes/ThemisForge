<script lang="ts">
	import { auth } from '$lib/auth.svelte'
	import * as AlertDialog from '$lib/components/ui/alert-dialog/index.js'
	import { api, ApiError, type ControlConnect, type ControlToken } from '$lib/api'
	import { Button } from '$lib/components/ui/button/index.js'
	import { Checkbox } from '$lib/components/ui/checkbox/index.js'
	import { Input } from '$lib/components/ui/input/index.js'
	import { relative } from '$lib/format'
	import BotIcon from '@lucide/svelte/icons/bot'
	import CheckIcon from '@lucide/svelte/icons/check'
	import CopyIcon from '@lucide/svelte/icons/copy'
	import PlusIcon from '@lucide/svelte/icons/plus'
	import Trash2Icon from '@lucide/svelte/icons/trash-2'
	import { onMount } from 'svelte'
	import { slide } from 'svelte/transition'

	// Agents outside Themis (Claude Code, another machine's agent) that may look through MCP (and, when allowed, act): at
	// this project, or without a project at all: all of the user's projects. A row is a key: copying its command is all it takes to connect, and it
	// can be copied again later.
	let { projectId }: { projectId?: number } = $props()

	let tokens = $state<ControlToken[]>([])
	let loaded = $state(false)
	let error = $state('')
	let adding = $state(false)
	let name = $state('Claude Code')
	// off: the agent only looks. On: it may also make, run and cancel tasks, run workflows, answer approvals and halt work
	let mayChange = $state(false)
	let busy = $state(false)
	// the connect details of the row that is open, and which copy button just worked
	let openId = $state<number | null>(null)
	let connect = $state<ControlConnect | null>(null)
	let copied = $state('')
	// the key waiting for a yes before it is removed
	let doomed = $state<ControlToken | null>(null)

	async function load() {
		try {
			tokens = projectId === undefined ? await api.accountControlTokens() : await api.controlTokens(projectId)
			error = ''
		} catch (e) {
			error = e instanceof Error ? e.message : 'Could not load the connections'
		} finally {
			loaded = true
		}
	}
	onMount(load)

	async function create(e: SubmitEvent) {
		e.preventDefault()
		busy = true
		try {
			const body = { name: name.trim(), scope: mayChange ? ('write' as const) : ('read' as const) }
			const made = projectId === undefined ? await api.createAccountControlToken(body) : await api.createControlToken(projectId, body)
			adding = false
			name = 'Claude Code'
			mayChange = false
			await load()
			await show(made)
		} catch (err) {
			error = err instanceof ApiError || err instanceof Error ? err.message : 'Could not make the connection'
		} finally {
			busy = false
		}
	}

	async function show(token: ControlToken) {
		if (openId === token.id) {
			openId = null
			return
		}
		try {
			connect = await api.controlConnect(token.id)
			openId = token.id
			error = ''
		} catch (e) {
			error = e instanceof Error ? e.message : 'Could not read the connection'
		}
	}

	async function copy(label: string, text: string) {
		try {
			await navigator.clipboard.writeText(text)
			copied = label
			setTimeout(() => copied === label && (copied = ''), 1800)
		} catch {
			error = 'Copying was blocked by the browser. Select the text and copy it by hand.'
		}
	}

	async function remove() {
		const token = doomed
		doomed = null
		if (!token) return
		try {
			await api.deleteControlToken(token.id)
			if (openId === token.id) openId = null
			await load()
		} catch (e) {
			error = e instanceof Error ? e.message : 'Could not remove the connection'
		}
	}
</script>

<section id="agent-access" class="scroll-mt-6 rounded-xl border bg-card">
	<div class="flex items-center gap-3 p-5 pb-3">
		<div class="min-w-0 flex-1">
			<h3 class="text-base font-semibold tracking-tight">Connect an agent</h3>
			<p class="text-sm text-muted-foreground">
				{#if projectId === undefined}
					Let Claude Code or another agent look at all of your projects through MCP{auth.user?.is_admin ? ', and at how Themis is set up' : ''}. They only read, unless you allow changes.
				{:else}
					Let Claude Code or another agent look at this project through MCP. They only read, unless you allow changes.
				{/if}
			</p>
		</div>
		{#if !adding}<Button size="sm" onclick={() => (adding = true)}><PlusIcon /> Connect</Button>{/if}
	</div>

	{#if error}<p class="px-5 pb-3 text-sm text-destructive" role="alert">{error}</p>{/if}

	{#if adding}
		<form class="flex flex-wrap items-center gap-2 border-t px-5 py-3" onsubmit={create} transition:slide={{ duration: 150 }}>
			<label for="control-name" class="sr-only">Name of the agent</label>
			<Input id="control-name" class="min-w-0 flex-1" bind:value={name} maxlength={60} placeholder="Claude Code" required />
			<Button type="submit" size="sm" disabled={busy || !name.trim()}>Make the connection</Button>
			<Button type="button" size="sm" variant="ghost" onclick={() => (adding = false)}>Cancel</Button>
			<label class="flex basis-full items-start gap-2 text-sm">
				<Checkbox class="mt-0.5" checked={mayChange} onCheckedChange={(on) => (mayChange = !!on)} />
				<span>
					Allow changes
					<span class="block text-xs text-muted-foreground">It can then make, move, run and cancel tasks, run workflows, answer approvals, and halt or resume work. It never deletes or changes settings.</span>
				</span>
			</label>
		</form>
	{/if}

	{#if !loaded}
		<p class="px-5 pb-5 text-sm text-muted-foreground">Loading...</p>
	{:else if tokens.length === 0 && !adding}
		<div class="mx-5 mb-5 rounded-lg border border-dashed py-8 text-center">
			<p class="text-sm font-medium">No agents connected</p>
			<p class="mt-1 text-xs text-muted-foreground">Connecting makes one key. You paste a single command into your agent and it can see this project.</p>
		</div>
	{:else if tokens.length}
		<ul class="divide-y border-t">
			{#each tokens as t (t.id)}
				<li transition:slide={{ duration: 200 }}>
					<div class="flex items-center gap-3 px-5 py-3">
						<span class="flex size-8 shrink-0 items-center justify-center rounded-md bg-primary/15 text-primary"><BotIcon class="size-4" /></span>
						<span class="min-w-0 flex-1">
							<span class="block truncate text-sm font-medium">{t.name}</span>
							<span class="block truncate text-xs text-muted-foreground">
								{t.scope === 'read' ? 'Can read' : 'Can read and change'}{t.project_id === null ? ' all projects' : ''} · {t.last_used_at ? `used ${relative(t.last_used_at)}` : 'not used yet'} · ends in {t.token_hint}
							</span>
						</span>
						<Button size="sm" variant="outline" onclick={() => show(t)}>{openId === t.id ? 'Hide' : 'Connect'}</Button>
						<Button size="icon" variant="ghost" class="size-8 text-muted-foreground hover:text-destructive" aria-label="Remove {t.name}" onclick={() => (doomed = t)}>
							<Trash2Icon class="size-4" />
						</Button>
					</div>
					{#if openId === t.id && connect}
						<div class="space-y-3 bg-muted/30 px-5 py-4" transition:slide={{ duration: 150 }}>
							<div>
								<p class="mb-1 text-xs font-medium">Claude Code: paste this in a terminal</p>
								<pre class="overflow-x-auto rounded-md border bg-background p-3 text-xs">{connect.claude_code}</pre>
								<Button size="sm" class="mt-2" onclick={() => copy('command', connect!.claude_code)}>
									{#if copied === 'command'}<CheckIcon /> Copied{:else}<CopyIcon /> Copy command{/if}
								</Button>
							</div>
							<div>
								<p class="mb-1 text-xs font-medium">Other agents: add this to their MCP config</p>
								<pre class="overflow-x-auto rounded-md border bg-background p-3 text-xs">{connect.config_json}</pre>
								<Button size="sm" variant="outline" class="mt-2" onclick={() => copy('config', connect!.config_json)}>
									{#if copied === 'config'}<CheckIcon /> Copied{:else}<CopyIcon /> Copy config{/if}
								</Button>
							</div>
							<p class="text-xs text-muted-foreground">This holds the key itself, so keep it to yourself. You can open this again whenever you need it.</p>
						</div>
					{/if}
				</li>
			{/each}
		</ul>
	{/if}
</section>

<AlertDialog.Root open={doomed !== null} onOpenChange={(open) => !open && (doomed = null)}>
	<AlertDialog.Content>
		<AlertDialog.Header>
			<AlertDialog.Title>Remove this connection?</AlertDialog.Title>
			<AlertDialog.Description>
				"{doomed?.name}" stops working at once. An agent that still uses it is refused until you connect it again with a new key.
			</AlertDialog.Description>
		</AlertDialog.Header>
		<AlertDialog.Footer>
			<AlertDialog.Cancel>Keep it</AlertDialog.Cancel>
			<AlertDialog.Action onclick={remove}>Remove</AlertDialog.Action>
		</AlertDialog.Footer>
	</AlertDialog.Content>
</AlertDialog.Root>
