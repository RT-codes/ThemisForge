<script lang="ts">
	import { Background, Controls, MarkerType, MiniMap, SvelteFlow, useSvelteFlow, type Connection, type Edge, type Node } from '@xyflow/svelte'
	import '@xyflow/svelte/dist/style.css'
	import { Button } from '$lib/components/ui/button/index.js'
	import Trash2Icon from '@lucide/svelte/icons/trash-2'
	import { DRAG_TYPE, NODE_KINDS, kindInfo, type NodeKind } from '$lib/workflow'
	import WorkflowNode from './WorkflowNode.svelte'

	const nodeTypes = { workflow: WorkflowNode }
	const { screenToFlowPosition, deleteElements } = useSvelteFlow()

	let nodes = $state.raw<Node[]>([])
	let edges = $state.raw<Edge[]>([])
	let counter = 0
	let wrapper: HTMLDivElement

	const hasSelection = $derived(nodes.some((n) => n.selected) || edges.some((e) => e.selected))

	function addNode(kind: NodeKind, position: { x: number; y: number }) {
		const label = kindInfo(kind).label
		nodes = [...nodes.map((n) => ({ ...n, selected: false })), { id: `n${++counter}`, type: 'workflow', position, selected: true, data: { kind, label } }]
	}

	// a click on the palette drops the node in the middle of the canvas, nudged so repeated clicks do not stack
	function addAtCenter(kind: NodeKind) {
		const r = wrapper.getBoundingClientRect()
		const nudge = (nodes.length % 6) * 24
		const p = screenToFlowPosition({ x: r.left + r.width / 2 + nudge, y: r.top + r.height / 2 + nudge })
		addNode(kind, { x: p.x - 104, y: p.y - 28 })
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
	<aside class="flex w-56 shrink-0 flex-col gap-2 border-e p-3">
		<p class="px-1 text-xs font-medium tracking-wide text-muted-foreground uppercase">Nodes</p>
		{#each NODE_KINDS as k (k.kind)}
			<button
				type="button"
				draggable="true"
				class="cursor-grab rounded-md border bg-card px-3 py-2 text-start transition-colors hover:border-primary/50 active:cursor-grabbing"
				ondragstart={(e) => {
					e.dataTransfer?.setData(DRAG_TYPE, k.kind)
					if (e.dataTransfer) e.dataTransfer.effectAllowed = 'move'
				}}
				onclick={() => addAtCenter(k.kind)}
			>
				<span class="block text-sm font-medium">{k.label}</span>
				<span class="block text-xs text-muted-foreground">{k.description}</span>
			</button>
		{/each}
		<p class="px-1 text-xs text-muted-foreground">Click or drag a node onto the canvas. Drag between the dots to connect. Select and press Delete to remove.</p>
		<div class="mt-auto flex flex-col gap-2">
			<Button variant="outline" size="sm" disabled={!hasSelection} onclick={deleteSelected}><Trash2Icon /> Delete selected</Button>
			<Button variant="outline" size="sm" disabled={nodes.length === 0} onclick={() => deleteElements({ nodes, edges })}>Clear canvas</Button>
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
		>
			<Background gap={24} />
			<Controls showLock={false} />
			<MiniMap pannable zoomable />
		</SvelteFlow>
	</div>
</div>
