<script lang="ts">
	import { api, ApiError, type KeyInfo, type McpInput, type McpServer } from '$lib/api'
	import { auth } from '$lib/auth.svelte'
	import { Button } from '$lib/components/ui/button/index.js'
	import { Input } from '$lib/components/ui/input/index.js'
	import { Label } from '$lib/components/ui/label/index.js'
	import * as Select from '$lib/components/ui/select/index.js'
	import { Textarea } from '$lib/components/ui/textarea/index.js'
	import { commandLine, formatEnv, isVariableName, parseEnv } from '$lib/tools'
	import PlusIcon from '@lucide/svelte/icons/plus'
	import XIcon from '@lucide/svelte/icons/x'
	import { untrack } from 'svelte'
	import { slide } from 'svelte/transition'

	// The fields of a tool server (MCP), for making one or changing one. It is used in a dialog on the project overview
	// and inline in the agent editor, so it saves by itself and reports back. The parent keys it by tool, so it always
	// starts from the tool it was given.
	let {
		projectId,
		server,
		keys,
		oncancel,
		onsaved,
		dirty = $bindable(false),
		panel = false,
	}: {
		projectId: number
		server: McpServer | null
		keys: KeyInfo[]
		oncancel?: () => void
		onsaved: (saved: McpServer) => void
		panel?: boolean // fills a panel of fixed height: the fields scroll, and the buttons sit on a bar of their own below them
		dirty?: boolean // the fields differ from what was loaded, so the parent can ask before throwing them away
	} = $props()

	const start = untrack(() => server)
	let name = $state(start?.name ?? '')
	let description = $state(start?.description ?? '')
	let kind = $state<'stdio' | 'http'>(start?.kind ?? 'stdio')
	let command = $state(start ? commandLine(start.command, start.args) : '')
	let url = $state(start?.url ?? '')
	let envText = $state(formatEnv(start?.env ?? {}))
	let secretRows = $state<{ env: string; id: number | null }[]>(Object.entries(start?.secret_env ?? {}).map(([env, id]) => ({ env, id })))
	let bearer = $state<number | null>(start?.bearer_secret_id ?? null)
	let saving = $state(false)
	let formError = $state('')

	const snapshot = () => JSON.stringify([name, description, kind, command, url, envText, secretRows, bearer])
	const loaded = snapshot()
	$effect(() => {
		dirty = snapshot() !== loaded
	})

	const isAdmin = $derived(!!auth.user?.is_admin)
	const keyName = (id: number | null) => keys.find((k) => k.id === id)?.name ?? (id === null ? 'No key' : 'A key that was deleted')

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
			description,
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
			onsaved(server ? await api.updateMcpServer(server.id, body) : await api.createMcpServer(projectId, body))
		} catch (err) {
			formError = err instanceof ApiError || err instanceof Error ? err.message : 'Could not save the tool'
		} finally {
			saving = false
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

<form onsubmit={save} class={panel ? 'flex min-h-0 flex-1 flex-col' : 'grid gap-4'}>
	<div class={panel ? 'slim-scrollbar grid min-h-0 flex-1 content-start gap-4 overflow-y-auto p-4' : 'grid gap-4'}>
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
	<div class="grid gap-1.5">
		<Label for="tool-description">Description</Label>
		<Textarea id="tool-description" bind:value={description} rows={2} maxlength={2000} placeholder="For people: what is this tool for?" />
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
	</div>
	<div class={panel ? 'flex justify-end gap-2 border-t p-2' : 'flex justify-end gap-2'}>
		{#if oncancel}<Button type="button" variant="ghost" size={panel ? 'sm' : 'default'} onclick={oncancel}>Cancel</Button>{/if}
		<Button type="submit" size={panel ? 'sm' : 'default'} disabled={saving || !name.trim()}>{server ? 'Save' : 'Create tool'}</Button>
	</div>
</form>
