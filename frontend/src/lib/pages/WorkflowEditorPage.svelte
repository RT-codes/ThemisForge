<script lang="ts">
	import { api, type WorkflowDetail, type WorkflowSummary } from '$lib/api'
	import { SvelteFlowProvider } from '@xyflow/svelte'
	import FlowCanvas from '$lib/components/FlowCanvas.svelte'
	import LoadWorkflowDialog from '$lib/components/LoadWorkflowDialog.svelte'
	import WorkflowRuns from '$lib/components/WorkflowRuns.svelte'
	import { Button } from '$lib/components/ui/button/index.js'
	import * as DropdownMenu from '$lib/components/ui/dropdown-menu/index.js'
	import * as Tabs from '$lib/components/ui/tabs/index.js'
	import { relative } from '$lib/format'
	import { projects } from '$lib/projects.svelte'
	import { router } from '$lib/router.svelte'
	import { nextWorkflowName, seedGraph, type Graph } from '$lib/workflow'
	import CheckIcon from '@lucide/svelte/icons/check'
	import ChevronDownIcon from '@lucide/svelte/icons/chevron-down'
	import ClockIcon from '@lucide/svelte/icons/clock'
	import FolderOpenIcon from '@lucide/svelte/icons/folder-open'
	import LoaderCircleIcon from '@lucide/svelte/icons/loader-circle'
	import SaveIcon from '@lucide/svelte/icons/save'
	import WorkflowIcon from '@lucide/svelte/icons/workflow'
	import { untrack } from 'svelte'

	// workflowId null: a new workflow that exists nowhere until the first change (or an explicit Save)
	let { projectId, workflowId, run = null }: { projectId: number; workflowId: number | null; run?: number | null } = $props()

	let workflow = $state<WorkflowDetail | null>(null)
	let initialGraph = $state<Graph>(seedGraph())
	let canvasKey = $state(0)
	let loading = $state(true)
	let error = $state('')
	let all = $state<WorkflowSummary[]>([])
	let name = $state('')
	let nameEdited = false // a name the user typed is kept; otherwise the server picks the first free "Workflow N"
	let renameError = $state('')
	let saveState = $state<'saved' | 'saving' | 'error'>('saved')
	let saving = $state(false)
	let loadOpen = $state(false)
	let canvas = $state<{ flush: () => Promise<void>; graph: () => Graph }>()
	let tab = $state<'editor' | 'runs'>('editor')
	let selectedRun = $state<number | null>(null)
	let current: number | null | undefined // the workflow this page is showing (undefined: nothing loaded yet)
	let creating: Promise<WorkflowDetail> | null = null
	const now = $derived(Date.now())

	const recent = $derived(
		[...all]
			.filter((w) => w.id !== workflow?.id)
			.sort((a, b) => b.updated_at.localeCompare(a.updated_at))
			.slice(0, 5)
	)

	// ----- loading and switching: the page follows the address -----

	async function load(id: number | null) {
		loading = true
		error = ''
		try {
			all = await api.workflows(projectId)
			if (id === null) {
				workflow = null
				initialGraph = seedGraph()
				name = nextWorkflowName(all.map((w) => w.name))
				nameEdited = false
			} else {
				const loaded = await api.workflow(id)
				if (loaded.project_id !== projectId) throw new Error('Workflow not found')
				workflow = loaded
				initialGraph = loaded.graph
				name = loaded.name
			}
			renameError = ''
			saveState = 'saved'
			canvasKey++
		} catch (e) {
			error = e instanceof Error ? e.message : 'Could not load the workflow'
		} finally {
			loading = false
		}
	}

	async function switchTo(id: number | null) {
		await canvas?.flush() // what was being edited is saved before it is replaced
		current = id
		const wanted = untrack(() => run)
		tab = wanted !== null && id !== null ? 'runs' : 'editor'
		selectedRun = id !== null ? wanted : null
		await load(id)
	}

	$effect(() => {
		const id = workflowId
		const wanted = run
		if (id !== current) untrack(() => switchTo(id))
		else if (wanted !== null) untrack(() => ((selectedRun = wanted), (tab = 'runs'))) // a link to another run of this workflow
	})

	// ----- saving: nothing exists until something has changed -----

	/** creates the workflow the first time it is needed; everyone who asks meanwhile gets the same one */
	function ensureCreated(graph: Graph): Promise<WorkflowDetail> {
		if (workflow) return Promise.resolve(workflow)
		creating ??= api
			.createWorkflow(projectId, { name: nameEdited ? name.trim() : undefined, graph })
			.then((created) => {
				workflow = created
				name = created.name
				current = created.id
				all = [{ ...created, node_count: created.graph.nodes.length, runs: 0, last_run: null }, ...all]
				// give it its real address, unless the user has already gone somewhere else
				if (router.path.endsWith('/workflows/new')) router.replace(`/projects/${projectId}/workflows/${created.id}`)
				return created
			})
			.finally(() => (creating = null))
		return creating
	}

	async function persist(graph: Graph) {
		const existing = workflow // read before anything awaits: the page may be switching to another workflow
		if (!existing) {
			await ensureCreated(graph)
			return
		}
		workflow = { ...existing, ...(await api.updateWorkflow(existing.id, { graph })) }
	}

	/** the Save button: save what is there, and keep a new workflow even if it is still untouched */
	async function save() {
		saving = true
		try {
			if (!workflow) await ensureCreated(canvas?.graph() ?? seedGraph())
			else await canvas?.flush()
		} catch (e) {
			renameError = e instanceof Error ? e.message : 'Could not save'
		} finally {
			saving = false
		}
	}

	async function rename() {
		const wanted = name.trim()
		if (!wanted) {
			name = workflow?.name ?? nextWorkflowName(all.map((w) => w.name))
			if (workflow) renameError = 'A workflow needs a name'
			return
		}
		if (workflow ? wanted === workflow.name : !nameEdited && wanted === nextWorkflowName(all.map((w) => w.name))) return
		try {
			renameError = ''
			if (!workflow) {
				nameEdited = true // renaming is a change: the workflow now exists
				await ensureCreated(canvas?.graph() ?? seedGraph())
				return
			}
			const updated = await api.updateWorkflow(workflow.id, { name: wanted })
			workflow = { ...workflow, ...updated }
			name = updated.name
			all = all.map((w) => (w.id === updated.id ? { ...w, name: updated.name, updated_at: updated.updated_at } : w))
		} catch (e) {
			renameError = e instanceof Error ? e.message : 'Could not rename'
			name = workflow?.name ?? name
		}
	}

	async function test() {
		const created = await ensureCreated(canvas?.graph() ?? seedGraph())
		await canvas?.flush()
		const started = await api.startWorkflowRun(created.id)
		selectedRun = started.id
		tab = 'runs'
	}

	const open = (id: number) => router.navigate(`/projects/${projectId}/workflows/${id}`)
	const startNew = () => router.navigate(`/projects/${projectId}/workflows/new`)
	const refreshRecent = (isOpen: boolean) => isOpen && api.workflows(projectId).then((list) => (all = list)).catch(() => {})

	const saveLabel = $derived(
		saving || saveState === 'saving' ? 'Saving' : saveState === 'error' ? 'Retry save' : workflow ? 'Saved' : 'Save'
	)
	const saveDisabled = $derived(saving || (!!workflow && saveState === 'saved'))
</script>

{#if error}
	<div class="m-auto text-center">
		<p class="text-lg font-medium">Workflow not found</p>
		<p class="mt-1 text-sm text-muted-foreground">{error}</p>
		<a href="/projects/{projectId}#workflows" class="mt-3 inline-block text-sm text-primary hover:underline">Back to the project</a>
	</div>
{:else if loading || !projects.loaded}
	<div class="min-h-0 flex-1"></div>
{:else}
	<div class="flex min-h-0 flex-1 flex-col">
		<div class="flex items-center gap-4 border-b px-6 py-3">
			<div class="inline-flex shrink-0 items-center gap-0.5 rounded-lg border bg-card p-0.5" role="group" aria-label="Workflow actions">
				<Button variant="ghost" size="sm" class="h-8 gap-1.5" disabled={saveDisabled} onclick={save} title="Save this workflow">
					{#if saving || saveState === 'saving'}<LoaderCircleIcon class="animate-spin" />{:else if workflow && saveState === 'saved'}<CheckIcon class="text-emerald-400" />{:else}<SaveIcon />{/if}
					{saveLabel}
				</Button>
				<span class="h-4 w-px bg-border" aria-hidden="true"></span>
				<Button variant="ghost" size="sm" class="h-8 gap-1.5" onclick={() => (loadOpen = true)} title="Open another workflow of this project">
					<FolderOpenIcon /> Load
				</Button>
				<span class="h-4 w-px bg-border" aria-hidden="true"></span>
				<DropdownMenu.Root onOpenChange={refreshRecent}>
					<DropdownMenu.Trigger>
						{#snippet child({ props })}
							<Button {...props} variant="ghost" size="sm" class="h-8 gap-1.5" title="The workflows you edited last">
								<ClockIcon /> Recent <ChevronDownIcon class="size-3.5 opacity-60" />
							</Button>
						{/snippet}
					</DropdownMenu.Trigger>
					<DropdownMenu.Content align="start" class="w-72">
						<DropdownMenu.Label class="text-xs text-muted-foreground">Recently edited</DropdownMenu.Label>
						{#each recent as w (w.id)}
							<DropdownMenu.Item onSelect={() => open(w.id)} class="gap-2.5">
								<span class="flex size-6 shrink-0 items-center justify-center rounded bg-primary/15 text-primary"><WorkflowIcon class="size-3.5" /></span>
								<span class="min-w-0 flex-1">
									<span class="block truncate text-sm">{w.name}</span>
									<span class="block text-xs text-muted-foreground">{relative(w.updated_at, now)}</span>
								</span>
							</DropdownMenu.Item>
						{:else}
							<p class="px-2 py-3 text-center text-xs text-muted-foreground">No other workflows yet.</p>
						{/each}
						<DropdownMenu.Separator />
						<DropdownMenu.Item onSelect={() => (loadOpen = true)} class="gap-2 text-xs"><FolderOpenIcon class="size-3.5" /> All workflows...</DropdownMenu.Item>
					</DropdownMenu.Content>
				</DropdownMenu.Root>
			</div>

			<div class="min-w-0 flex-1">
				<input
					bind:value={name}
					onblur={rename}
					onkeydown={(e) => e.key === 'Enter' && e.currentTarget.blur()}
					aria-label="Workflow name"
					maxlength="100"
					class="-ms-2 block w-full min-w-0 rounded-md border border-transparent bg-transparent px-2 py-1 text-lg font-semibold tracking-tight transition-colors outline-none hover:border-border focus:border-ring"
				/>
				{#if renameError}<p class="-mt-0.5 text-xs text-destructive" role="alert">{renameError}</p>{/if}
			</div>

			<Tabs.Root bind:value={tab} class="shrink-0">
				<Tabs.List>
					<Tabs.Trigger value="editor">Editor</Tabs.Trigger>
					<Tabs.Trigger value="runs">Runs</Tabs.Trigger>
				</Tabs.List>
			</Tabs.Root>
		</div>

		{#if tab === 'editor'}
			{#key canvasKey}
				<SvelteFlowProvider>
					<FlowCanvas bind:this={canvas} {initialGraph} onsave={persist} ontest={test} bind:saveState draft={!workflow} />
				</SvelteFlowProvider>
			{/key}
		{:else if workflow}
			<WorkflowRuns workflowId={workflow.id} bind:selected={selectedRun} />
		{:else}
			<div class="m-auto max-w-xs text-center">
				<p class="text-sm font-medium">No runs yet</p>
				<p class="mt-1 text-xs text-muted-foreground">This workflow is not saved yet. Make a change, then press Test run in the editor.</p>
			</div>
		{/if}
	</div>
{/if}

<LoadWorkflowDialog bind:open={loadOpen} {projectId} currentId={workflow?.id ?? null} onpick={open} onnew={startNew} />
