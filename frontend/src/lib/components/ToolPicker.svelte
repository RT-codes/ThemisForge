<script lang="ts">
	import { api, ApiError, type KeyInfo, type McpServer } from '$lib/api'
	import McpForm from '$lib/components/McpForm.svelte'
	import * as AlertDialog from '$lib/components/ui/alert-dialog/index.js'
	import { Button } from '$lib/components/ui/button/index.js'
	import { Switch } from '$lib/components/ui/switch/index.js'
	import { relative } from '$lib/format'
	import { cn } from '$lib/utils'
	import AlertTriangleIcon from '@lucide/svelte/icons/triangle-alert'
	import CircleCheckIcon from '@lucide/svelte/icons/circle-check'
	import CircleXIcon from '@lucide/svelte/icons/circle-x'
	import FolderOpenIcon from '@lucide/svelte/icons/folder-open'
	import GlobeIcon from '@lucide/svelte/icons/globe'
	import LoaderCircleIcon from '@lucide/svelte/icons/loader-circle'
	import PlugZapIcon from '@lucide/svelte/icons/plug-zap'
	import PlusIcon from '@lucide/svelte/icons/plus'
	import TerminalIcon from '@lucide/svelte/icons/terminal'
	import Trash2Icon from '@lucide/svelte/icons/trash-2'
	import { fade, slide } from 'svelte/transition'

	// Every tool server (MCP) of the project, with a switch for the ones this agent has. Picking one shows what it is, lets
	// it be changed (saved on the spot, like a skill) and tried: does the project have a working connection to it?
	// The switches are part of the agent and saved with it.
	let {
		projectId,
		selected = $bindable(),
		servers = $bindable(),
		keys,
		dirty = $bindable(false),
		canEdit,
		onremoved,
	}: {
		projectId: number
		selected: number[]
		servers: McpServer[]
		keys: KeyInfo[]
		dirty?: boolean // the tool being edited has unsaved changes
		canEdit: boolean
		onremoved: (id: number) => void // a tool was deleted, so agents lost it
	} = $props()

	// a tool's id, or 'new' for the empty form
	let focus = $state<number | 'new' | null>(null)
	let formDirty = $state(false)
	let error = $state('')
	$effect(() => {
		dirty = formDirty
	})

	const current = $derived(typeof focus === 'number' ? (servers.find((s) => s.id === focus) ?? null) : null)
	const toggled = (id: number, on: boolean) => (selected = on ? [...selected, id] : selected.filter((x) => x !== id))
	const missing = $derived(selected.filter((id) => !servers.some((s) => s.id === id)))

	let pending = $state<(() => void) | null>(null)
	function guarded(go: () => void) {
		if (formDirty) pending = go
		else go()
	}
	const pick = (id: number | 'new') => id !== focus && guarded(() => (focus = id))

	async function reload() {
		try {
			servers = await api.mcpServers(projectId)
		} catch (e) {
			error = e instanceof Error ? e.message : 'Could not load the tools'
		}
	}

	async function saved(server: McpServer) {
		await reload()
		if (focus === 'new') toggled(server.id, true) // made for this agent, so it has it
		formDirty = false
		focus = server.id
	}

	// ----- trying a tool -----

	let testing = $state<number | null>(null)
	async function test(server: McpServer) {
		testing = server.id
		error = ''
		try {
			const result = await api.testMcpServer(server.id)
			servers = servers.map((s) => (s.id === server.id ? { ...s, last_test: result } : s))
		} catch (e) {
			error = e instanceof ApiError || e instanceof Error ? e.message : 'Could not test the tool'
		} finally {
			testing = null
		}
	}

	// how a tool looks in the list: green or red from its last test, yellow when its file has a problem
	const tone = (s: McpServer) => (s.config_error ? 'warn' : s.last_test === null ? 'none' : s.last_test.ok ? 'ok' : 'bad')
	const toneLabel = (s: McpServer) =>
		s.config_error ? 'Its file has a problem' : s.last_test === null ? 'Not tried yet' : s.last_test.ok ? 'The last test worked' : 'The last test failed'

	// ----- deleting one -----

	let doomed = $state<McpServer | null>(null)
	async function remove() {
		const target = doomed
		doomed = null
		if (!target) return
		try {
			await api.deleteMcpServer(target.id)
			if (focus === target.id) focus = null
			formDirty = false
			onremoved(target.id)
			await reload()
		} catch (e) {
			error = e instanceof ApiError || e instanceof Error ? e.message : 'Could not delete the tool'
		}
	}
</script>

<!-- fills the height the editor has (at least 26rem), so the two panels grow with the window -->
<div class="grid min-h-[26rem] flex-1 gap-3 lg:grid-cols-[minmax(0,19rem)_minmax(0,1fr)] lg:grid-rows-[minmax(0,1fr)]">
	<!-- the list is a panel like the one beside it, as tall as it: the tools scroll inside it, and the toolbar with New
	     tool stays at its foot -->
	<div class="flex h-[26rem] min-w-0 flex-col overflow-hidden rounded-lg border bg-background/40 lg:h-auto">
		<div class="slim-scrollbar grid min-h-0 flex-1 grid-cols-1 content-start gap-1.5 overflow-y-auto p-2">
		{#each servers as s (s.id)}
			{@const on = selected.includes(s.id)}
			<div class={cn('flex min-w-0 items-center gap-2.5 cursor-pointer overflow-hidden rounded-md border px-2.5 py-2 transition-colors hover:border-primary/40 hover:bg-accent/40', s.id === focus && 'border-primary/40 bg-accent/60')} transition:slide={{ duration: 160 }} onclick={() => pick(s.id)} role="presentation">
				<button type="button" class="flex min-w-0 flex-1 cursor-pointer items-center gap-2.5 text-start" aria-pressed={s.id === focus}>
					<span class={cn('relative flex size-7 shrink-0 items-center justify-center rounded-md transition-colors', on ? 'bg-primary/15 text-primary' : 'bg-muted text-muted-foreground')}>
						{#if s.kind === 'http'}<GlobeIcon class="size-4" />{:else}<TerminalIcon class="size-4" />{/if}
						<span
							class={cn('absolute -end-0.5 -top-0.5 size-2.5 rounded-full border-2 border-card', {
								'bg-emerald-400': tone(s) === 'ok',
								'bg-destructive': tone(s) === 'bad',
								'bg-yellow-400': tone(s) === 'warn',
								'bg-muted-foreground/40': tone(s) === 'none',
							})}
							title={toneLabel(s)}
						></span>
					</span>
					<span class="min-w-0 flex-1">
						<span class="block truncate font-mono text-sm font-medium">{s.name}</span>
						<span class="block truncate text-xs text-muted-foreground">{s.description || (s.kind === 'http' ? s.url : s.command)}</span>
					</span>
				</button>
				<!-- svelte-ignore a11y_click_events_have_key_events, a11y_no_static_element_interactions -->
				<span class="flex cursor-default" onclick={(e) => e.stopPropagation()}><Switch checked={on} onCheckedChange={(v) => toggled(s.id, v)} aria-label="Give the agent {s.name}" /></span>
			</div>
		{:else}
			<p class="rounded-lg border border-dashed px-3 py-6 text-center text-sm text-muted-foreground">No tools yet. A tool is an MCP server that gives agents more to work with, such as a file system or a search service.</p>
		{/each}
		{#each missing as id (id)}
			<div class="flex items-center gap-3 rounded-lg border border-yellow-500/30 bg-yellow-500/5 px-3 py-2.5" transition:slide={{ duration: 160 }}>
				<AlertTriangleIcon class="size-4 shrink-0 text-yellow-300" />
				<span class="min-w-0 flex-1 text-xs text-yellow-300">A tool this agent had no longer exists</span>
				<Button type="button" variant="outline" size="sm" onclick={() => toggled(id, false)}>Remove</Button>
			</div>
		{/each}
		{#if error}<p class="px-1 text-sm text-destructive" role="alert">{error}</p>{/if}
		</div>
		{#if canEdit}
			<div class="border-t p-2">
				<Button type="button" variant="outline" size="sm" class="w-full" onclick={() => pick('new')}><PlusIcon /> New tool</Button>
			</div>
		{/if}
	</div>

	<div class="relative flex h-[26rem] min-w-0 flex-col overflow-hidden rounded-lg border bg-background/40 lg:h-auto">
		{#if current || focus === 'new'}
			{#key focus}
				<div class="flex items-center gap-2 border-b px-4 py-2.5" in:fade={{ duration: 150 }}>
					<div class="min-w-0 flex-1">
						<p class="truncate font-mono text-sm font-medium">{current?.name ?? 'New tool'}</p>
						<p class="truncate text-xs text-muted-foreground">
							{#if current}{selected.includes(current.id) ? 'This agent has it.' : 'This agent does not have it.'} Other agents may.{:else}It will be given to this agent.{/if}
						</p>
					</div>
					{#if current}
						<Button variant="ghost" size="icon-sm" class="text-muted-foreground" aria-label="Open its file in Files" title="Open in Files" href="/projects/{projectId}/files#config/{current.path}"><FolderOpenIcon /></Button>
						{#if canEdit}
							<Button variant="ghost" size="icon-sm" class="text-muted-foreground hover:text-destructive" aria-label="Delete {current.name}" onclick={() => (doomed = current)}><Trash2Icon /></Button>
						{/if}
					{/if}
				</div>
				<div class="flex min-h-0 flex-1 flex-col" in:fade={{ duration: 150 }}>
					{#if current}
						{@const server = current}
						<div class="m-4 mb-0 shrink-0 rounded-lg border p-3">
							<div class="flex flex-wrap items-center gap-3">
								<div class="min-w-0 flex-1">
									{#if server.config_error}
										<p class="flex items-start gap-2 text-sm text-yellow-300"><AlertTriangleIcon class="mt-0.5 size-4 shrink-0" /><span>{server.config_error}</span></p>
									{:else if server.last_test}
										<p class={cn('flex items-start gap-2 text-sm', server.last_test.ok ? 'text-emerald-400' : 'text-destructive')} role="status">
											{#if server.last_test.ok}<CircleCheckIcon class="mt-0.5 size-4 shrink-0" />{:else}<CircleXIcon class="mt-0.5 size-4 shrink-0" />{/if}
											<span>{server.last_test.message}</span>
										</p>
										<p class="mt-1 ps-6 text-xs text-muted-foreground">Tried {relative(server.last_test.at)}</p>
									{:else}
										<p class="text-sm text-muted-foreground">Not tried yet. A test checks that the project can reach this tool.</p>
									{/if}
								</div>
								<Button variant="outline" size="sm" disabled={testing !== null || formDirty} title={formDirty ? 'Save your changes first' : ''} onclick={() => test(server)}>
									{#if testing === server.id}<LoaderCircleIcon class="animate-spin" /> Testing...{:else}<PlugZapIcon /> Test connection{/if}
								</Button>
							</div>
							{#if server.last_test?.tools.length}
								<div class="mt-3 flex flex-wrap gap-1.5 ps-6">
									{#each server.last_test.tools as t (t)}<span class="rounded-md bg-muted px-1.5 py-0.5 font-mono text-xs text-muted-foreground">{t}</span>{/each}
								</div>
							{/if}
						</div>
					{/if}
					{#if canEdit}
						{#key current?.id ?? 'new'}
							<McpForm {projectId} server={current} {keys} panel bind:dirty={formDirty} onsaved={saved} oncancel={current ? undefined : () => guarded(() => (focus = null))} />
						{/key}
					{/if}
				</div>
			{/key}
		{:else}
			<div class="m-auto max-w-xs px-6 py-12 text-center" in:fade={{ duration: 150 }}>
				<PlugZapIcon class="mx-auto size-7 text-muted-foreground" />
				<p class="mt-3 text-sm font-medium">Pick a tool to see it</p>
				<p class="mt-1 text-xs text-muted-foreground">You can change it and test the connection here. The switch beside a tool gives it to this agent.</p>
			</div>
		{/if}
	</div>
</div>

<AlertDialog.Root open={doomed !== null} onOpenChange={(o) => !o && (doomed = null)}>
	<AlertDialog.Content>
		<AlertDialog.Header>
			<AlertDialog.Title>Delete this tool?</AlertDialog.Title>
			<AlertDialog.Description>"{doomed?.name}" is deleted from the project, and every agent that has it loses it.</AlertDialog.Description>
		</AlertDialog.Header>
		<AlertDialog.Footer>
			<AlertDialog.Cancel>Keep it</AlertDialog.Cancel>
			<AlertDialog.Action onclick={remove}>Delete</AlertDialog.Action>
		</AlertDialog.Footer>
	</AlertDialog.Content>
</AlertDialog.Root>

<AlertDialog.Root open={pending !== null} onOpenChange={(o) => !o && (pending = null)}>
	<AlertDialog.Content>
		<AlertDialog.Header>
			<AlertDialog.Title>You have unsaved changes</AlertDialog.Title>
			<AlertDialog.Description>The tool you are editing was changed and not saved. Keep editing, or discard the changes and go on.</AlertDialog.Description>
		</AlertDialog.Header>
		<AlertDialog.Footer>
			<AlertDialog.Cancel>Keep editing</AlertDialog.Cancel>
			<AlertDialog.Action
				onclick={() => {
					const go = pending
					pending = null
					formDirty = false
					go?.()
				}}>Discard changes</AlertDialog.Action
			>
		</AlertDialog.Footer>
	</AlertDialog.Content>
</AlertDialog.Root>
