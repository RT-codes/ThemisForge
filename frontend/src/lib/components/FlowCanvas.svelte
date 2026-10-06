<script lang="ts">
	import { Background, Controls, MarkerType, MiniMap, SvelteFlow, useSvelteFlow, type Connection, type Edge, type Node } from '@xyflow/svelte'
	import '@xyflow/svelte/dist/style.css'
	import { api } from '$lib/api'
	import { Button } from '$lib/components/ui/button/index.js'
	import LoaderCircleIcon from '@lucide/svelte/icons/loader-circle'
	import PlayIcon from '@lucide/svelte/icons/play'
	import Trash2Icon from '@lucide/svelte/icons/trash-2'
	import { DRAG_TYPE, NODE_KINDS, defaultConfig, fromGraph, kindInfo, nextNodeNumber, toGraph, type NodeKind, type WorkflowNodeData } from '$lib/workflow'
	import { onDestroy, onMount } from 'svelte'
	import { nodeIcons } from '$lib/workflowIcons'
	import { slide } from 'svelte/transition'
	import NodeConfigPanel from './NodeConfigPanel.svelte'
	import WorkflowNode from './WorkflowNode.svelte'

	let { projectId, onrun }: { projectId: number; onrun: (runId: number) => void } = $props()

	const nodeTypes = { workflow: WorkflowNode }
	const { screenToFlowPosition, deleteElements, fitView } = useSvelteFlow()

	let nodes = $state.raw<Node[]>([])
	let edges = $state.raw<Edge[]>([])
	let counter = 0
	let wrapper: HTMLDivElement

	// ----- saving: the workflow is kept on the server and saved shortly after every change -----
	let loaded = $state(false)
	let loadError = $state('')
	let saveState = $state<'saved' | 'saving' | 'error'>('saved')
	let lastSaved = ''
	let saveTimer: ReturnType<typeof setTimeout> | undefined
	const signature = $derived(JSON.stringify(toGraph(nodes, edges)))

	onMount(async () => {
		try {
			const { graph } = await api.workflow(projectId)
			const flow = fromGraph(graph)
			nodes = flow.nodes
			edges = flow.edges
			counter = nextNodeNumber(graph.nodes.map((n) => n.id))
			lastSaved = JSON.stringify(toGraph(nodes, edges))
			setTimeout(() => fitView({ maxZoom: 1, padding: 0.15 }), 50)
		} catch (e) {
			loadError = e instanceof Error ? e.message : 'Could not load the workflow'
		}
		loaded = true
	})

	$effect(() => {
		if (!loaded || signature === lastSaved) return
		saveState = 'saving'
		clearTimeout(saveTimer)
		saveTimer = setTimeout(flush, 700)
	})

	async function flush() {
		clearTimeout(saveTimer)
		const sig = signature
		if (!loaded || loadError || sig === lastSaved) return
		try {
			await api.saveWorkflow(projectId, JSON.parse(sig))
			lastSaved = sig
			saveState = signature === sig ? 'saved' : 'saving'
		} catch {
			saveState = 'error'
		}
	}
	onDestroy(() => void flush())

	// ----- testing -----
	let testing = $state(false)
	let testError = $state('')
	const hasStart = $derived(nodes.some((n) => ['start', 'trigger'].includes((n.data as WorkflowNodeData).kind)))

	async function test() {
		testError = ''
		testing = true
		try {
			await flush()
			onrun((await api.startWorkflowRun(projectId)).id)
		} catch (e) {
			testError = e instanceof Error ? e.message : 'Could not start the run'
		} finally {
			testing = false
		}
	}

	const hasSelection = $derived(nodes.some((n) => n.selected) || edges.some((e) => e.selected))
	// the panel on the right configures the node when exactly one is selected
	const selectedNodes = $derived(nodes.filter((n) => n.selected))
	const active = $derived(selectedNodes.length === 1 ? selectedNodes[0] : null)

	function updateNode(id: string, patch: Partial<WorkflowNodeData>) {
		nodes = nodes.map((n) => (n.id === id ? { ...n, data: { ...n.data, ...patch } } : n))
	}
	const deselectAll = () => (nodes = nodes.map((n) => ({ ...n, selected: false })))

	function addNode(kind: NodeKind, position: { x: number; y: number }) {
		const label = kindInfo(kind).label
		nodes = [...nodes.map((n) => ({ ...n, selected: false })), { id: `n${++counter}`, type: 'workflow', position, selected: true, data: { kind, label, config: defaultConfig(kind) } }]
	}

	// step to the right until the spot is not on top of another node (nodes are about 208 x 56)
	function freeSpot(at: { x: number; y: number }) {
		const taken = (x: number) => nodes.some((n) => Math.abs(n.position.x - x) < 232 && Math.abs(n.position.y - at.y) < 72)
		let x = at.x
		while (taken(x)) x += 248
		return { x, y: at.y }
	}

	// a click on the palette drops the node in the middle of the canvas, beside any node already there
	function addAtCenter(kind: NodeKind) {
		// next to the selected (or latest) node, so a flow reads left to right; the canvas centre when it is empty
		const anchor = active ?? nodes.at(-1)
		let at: { x: number; y: number }
		if (anchor) at = { x: anchor.position.x + 248, y: anchor.position.y }
		else {
			const r = wrapper.getBoundingClientRect()
			const p = screenToFlowPosition({ x: r.left + r.width / 2, y: r.top + r.height / 2 })
			at = { x: p.x - 104, y: p.y - 28 }
		}
		addNode(kind, freeSpot(at))
		// bring the whole graph into view; wait for the config panel to finish sliding in, which resizes the canvas
		setTimeout(() => fitView({ maxZoom: 1, padding: 0.25, duration: 350 }), 240)
	}

	function onDrop(e: DragEvent) {
		const kind = e.dataTransfer?.getData(DRAG_TYPE) as NodeKind | undefined
		if (!kind) return
		e.preventDefault()
		const p = screenToFlowPosition({ x: e.clientX, y: e.clientY })
		addNode(kind, { x: p.x - 104, y: p.y - 28 })
	}

	function onDragOver(e: DragEvent) {
		if (!e.dataTransfer?.types.includes(DRAG_TYPE)) return
		e.preventDefault()
		e.dataTransfer.dropEffect = 'move'
	}

	// a node cannot connect to itself
	const isValidConnection = (c: Connection | Edge) => c.source !== c.target

	const deleteSelected = () => deleteElements({ nodes: nodes.filter((n) => n.selected), edges: edges.filter((e) => e.selected) })
</script>

<div class="flex min-h-0 flex-1">
	<aside class="flex w-44 shrink-0 flex-col gap-1 border-e p-2">
		<Button class="h-8 w-full" disabled={!loaded || testing || !hasStart || !!loadError} onclick={test}>
			{#if testing}<LoaderCircleIcon class="animate-spin" />{:else}<PlayIcon />{/if} Test run
		</Button>
		{#if testError}
			<p class="px-1 text-[11px] leading-snug text-destructive" role="alert">{testError}</p>
		{:else if loadError}
			<p class="px-1 text-[11px] leading-snug text-destructive" role="alert">{loadError}</p>
		{:else if !hasStart}
			<p class="px-1 text-[11px] leading-snug text-muted-foreground">Add a Start node to test.</p>
		{:else}
			<p class={`px-1 text-[11px] leading-snug transition-colors ${saveState === 'error' ? 'text-destructive' : 'text-muted-foreground'}`}>
				{saveState === 'saving' ? 'Saving...' : saveState === 'error' ? 'Could not save' : 'All changes saved'}
			</p>
		{/if}
		<div class="my-1.5 border-t"></div>
		<p class="px-1.5 pb-0.5 text-[11px] font-medium tracking-wide text-muted-foreground uppercase">Nodes</p>
		{#each NODE_KINDS as k (k.kind)}
			{@const Icon = nodeIcons[k.kind]}
			<button
				type="button"
				draggable="true"
				title={k.description}
				class="flex cursor-grab items-center gap-2 rounded-md border bg-card px-2 py-1.5 text-start text-sm transition-colors hover:border-primary/50 hover:bg-accent/40 active:cursor-grabbing"
				ondragstart={(e) => {
					e.dataTransfer?.setData(DRAG_TYPE, k.kind)
					if (e.dataTransfer) e.dataTransfer.effectAllowed = 'move'
				}}
				onclick={() => addAtCenter(k.kind)}
			>
				<span class="flex size-5 shrink-0 items-center justify-center rounded bg-primary/15 text-primary"><Icon class="size-3" /></span>
				<span class="truncate">{k.label}</span>
			</button>
		{/each}
		<p class="px-1.5 pt-1 text-[11px] leading-snug text-muted-foreground">Click or drag onto the canvas. Drag between the dots to connect. The Test run starts at every Start node.</p>
		<div class="mt-auto flex flex-col gap-1.5">
			<Button variant="outline" size="sm" class="h-7 text-xs" disabled={!hasSelection} onclick={deleteSelected}><Trash2Icon class="size-3.5" /> Delete selected</Button>
			<Button variant="outline" size="sm" class="h-7 text-xs" disabled={nodes.length === 0} onclick={() => deleteElements({ nodes, edges })}>Clear canvas</Button>
		</div>
	</aside>

	<div class="min-w-0 flex-1" bind:this={wrapper} role="presentation" ondrop={onDrop} ondragover={onDragOver}>
		<SvelteFlow
			bind:nodes
			bind:edges
			{nodeTypes}
			{isValidConnection}
			colorMode="dark"
			deleteKey={['Backspace', 'Delete']}
			defaultEdgeOptions={{ animated: true, style: 'stroke: var(--primary)', markerEnd: { type: MarkerType.ArrowClosed } }}
			fitView
			fitViewOptions={{ maxZoom: 1, padding: 0.3 }}
			minZoom={0.2}
		>
			<Background gap={24} />
			<Controls showLock={false} />
			<MiniMap pannable zoomable />
		</SvelteFlow>
	</div>
	{#if active}
		<aside transition:slide={{ axis: 'x', duration: 220 }} class="shrink-0 overflow-hidden border-s bg-background">
			{#key active.id}
				<NodeConfigPanel
					id={active.id}
					data={active.data as WorkflowNodeData}
					onchange={(patch) => updateNode(active.id, patch)}
					onclose={deselectAll}
					ondelete={() => deleteElements({ nodes: [{ id: active.id }] })}
				/>
			{/key}
		</aside>
	{/if}
</div>
