<script lang="ts">
	import { api, ApiError, type Agent, type AgentInput, type CellDefaults, type HarnessInfo, type KeyInfo, type McpServer, type Project, type Skill } from '$lib/api'
	import { auth } from '$lib/auth.svelte'
	import CellChoice from '$lib/components/CellChoice.svelte'
	import MountsPicker from '$lib/components/MountsPicker.svelte'
	import SkillPicker from '$lib/components/SkillPicker.svelte'
	import ToolPicker from '$lib/components/ToolPicker.svelte'
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
	import Trash2Icon from '@lucide/svelte/icons/trash-2'
	import { untrack } from 'svelte'
	import type { AgentCounts, AgentTab } from '$lib/agentTabs'

	// The editor of one agent (or of a new one). The settings are saved together with the Save button. Skills and tools
	// can be read and changed right here as well: those edits are saved as they are made, because they change files that
	// other agents share, and only the switches that give them to this agent wait for Save.
	let {
		projectId,
		agent,
		harnesses,
		project,
		defaults,
		keys,
		skills = $bindable(),
		servers = $bindable(),
		tab = $bindable('general'),
		counts = $bindable({ skills: 0, tools: 0, hasSkills: true, hasTools: true }),
		onsaved,
		onclose,
		ondeleted,
		onchanged,
	}: {
		projectId: number
		agent: Agent | null // null: a new agent
		harnesses: HarnessInfo[]
		project: Project | null
		defaults: CellDefaults | null
		keys: KeyInfo[]
		skills: Skill[]
		servers: McpServer[]
		tab?: AgentTab // which part is shown: the page puts the tabs above the panel
		counts?: AgentCounts // what the tabs say about this agent, for the page
		onsaved: (agent: Agent, created: boolean) => void
		onclose: () => void // back to the overview of the agent (or the list, for a new one)
		ondeleted: () => void
		onchanged: () => void // a skill or tool was deleted, which changed other agents too
	} = $props()

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

	const first = untrack(() => (agent ? toInput(agent) : blank()))
	let draft = $state<AgentInput>(first)
	let baseline = $state(JSON.stringify(first))
	let warnings = $state<string[]>([]) // tools whose command is not in the image the agent runs in
	let saving = $state(false)
	let saveError = $state('')
	let justSaved = $state(false)
	let confirmOpen = $state(false)
	let formVersion = $state(0) // bumped whenever the form is reloaded, so the cell control starts from the saved agent

	let skillsDirty = $state(false)
	let toolsDirty = $state(false)
	const dirty = $derived(JSON.stringify(draft) !== baseline)
	const anything = $derived(dirty || skillsDirty || toolsDirty)
	const isNew = $derived(agent === null)
	// what an agent's cell is when it does not customise it: the project's cell, on top of the global defaults
	const inherited = $derived(defaults ? effectiveCell(defaults, project?.cell_profile) : null)
	const harness = $derived(harnesses.find((h) => h.id === draft.harness))
	const isAdmin = $derived(!!auth.user?.is_admin)
	const efforts = [
		{ value: '', label: 'Default from Settings' },
		{ value: 'low', label: 'Low' },
		{ value: 'medium', label: 'Medium' },
		{ value: 'high', label: 'High' },
	]

	$effect(() => {
		counts = { skills: draft.skills.length, tools: draft.mcp_servers.length, hasSkills: !!harness?.supports_skills, hasTools: !!harness?.supports_mcp }
	})

	function show(input: AgentInput) {
		draft = input
		formVersion++
		baseline = JSON.stringify(input)
		saveError = ''
	}

	async function save(e: SubmitEvent) {
		e.preventDefault()
		saveError = ''
		saving = true
		try {
			const created = agent === null
			const saved = agent === null ? await api.createAgent(projectId, draft) : await api.updateAgent(agent.id, draft)
			show(toInput(saved))
			onsaved(saved, created)
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
		if (!agent) return
		try {
			await api.deleteAgent(agent.id)
			ondeleted()
		} catch (err) {
			saveError = err instanceof ApiError || err instanceof Error ? err.message : 'Could not delete the agent'
		}
	}

	// A skill or tool was deleted from the editor: the server took it off every agent, so this form's copy (and what it
	// counts as saved) forgets it too, or it would call the agent changed.
	function rebase(change: (a: AgentInput) => void) {
		change(draft)
		const saved = JSON.parse(baseline) as AgentInput
		change(saved)
		baseline = JSON.stringify(saved)
		onchanged()
	}

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

	// ----- leaving with unsaved changes -----

	let leaving = $state<(() => void) | null>(null)
	$effect(() => {
		router.guard = (go) => {
			if (!anything) return false
			leaving = go
			return true
		}
		return () => (router.guard = null)
	})
</script>

<svelte:window onbeforeunload={(e) => anything && e.preventDefault()} />

<form onsubmit={save} class="flex min-h-0 flex-1 flex-col gap-3">
	<!-- every tab stays mounted and is only hidden, so a skill or tool being edited keeps its place while another tab is open -->
	<div role="tabpanel" hidden={tab !== 'general'} class="grid gap-5">
	<section class="grid gap-3 border-t pt-5 first:border-t-0 first:pt-0">
			<h3 class="text-sm font-semibold tracking-tight">Who it is</h3>
			<div class="grid gap-3 sm:grid-cols-2">
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
	
		<section class="grid gap-3 border-t pt-5 first:border-t-0 first:pt-0">
			<h3 class="text-sm font-semibold tracking-tight">How it works</h3>
			<div class="grid gap-3 sm:grid-cols-3">
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
				<Textarea id="agent-instructions" bind:value={draft.instructions} rows={6} maxlength={20000} placeholder="Always put in front of whatever task this agent is given. How it should work, what to produce, what to avoid." />
			</div>
		</section>
	
		{#if harness?.supports_keys}
			<section class="grid gap-3 border-t pt-5">
				<div>
					<h3 class="text-sm font-semibold tracking-tight">Keys</h3>
					<p class="text-xs text-muted-foreground">
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
	
		<section class="grid gap-3 border-t pt-5 first:border-t-0 first:pt-0">
			<div>
				<h3 class="text-sm font-semibold tracking-tight">Its cell</h3>
				<p class="text-xs text-muted-foreground">The container it runs in.</p>
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
	
		<section class="grid gap-3 border-t pt-5 first:border-t-0 first:pt-0">
			<div>
				<h3 class="text-sm font-semibold tracking-tight">Folders it can reach</h3>
				<p class="text-xs text-muted-foreground">Shared folders mounted inside its workspace. A workflow can add more for a single step.</p>
			</div>
			{#key projectId}<MountsPicker {projectId} bind:value={draft.mounts} />{/key}
		</section>
	
	</div>

	<div role="tabpanel" hidden={tab !== 'skills'} class="flex min-h-0 flex-1 flex-col">
	{#if harness?.supports_skills}
			<section class="flex min-h-0 flex-1 flex-col gap-3">
				<div>
					<h3 class="text-sm font-semibold tracking-tight">Skills</h3>
					<p class="text-xs text-muted-foreground">Guides it reads when a task calls for them. Every skill of the project is here: switch on the ones this agent should have, and open one to read or change it.</p>
				</div>
				<SkillPicker {projectId} bind:selected={draft.skills} bind:skills bind:dirty={skillsDirty} canEdit onremoved={(name) => rebase((a) => (a.skills = a.skills.filter((x) => x !== name)))} />
			</section>
		{/if}
	
	</div>

	<div role="tabpanel" hidden={tab !== 'tools'} class="flex min-h-0 flex-1 flex-col">
	{#if harness?.supports_mcp}
			<section class="flex min-h-0 flex-1 flex-col gap-3">
				<div>
					<h3 class="text-sm font-semibold tracking-tight">Tools</h3>
					<p class="text-xs text-muted-foreground">Extra tools it can use while it works (MCP servers). Switch on the ones this agent should have, and open one to change it or test the connection.</p>
				</div>
				<ToolPicker {projectId} bind:selected={draft.mcp_servers} bind:servers {keys} bind:dirty={toolsDirty} canEdit onremoved={(id) => rebase((a) => (a.mcp_servers = a.mcp_servers.filter((x) => x !== id)))} />
				{#each warnings as warning (warning)}
					<p class="rounded-lg border border-yellow-500/30 bg-yellow-500/5 px-3 py-2 text-sm text-yellow-300" role="status">{warning}</p>
				{/each}
			</section>
		{/if}
	
	</div>

	<div class="sticky bottom-0 z-10 mt-auto pt-1">
		<div class="flex items-center gap-2 rounded-lg border bg-popover/95 px-3 py-2 shadow-lg backdrop-blur">
			{#if agent}
				<Button type="button" size="sm" variant="ghost" class="text-destructive hover:text-destructive" onclick={() => (confirmOpen = true)}><Trash2Icon /> Delete</Button>
			{/if}
			<p class={cn('flex-1 text-sm', saveError ? 'text-destructive' : justSaved && !anything ? 'text-emerald-400' : 'text-muted-foreground')} role={saveError ? 'alert' : 'status'}>
				{saveError || (anything ? (dirty ? 'You have unsaved changes' : 'A file you are editing is not saved yet') : justSaved ? 'Saved' : '')}
			</p>
			{#if isNew}
				<Button type="button" size="sm" variant="ghost" onclick={onclose}>Cancel</Button>
			{:else}
				<Button type="button" size="sm" variant="ghost" disabled={!dirty || saving} onclick={() => agent && show(toInput(agent))}>Discard</Button>
				<Button type="button" size="sm" variant="outline" onclick={onclose}>Done</Button>
			{/if}
			<Button type="submit" size="sm" disabled={saving || !draft.name.trim() || (!isNew && !dirty)}>{isNew ? 'Create agent' : 'Save changes'}</Button>
		</div>
	</div>
</form>

<AlertDialog.Root bind:open={confirmOpen}>
	<AlertDialog.Content>
		<AlertDialog.Header>
			<AlertDialog.Title>Delete this agent?</AlertDialog.Title>
			<AlertDialog.Description>
				"{agent?.name}" is removed, together with its file in the config folder. Tasks it did stay, but workflow nodes that use it will fail until you pick another agent.
			</AlertDialog.Description>
		</AlertDialog.Header>
		<AlertDialog.Footer>
			<AlertDialog.Cancel>Keep it</AlertDialog.Cancel>
			<AlertDialog.Action onclick={remove}>Delete</AlertDialog.Action>
		</AlertDialog.Footer>
	</AlertDialog.Content>
</AlertDialog.Root>

<AlertDialog.Root open={leaving !== null} onOpenChange={(o) => !o && (leaving = null)}>
	<AlertDialog.Content>
		<AlertDialog.Header>
			<AlertDialog.Title>You have unsaved changes</AlertDialog.Title>
			<AlertDialog.Description>
				{dirty ? 'The agent was changed and not saved.' : 'A file you are editing was changed and not saved.'} Keep editing, or discard the changes and go on.
			</AlertDialog.Description>
		</AlertDialog.Header>
		<AlertDialog.Footer>
			<AlertDialog.Cancel>Keep editing</AlertDialog.Cancel>
			<AlertDialog.Action
				onclick={() => {
					const go = leaving
					leaving = null
					go?.()
				}}>Discard changes</AlertDialog.Action
			>
		</AlertDialog.Footer>
	</AlertDialog.Content>
</AlertDialog.Root>
