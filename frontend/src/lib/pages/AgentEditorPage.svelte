<script lang="ts">
	import { api, ApiError, type Agent, type AgentInput, type CellDefaults, type HarnessInfo, type KeyInfo, type McpServer, type Project, type Skill } from '$lib/api'
	import { auth } from '$lib/auth.svelte'
	import MountsPicker from '$lib/components/MountsPicker.svelte'
	import CellChoice from '$lib/components/CellChoice.svelte'
	import * as AlertDialog from '$lib/components/ui/alert-dialog/index.js'
	import { Button } from '$lib/components/ui/button/index.js'
	import { Checkbox } from '$lib/components/ui/checkbox/index.js'
	import { Input } from '$lib/components/ui/input/index.js'
	import { Label } from '$lib/components/ui/label/index.js'
	import * as Select from '$lib/components/ui/select/index.js'
	import { Textarea } from '$lib/components/ui/textarea/index.js'
	import { effectiveCell } from '$lib/cell'
	import { router } from '$lib/router.svelte'
	import { cn } from '$lib/utils'
	import BotIcon from '@lucide/svelte/icons/bot'
	import PlusIcon from '@lucide/svelte/icons/plus'
	import Trash2Icon from '@lucide/svelte/icons/trash-2'
	import { onMount, untrack } from 'svelte'

	let { projectId, agentId, isNew }: { projectId: number; agentId: number | null; isNew: boolean } = $props()

	const blank = (): AgentInput => ({
		name: '',
		role: '',
		description: '',
		instructions: '',
		harness: 'codex',
		model: '',
		reasoning_effort: '',
		cell_profile: null,
		mounts: [],
		skills: [],
		mcp_servers: [],
		secrets: [],
	})
	const toInput = (a: Agent): AgentInput => ({
		name: a.name,
		role: a.role,
		description: a.description,
		instructions: a.instructions,
		harness: a.harness,
		model: a.model,
		reasoning_effort: a.reasoning_effort,
		cell_profile: a.cell_profile ? { ...a.cell_profile } : null,
		mounts: a.mounts.map((m) => ({ ...m })),
		skills: [...a.skills],
		mcp_servers: [...a.mcp_servers],
		secrets: [...a.secrets],
	})

	let agents = $state<Agent[]>([])
	let harnesses = $state<HarnessInfo[]>([])
	let project = $state<Project | null>(null)
	let skills = $state<Skill[]>([])
	let servers = $state<McpServer[]>([])
	let keys = $state<KeyInfo[]>([])
	let warnings = $state<string[]>([]) // tools whose command is not in the image the agent runs in
	let defaults = $state<CellDefaults | null>(null)
	let loaded = $state(false)
	let loadError = $state('')

	let draft = $state<AgentInput>(blank())
	let baseline = $state(JSON.stringify(blank()))
	let saving = $state(false)
	let saveError = $state('')
	let justSaved = $state(false)
	let confirmOpen = $state(false)

	const current = $derived(agents.find((a) => a.id === agentId) ?? null)
	const dirty = $derived(JSON.stringify(draft) !== baseline)
	const editing = $derived(isNew || current !== null)
	// what an agent's cell is when it does not customise it: the project's cell, on top of the global defaults
	const inherited = $derived(defaults ? effectiveCell(defaults, project?.cell_profile) : null)
	let formVersion = $state(0) // bumped whenever the form is loaded, so the cell control starts from the loaded agent
	const efforts = [
		{ value: '', label: 'Default from Settings' },
		{ value: 'low', label: 'Low' },
		{ value: 'medium', label: 'Medium' },
		{ value: 'high', label: 'High' },
	]

	function show(input: AgentInput) {
		draft = input
		formVersion++
		baseline = JSON.stringify(input)
		saveError = ''
	}

	// choosing another agent (or "new") loads it into the form
	$effect(() => {
		const target = isNew ? null : agentId
		const list = agents
		untrack(() => {
			if (isNew) show(blank())
			else if (target !== null) {
				const found = list.find((a) => a.id === target)
				if (found) show(toInput(found))
			}
		})
	})

	async function load() {
		try {
			;[agents, harnesses, project, defaults, skills, servers, keys] = await Promise.all([
				api.agents(projectId),
				api.harnesses(),
				api.project(projectId),
				api.systemStatus().then((s) => s.cell_defaults),
				api.skills(projectId),
				api.mcpServers(projectId),
				api.keys(),
			])
			loadError = ''
		} catch (e) {
			loadError = e instanceof Error ? e.message : 'Could not load the agents'
		} finally {
			loaded = true
		}
	}
	onMount(load)

	async function save(e: SubmitEvent) {
		e.preventDefault()
		saveError = ''
		saving = true
		try {
			if (isNew) {
				const created = await api.createAgent(projectId, draft)
				agents = [...agents, created].sort((a, b) => a.name.localeCompare(b.name))
				router.navigate(`/projects/${projectId}/agents/${created.id}`)
			} else if (current) {
				const updated = await api.updateAgent(current.id, draft)
				agents = agents.map((a) => (a.id === updated.id ? updated : a)).sort((a, b) => a.name.localeCompare(b.name))
				show(toInput(updated))
			}
			justSaved = true
			setTimeout(() => (justSaved = false), 2500)
		} catch (err) {
			saveError = err instanceof ApiError || err instanceof Error ? err.message : 'Could not save the agent'
		} finally {
			saving = false
		}
	}

	async function remove() {
		confirmOpen = false
		if (!current) return
		try {
			await api.deleteAgent(current.id)
			agents = agents.filter((a) => a.id !== current!.id)
			router.navigate(`/projects/${projectId}/agents`)
		} catch (err) {
			saveError = err instanceof ApiError || err instanceof Error ? err.message : 'Could not delete the agent'
		}
	}

	const harness = $derived(harnesses.find((h) => h.id === draft.harness))
	const isAdmin = $derived(!!auth.user?.is_admin)

	const toggled = <T,>(list: T[], item: T, on: boolean) => (on ? [...list, item] : list.filter((x) => x !== item))

	// would the tools start in the image this agent will run in? Asked after a change, the latest answer wins
	let checking = 0
	async function checkTools() {
		const ticket = ++checking
		if (draft.mcp_servers.length === 0) return void (warnings = [])
		try {
			const result = await api.checkAgent(projectId, { harness: draft.harness, cell_profile: draft.cell_profile, mcp_servers: draft.mcp_servers })
			if (ticket === checking) warnings = result.warnings
		} catch {
			if (ticket === checking) warnings = []
		}
	}
	// whenever the tools, the harness or the image change (this also covers loading an agent and saving it)
	$effect(() => {
		void [draft.harness, draft.cell_profile?.image, draft.mcp_servers.join(',')]
		untrack(checkTools)
	})
</script>

<div class="w-full max-w-6xl px-6 py-8">
	<div class="flex flex-wrap items-center gap-3">
		<div class="min-w-0 flex-1">
			<h2 class="text-2xl font-semibold tracking-tight">Agents</h2>
			<p class="mt-1 text-sm text-muted-foreground">Who does the work in this project: what each one is for, how it runs, and what it can reach.</p>
		</div>
		<Button onclick={() => router.navigate(`/projects/${projectId}/agents/new`)}><PlusIcon /> New agent</Button>
	</div>

	{#if loadError}
		<p class="mt-6 text-sm text-destructive" role="alert">{loadError}</p>
	{:else if !loaded}
		<p class="mt-6 text-sm text-muted-foreground">Loading...</p>
	{:else}
		<div class="mt-6 grid items-start gap-6 lg:grid-cols-[16rem_minmax(0,1fr)]">
			<nav aria-label="Agents" class="grid gap-1.5">
				{#each agents as a (a.id)}
					<a
						href="/projects/{projectId}/agents/{a.id}"
						class={cn('flex items-center gap-3 rounded-lg border px-3 py-2.5 transition-colors hover:bg-accent/40', a.id === agentId && 'border-primary/40 bg-accent/60')}
						aria-current={a.id === agentId ? 'page' : undefined}
					>
						<span class="flex size-8 shrink-0 items-center justify-center rounded-md bg-primary/15 text-primary"><BotIcon class="size-4" /></span>
						<span class="min-w-0">
							<span class="block truncate text-sm font-medium">{a.name}</span>
							<span class="block truncate text-xs text-muted-foreground">{a.role || 'No role yet'}</span>
						</span>
					</a>
				{/each}
				{#if isNew}
					<div class="flex items-center gap-3 rounded-lg border border-dashed border-primary/40 px-3 py-2.5 text-sm text-muted-foreground">
						<PlusIcon class="size-4" /> New agent
					</div>
				{/if}
			</nav>

			{#if !editing}
				<div class="rounded-xl border border-dashed px-6 py-14 text-center">
					<BotIcon class="mx-auto size-8 text-muted-foreground" />
					{#if agents.length === 0}
						<p class="mt-3 text-sm font-medium">No agents in this project yet</p>
						<p class="mx-auto mt-1 max-w-sm text-xs text-muted-foreground">
							An agent has a name, a role, instructions and a harness such as Codex. Workflows and tasks pick one to do the work.
						</p>
					{:else}
						<p class="mt-3 text-sm font-medium">Pick an agent to edit it</p>
					{/if}
					<Button class="mt-4" onclick={() => router.navigate(`/projects/${projectId}/agents/new`)}><PlusIcon /> New agent</Button>
				</div>
			{:else}
				<form onsubmit={save} class="grid gap-4">
					<section class="grid gap-4 rounded-xl border bg-card p-5">
						<h3 class="text-base font-semibold tracking-tight">Who it is</h3>
						<div class="grid gap-4 sm:grid-cols-2">
							<div class="grid gap-1.5">
								<Label for="agent-name">Name</Label>
								<Input id="agent-name" bind:value={draft.name} required maxlength={100} placeholder="e.g. Researcher" />
							</div>
							<div class="grid gap-1.5">
								<Label for="agent-role">Role</Label>
								<Input id="agent-role" bind:value={draft.role} maxlength={200} placeholder="e.g. finds and summarises sources" />
							</div>
						</div>
						<div class="grid gap-1.5">
							<Label for="agent-desc">Description</Label>
							<Textarea id="agent-desc" bind:value={draft.description} rows={2} maxlength={2000} placeholder="For people: what is this agent responsible for?" />
						</div>
					</section>

					<section class="grid gap-4 rounded-xl border bg-card p-5">
						<h3 class="text-base font-semibold tracking-tight">How it works</h3>
						<div class="grid gap-4 sm:grid-cols-3">
							<div class="grid gap-1.5">
								<Label for="agent-harness">Harness</Label>
								<Select.Root type="single" bind:value={draft.harness}>
									<Select.Trigger id="agent-harness" class="w-full">{harness?.label ?? draft.harness}</Select.Trigger>
									<Select.Content>
										{#each harnesses as h (h.id)}<Select.Item value={h.id} label={h.label}>{h.label}</Select.Item>{/each}
									</Select.Content>
								</Select.Root>
							</div>
							<div class="grid gap-1.5">
								<Label for="agent-model">Model</Label>
								<Input id="agent-model" bind:value={draft.model} maxlength={100} class="font-mono" placeholder="Default from Settings" />
							</div>
							<div class="grid gap-1.5">
								<Label for="agent-effort">Reasoning effort</Label>
								<Select.Root type="single" bind:value={draft.reasoning_effort}>
									<Select.Trigger id="agent-effort" class="w-full">{efforts.find((e) => e.value === draft.reasoning_effort)?.label}</Select.Trigger>
									<Select.Content>
										{#each efforts as e (e.value)}<Select.Item value={e.value} label={e.label}>{e.label}</Select.Item>{/each}
									</Select.Content>
								</Select.Root>
							</div>
						</div>
						{#if harness}<p class="-mt-2 text-xs text-muted-foreground">{harness.description}</p>{/if}
						<div class="grid gap-1.5">
							<Label for="agent-instructions">Instructions</Label>
							<Textarea id="agent-instructions" bind:value={draft.instructions} rows={8} maxlength={20000} placeholder="Always put in front of whatever task this agent is given. How it should work, what to produce, what to avoid." />
						</div>
					</section>

					{#if harness?.supports_skills}
						<section class="grid gap-3 rounded-xl border bg-card p-5">
							<div>
								<h3 class="text-base font-semibold tracking-tight">Skills</h3>
								<p class="text-sm text-muted-foreground">Guides it reads when a task calls for them.</p>
							</div>
							{#each skills as skill (skill.name)}
								<label class="flex items-start gap-3 rounded-lg border px-3 py-2.5">
									<Checkbox class="mt-0.5" checked={draft.skills.includes(skill.name)} onCheckedChange={(on) => (draft.skills = toggled(draft.skills, skill.name, !!on))} aria-label="Give it {skill.name}" />
									<span class="min-w-0 flex-1">
										<span class="block font-mono text-sm">{skill.name}</span>
										<span class="block text-xs text-muted-foreground">{skill.description || 'No description'}</span>
									</span>
								</label>
							{:else}
								<p class="text-sm text-muted-foreground">No skills yet. <a class="text-primary hover:underline" href="/projects/{projectId}#skills">Add some</a> on the project overview.</p>
							{/each}
						</section>
					{/if}

					{#if harness?.supports_mcp}
						<section class="grid gap-3 rounded-xl border bg-card p-5">
							<div>
								<h3 class="text-base font-semibold tracking-tight">Tools</h3>
								<p class="text-sm text-muted-foreground">Extra tools it can use while it works (MCP servers).</p>
							</div>
							{#each servers as server (server.id)}
								<label class="flex items-start gap-3 rounded-lg border px-3 py-2.5">
									<Checkbox class="mt-0.5" checked={draft.mcp_servers.includes(server.id)} onCheckedChange={(on) => (draft.mcp_servers = toggled(draft.mcp_servers, server.id, !!on))} aria-label="Give it {server.name}" />
									<span class="min-w-0 flex-1">
										<span class="block font-mono text-sm">{server.name}</span>
										<span class="block truncate font-mono text-xs text-muted-foreground">{server.kind === 'http' ? server.url : server.command}</span>
									</span>
								</label>
							{:else}
								<p class="text-sm text-muted-foreground">No tools yet. <a class="text-primary hover:underline" href="/projects/{projectId}#tools">Add some</a> on the project overview.</p>
							{/each}
							{#each warnings as warning (warning)}
								<p class="rounded-lg border border-yellow-500/30 bg-yellow-500/5 px-3 py-2 text-sm text-yellow-300" role="status">{warning}</p>
							{/each}
						</section>
					{/if}

					{#if harness?.supports_keys}
						<section class="grid gap-3 rounded-xl border bg-card p-5">
							<div>
								<h3 class="text-base font-semibold tracking-tight">Keys</h3>
								<p class="text-sm text-muted-foreground">
									Stored keys it can use, available to its commands as environment variables. Its output is scrubbed of their values, but only give a key to an agent you trust with it.
								</p>
							</div>
							{#each keys as key (key.id)}
								<label class="flex items-center gap-3 rounded-lg border px-3 py-2.5">
									<Checkbox checked={draft.secrets.includes(key.id)} disabled={!isAdmin} onCheckedChange={(on) => (draft.secrets = toggled(draft.secrets, key.id, !!on))} aria-label="Give it {key.name}" />
									<span class="min-w-0 flex-1 text-sm">{key.name}</span>
									<span class="font-mono text-xs text-muted-foreground">${key.env_name}</span>
								</label>
							{:else}
								<p class="text-sm text-muted-foreground">No keys stored yet. An administrator adds them under Settings, Keys.</p>
							{/each}
							{#if keys.length && !isAdmin}
								<p class="text-xs text-muted-foreground">Only an administrator can give an agent keys.</p>
							{/if}
						</section>
					{/if}

					<section class="grid gap-4 rounded-xl border bg-card p-5">
						<div>
							<h3 class="text-base font-semibold tracking-tight">Its cell</h3>
							<p class="text-sm text-muted-foreground">The container it runs in.</p>
						</div>
						{#key formVersion}
							<CellChoice
								bind:value={draft.cell_profile}
								{inherited}
								source="the project's cell"
								prefix="agent"
								imagePlaceholder={project?.cell_profile?.image ?? `The ${harness?.label ?? 'harness'} image from Settings`}
							/>
						{/key}
					</section>

					<section class="grid gap-4 rounded-xl border bg-card p-5">
						<div>
							<h3 class="text-base font-semibold tracking-tight">Folders it can reach</h3>
							<p class="text-sm text-muted-foreground">Shared folders mounted inside its workspace. A workflow can add more for a single step.</p>
						</div>
						{#key projectId}<MountsPicker {projectId} bind:value={draft.mounts} />{/key}
					</section>

					<div class="sticky bottom-4 z-10">
						<div class="flex items-center gap-3 rounded-xl border bg-popover/95 px-4 py-3 shadow-lg backdrop-blur">
							{#if current}
								<Button type="button" variant="ghost" class="text-destructive hover:text-destructive" onclick={() => (confirmOpen = true)}><Trash2Icon /> Delete</Button>
							{/if}
							<p class={cn('flex-1 text-sm', saveError ? 'text-destructive' : justSaved && !dirty ? 'text-emerald-400' : 'text-muted-foreground')} role={saveError ? 'alert' : 'status'}>
								{saveError || (justSaved && !dirty ? 'Saved' : dirty ? 'You have unsaved changes' : '')}
							</p>
							{#if isNew}
								<Button type="button" variant="ghost" onclick={() => router.navigate(`/projects/${projectId}/agents`)}>Cancel</Button>
							{:else}
								<Button type="button" variant="ghost" disabled={!dirty || saving} onclick={() => current && show(toInput(current))}>Discard</Button>
							{/if}
							<Button type="submit" disabled={saving || !draft.name.trim() || (!isNew && !dirty)}>{isNew ? 'Create agent' : 'Save changes'}</Button>
						</div>
					</div>
				</form>
			{/if}
		</div>
	{/if}
</div>

<AlertDialog.Root bind:open={confirmOpen}>
	<AlertDialog.Content>
		<AlertDialog.Header>
			<AlertDialog.Title>Delete this agent?</AlertDialog.Title>
			<AlertDialog.Description>
				"{current?.name}" is removed. Tasks it did stay, but workflow nodes that use it will fail until you pick another agent.
			</AlertDialog.Description>
		</AlertDialog.Header>
		<AlertDialog.Footer>
			<AlertDialog.Cancel>Keep it</AlertDialog.Cancel>
			<AlertDialog.Action onclick={remove}>Delete</AlertDialog.Action>
		</AlertDialog.Footer>
	</AlertDialog.Content>
</AlertDialog.Root>
