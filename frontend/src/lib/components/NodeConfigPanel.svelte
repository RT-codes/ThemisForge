<script lang="ts">
	import { api, type Agent, type CellDefaults, type ProfileOverrides, type Project } from '$lib/api'
	import { effectiveCell } from '$lib/cell'
	import CellChoice from '$lib/components/CellChoice.svelte'
	import MountsPicker from '$lib/components/MountsPicker.svelte'
	import { Button } from '$lib/components/ui/button/index.js'
	import { Input } from '$lib/components/ui/input/index.js'
	import { Label } from '$lib/components/ui/label/index.js'
	import * as Select from '$lib/components/ui/select/index.js'
	import { Textarea } from '$lib/components/ui/textarea/index.js'
	import { formatMounts, kindInfo, parseMounts, visibleFields, type FieldDef, type WorkflowNodeData } from '$lib/workflow'
	import { nodeIcons } from '$lib/workflowIcons'
	import Trash2Icon from '@lucide/svelte/icons/trash-2'
	import ChevronDownIcon from '@lucide/svelte/icons/chevron-down'
	import XIcon from '@lucide/svelte/icons/x'
	import { onMount, untrack } from 'svelte'
	import { slide } from 'svelte/transition'

	let {
		projectId,
		id,
		data,
		onchange,
		onclose,
		ondelete,
	}: {
		projectId: number
		id: string
		data: WorkflowNodeData
		onchange: (patch: Partial<WorkflowNodeData>) => void
		onclose: () => void
		ondelete: () => void
	} = $props()

	const info = $derived(kindInfo(data.kind))
	const Icon = $derived(nodeIcons[data.kind])
	const fields = $derived(visibleFields(data.kind, data.config))
	const mainFields = $derived(fields.filter((f) => !f.advanced))
	const advancedFields = $derived(fields.filter((f) => f.advanced && !CELL_KEYS.includes(f.key)))
	const setConfig = (key: string, value: string) => onchange({ config: { ...data.config, [key]: value } })

	// an agent node picks one of the project's agents; the node only keeps its id
	let agents = $state<Agent[]>([])
	let agentsLoaded = $state(false)
	let project = $state<Project | null>(null)
	let defaults = $state<CellDefaults | null>(null)
	onMount(async () => {
		if (data.kind !== 'agent') return
		try {
			;[agents, project, defaults] = await Promise.all([api.agents(projectId), api.project(projectId), api.systemStatus().then((s) => s.cell_defaults)])
		} catch {
			// the picker then only offers "no agent", and the cell is described without numbers
		} finally {
			agentsLoaded = true
		}
	})

	// The cell of this step is automatic (the agent's, which is the project's, which is the default) until customised.
	// The node keeps it as four plain text settings, like everything else on a node.
	const CELL_KEYS = ['cellCpus', 'cellMemory', 'cellTimeout', 'cellImage']
	const readCell = (c: Record<string, string>): ProfileOverrides | null => {
		const out: ProfileOverrides = {}
		if (c.cellCpus) out.cpus = Number(c.cellCpus)
		if (c.cellMemory) out.memory_mb = Number(c.cellMemory)
		if (c.cellTimeout) out.timeout_seconds = Number(c.cellTimeout)
		if (c.cellImage) out.image = c.cellImage
		return Object.keys(out).length ? out : null
	}
	let cell = $state<ProfileOverrides | null>(untrack(() => readCell(data.config)))
	$effect(() => {
		const next = cell
		untrack(() => {
			if (JSON.stringify(next) === JSON.stringify(readCell(data.config))) return
			onchange({
				config: {
					...data.config,
					cellCpus: next?.cpus != null ? String(next.cpus) : '',
					cellMemory: next?.memory_mb != null ? String(next.memory_mb) : '',
					cellTimeout: next?.timeout_seconds != null ? String(next.timeout_seconds) : '',
					cellImage: next?.image ?? '',
				},
			})
		})
	})
	const optionsOf = (f: FieldDef) =>
		f.key === 'agentId' ? [...(f.options ?? []), ...agents.map((a) => ({ value: String(a.id), label: a.name }))] : (f.options ?? [])
	function labelOf(f: FieldDef): string {
		const value = data.config[f.key]
		const found = optionsOf(f).find((o) => o.value === value)
		if (found) return found.label
		return f.key === 'agentId' && agentsLoaded ? 'An agent that was deleted' : ''
	}
	// open from the start when the node already has settings in there; after that it stays as the person left it
	let advancedOpen = $state(untrack(() => cell !== null || advancedFields.some((f) => (data.config[f.key] ?? '') !== '')))
	const chosenAgent = $derived(agents.find((a) => String(a.id) === data.config.agentId))
	const inheritedCell = $derived(defaults ? effectiveCell(defaults, project?.cell_profile, chosenAgent?.cell_profile) : null)
</script>

<div class="flex h-full w-80 flex-col">
	<div class="flex items-center gap-3 border-b px-4 py-3">
		<div class="flex size-8 shrink-0 items-center justify-center rounded-md bg-primary/15 text-primary"><Icon class="size-4" /></div>
		<div class="min-w-0 flex-1">
			<p class="truncate text-sm font-medium">{info.label} node</p>
			<p class="truncate text-xs text-muted-foreground">{info.description}</p>
		</div>
		<Button variant="ghost" size="icon-sm" aria-label="Close the panel" onclick={onclose}><XIcon /></Button>
	</div>

	<div class="grid min-h-0 flex-1 grid-cols-[minmax(0,1fr)] content-start gap-4 overflow-y-auto p-4">
		<div class="grid gap-1.5">
			<Label for="node-{id}-label">Name</Label>
			<Input id="node-{id}-label" value={data.label} oninput={(e) => onchange({ label: e.currentTarget.value })} />
		</div>

		{#snippet field(f: FieldDef)}
			<div class="grid gap-1.5" transition:slide={{ duration: 160 }}>
				<Label for="node-{id}-{f.key}">{f.label}</Label>
				{#if f.type === 'select'}
					<Select.Root type="single" value={data.config[f.key]} onValueChange={(v) => setConfig(f.key, v)}>
						<Select.Trigger id="node-{id}-{f.key}" class="w-full">{labelOf(f)}</Select.Trigger>
						<Select.Content>
							{#each optionsOf(f) as o (o.value)}<Select.Item value={o.value} label={o.label}>{o.label}</Select.Item>{/each}
						</Select.Content>
					</Select.Root>
				{:else if f.type === 'time'}
					<Input id="node-{id}-{f.key}" type="time" value={data.config[f.key]} oninput={(e) => setConfig(f.key, e.currentTarget.value)} />
				{:else if f.type === 'textarea'}
					<Textarea id="node-{id}-{f.key}" rows={5} placeholder={f.placeholder} value={data.config[f.key]} oninput={(e) => setConfig(f.key, e.currentTarget.value)} />
				{:else if f.type === 'mounts'}
					<MountsPicker {projectId} value={parseMounts(data.config[f.key] ?? '')} onchange={(m) => setConfig(f.key, formatMounts(m))} />
				{:else}
					<Input id="node-{id}-{f.key}" placeholder={f.placeholder} value={data.config[f.key]} oninput={(e) => setConfig(f.key, e.currentTarget.value)} />
				{/if}
				{#if f.key === 'agentId' && chosenAgent}
					<p class="text-xs text-muted-foreground">{chosenAgent.role || 'No role set'}. Its instructions come first; what you write below is the task it is given.</p>
				{/if}
				{#if f.hint}<p class="text-xs text-muted-foreground">{f.hint}</p>{/if}
			</div>
		{/snippet}

		{#each mainFields as f (f.key)}
			{@render field(f)}
		{/each}

		{#if advancedFields.length}
			<details class="group rounded-lg border" bind:open={advancedOpen}>
				<summary class="flex cursor-pointer list-none items-center gap-2 px-3 py-2.5 text-sm font-medium [&::-webkit-details-marker]:hidden">
					<span class="flex-1">Cell and folders</span>
					<ChevronDownIcon class="size-4 text-muted-foreground transition-transform group-open:rotate-180" />
				</summary>
				<div class="grid grid-cols-[minmax(0,1fr)] gap-4 border-t p-3">
					<p class="text-xs text-muted-foreground">Only for this step, on top of the agent's own cell and folders.</p>
					<div class="grid grid-cols-[minmax(0,1fr)] gap-1.5">
						<Label>Cell</Label>
						<CellChoice bind:value={cell} inherited={inheritedCell} source={chosenAgent ? "the agent's cell" : "the project's cell"} prefix="node-{id}" />
					</div>
					{#each advancedFields as f (f.key)}
						{@render field(f)}
					{/each}
				</div>
			</details>
		{/if}
	</div>

	<div class="border-t p-3">
		<Button variant="outline" size="sm" class="w-full text-destructive hover:text-destructive" onclick={ondelete}><Trash2Icon /> Delete node</Button>
	</div>
</div>
