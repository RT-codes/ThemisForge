<script lang="ts">
	import type { KeyInfo } from '$lib/api/agents'
	import { projectsApi, type ProjectSummary } from '$lib/api/projects'
	import type { McpInput, McpServer } from '$lib/api/tools'
	import McpForm from '$lib/components/McpForm.svelte'
	import RegistryBrowser from '$lib/components/RegistryBrowser.svelte'
	import { Button } from '$lib/components/ui/button/index.js'
	import * as Dialog from '$lib/components/ui/dialog/index.js'
	import { Label } from '$lib/components/ui/label/index.js'
	import * as Select from '$lib/components/ui/select/index.js'

	// Adding a tool from the MCP registry, in three steps: browse, (when it was started from Settings) say which project
	// it is for, then the normal tool form with the fields filled in. It is used from a project's Tools section, where the
	// project is known, and from Settings, where it is not. Tools belong to a project, so this never makes one anywhere
	// else.
	let {
		open = $bindable(false),
		projectId,
		keys,
		onadded,
	}: {
		open: boolean
		projectId: number | null
		keys: KeyInfo[]
		onadded: (server: McpServer, project: { id: number; name: string }) => void
	} = $props()

	let stage = $state<'browse' | 'project' | 'form'>('browse')
	let fields = $state<McpInput | null>(null)
	let projects = $state<ProjectSummary[]>([])
	let chosen = $state<number | null>(null)
	let loadError = $state('')

	// every time it is opened it starts at the list
	$effect(() => {
		if (open) {
			stage = 'browse'
			fields = null
			chosen = projectId
		}
	})

	async function picked(f: McpInput) {
		fields = f
		if (projectId !== null) {
			stage = 'form'
			return
		}
		stage = 'project'
		try {
			projects = await projectsApi.projects()
			chosen = projects.length === 1 ? projects[0].id : null
			loadError = projects.length ? '' : 'There are no projects yet. Make one first, then add the tool to it.'
		} catch (e) {
			loadError = e instanceof Error ? e.message : 'Could not load your projects'
		}
	}

	const target = $derived(projectId ?? chosen)
	const targetName = $derived(projects.find((p) => p.id === target)?.name ?? '')

	function saved(server: McpServer) {
		open = false
		if (target !== null) onadded(server, { id: target, name: targetName })
	}
</script>

<Dialog.Root bind:open>
	{#if stage === 'browse'}
		<Dialog.Content class="h-[88vh] max-h-[88vh] grid-rows-[auto_minmax(0,1fr)] gap-3 p-5 sm:max-w-6xl">
			<Dialog.Header>
				<Dialog.Title>Add a tool from the MCP registry</Dialog.Title>
				<Dialog.Description>
					The official registry lists tools anyone has published; nobody vets them. Tools Themis cannot run yet are greyed out.
				</Dialog.Description>
			</Dialog.Header>
			{#if open}<RegistryBrowser {projectId} {keys} onpick={picked} oncancel={() => (open = false)} />{/if}
		</Dialog.Content>
	{:else if stage === 'project'}
		<Dialog.Content class="sm:max-w-md">
			<Dialog.Header>
				<Dialog.Title>Which project is it for?</Dialog.Title>
				<Dialog.Description>
					A tool belongs to a project, and agents of that project can be given it. Keys are shared, so the same key can serve tools in
					several projects.
				</Dialog.Description>
			</Dialog.Header>
			<div class="grid gap-1.5">
				<Label for="registry-project">Project</Label>
				<Select.Root type="single" value={chosen === null ? '' : String(chosen)} onValueChange={(v) => (chosen = Number(v))}>
					<Select.Trigger id="registry-project" class="w-full">{targetName || 'Choose a project'}</Select.Trigger>
					<Select.Content>
						{#each projects as p (p.id)}<Select.Item value={String(p.id)} label={p.name}>{p.name}</Select.Item>{/each}
					</Select.Content>
				</Select.Root>
				{#if loadError}<p class="text-sm text-muted-foreground" role="status">{loadError}</p>{/if}
			</div>
			<div class="flex justify-between gap-2">
				<Button variant="ghost" onclick={() => (stage = 'browse')}>Back to the list</Button>
				<Button disabled={chosen === null} onclick={() => (stage = 'form')}>Continue</Button>
			</div>
		</Dialog.Content>
	{:else if fields && target !== null}
		<Dialog.Content class="sm:max-w-xl">
			<Dialog.Header>
				<Dialog.Title>Add {fields.name}{targetName ? ` to ${targetName}` : ''}</Dialog.Title>
				<Dialog.Description>
					Filled in from the MCP registry. Check it over, then create it. Test connection is available once it is saved.
				</Dialog.Description>
			</Dialog.Header>
			{#key `${target}:${fields.name}`}
				<McpForm projectId={target} server={null} prefill={fields} {keys} oncancel={() => (open = false)} onsaved={saved} />
			{/key}
		</Dialog.Content>
	{/if}
</Dialog.Root>
