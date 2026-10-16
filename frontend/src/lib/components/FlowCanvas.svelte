<script lang="ts">
	import { Background, Controls, MarkerType, MiniMap, Panel, SvelteFlow, useSvelteFlow, useViewport, type Connection, type Edge, type Node } from '@xyflow/svelte'
	import '@xyflow/svelte/dist/style.css'
	import * as AlertDialog from '$lib/components/ui/alert-dialog/index.js'
	import { Button } from '$lib/components/ui/button/index.js'
	import { Switch } from '$lib/components/ui/switch/index.js'
	import LoaderCircleIcon from '@lucide/svelte/icons/loader-circle'
	import ChevronRightIcon from '@lucide/svelte/icons/chevron-right'
	import PlayIcon from '@lucide/svelte/icons/play'
	import XIcon from '@lucide/svelte/icons/x'
	import Trash2Icon from '@lucide/svelte/icons/trash-2'
	import { api, type NodePreset } from '$lib/api'
	import { CROWDED_LINES, DRAG_TYPE, MOUNT, NODE_KINDS, PRESET_DRAG_TYPE, branchPoints, canConnect, crowdedLines, defaultConfig, fromGraph, isSavedNode, kindInfo, mountsFromGraph, nextNodeNumber, presetNodeData, toGraph, type Graph, type NodeKind, type WorkflowNodeData } from '$lib/workflow'
	import { onDestroy, onMount, setContext, untrack } from 'svelte'
	import { router } from '$lib/router.svelte'
	import { nodeIcons } from '$lib/workflowIcons'
	import { fade, slide } from 'svelte/transition'
	import NodeConfigPanel from './NodeConfigPanel.svelte'
	import SelectionBox from './SelectionBox.svelte'
	import WorkflowEdge from './WorkflowEdge.svelte'
	import WorkflowNode from './WorkflowNode.svelte'
	import { RUN_VIEW, RunView } from '$lib/workflowRun.svelte'

	// The canvas edits a graph. It does not know where the graph lives: the page decides what saving and testing mean,
	// which is how a brand new workflow can stay unsaved until something is actually changed.
	let {
		initialGraph,
		projectId,
		onsave,
		ontest,
		saveState = $bindable('saved'),
		draft = false,
		runId = null,
		onviewrun,
		onrunended,
	}: {
		projectId: number
		initialGraph: Graph
		onsave: (graph: Graph) => Promise<void>
		ontest: () => Promise<void>
		saveState?: 'saved' | 'saving' | 'error'
		draft?: boolean // a new workflow that has not been saved yet
		runId?: number | null // the test run to follow on the canvas
		onviewrun?: () => void // open the details of that run
		onrunended?: () => void // the run was played to its end: it is not followed again if the canvas comes back
	} = $props()

	const nodeTypes = { workflow: WorkflowNode }
	const edgeTypes = { workflow: WorkflowEdge }
	// the minimap tells node types apart by colour
	const KIND_COLORS: Record<string, string> = { start: '#34d399', trigger: '#fbbf24', task: '#60a5fa', agent: '#c084fc', condition: '#fb923c', approval: '#f472b6', end: '#f87171', volume: '#2dd4bf', split: '#38bdf8', merge: '#38bdf8' }
	const { screenToFlowPosition, deleteElements, fitView } = useSvelteFlow()

	// the dotted background and the snapping share one grid, so a snapped node sits exactly on the dots (Svelte Flow
	// snaps whenever it is given a snapGrid, so switching snapping off means giving it none)
	const GRID = 24

	// Small settings of the editor, remembered in this browser (a convenience: no storage just means the default)
	function readFlag(key: string, fallback: boolean) {
		try {
			const v = localStorage.getItem(key)
			return v === null ? fallback : v === '1'
		} catch {
			return fallback
		}
	}
	function writeFlag(key: string, on: boolean) {
		try {
			localStorage.setItem(key, on ? '1' : '0')
		} catch {
			// remembering is a convenience
		}
	}
	// Snapping a dragged node to the grid: on unless turned off
	const SNAP_KEY = 'themis.workflow.snap'
	let snapToGrid = $state(readFlag(SNAP_KEY, true))
	$effect(() => writeFlag(SNAP_KEY, snapToGrid))

	// Saved nodes: configured nodes of this project, kept on the server. Each is listed in the palette under the built-in
	// node of its kind, which unfolds to show them; what is unfolded is remembered in this browser.
	const presetOpenKey = (kind: NodeKind) => `themis.workflow.saved.${kind}`
	let presets = $state<NodePreset[]>([])
	let openKinds = $state<Record<string, boolean>>(Object.fromEntries(NODE_KINDS.map((k) => [k.kind, readFlag(presetOpenKey(k.kind), false)])))
	let presetError = $state('')
	const presetsOf = (kind: NodeKind) => presets.filter((p) => p.kind === kind)
	function setKindOpen(kind: NodeKind, on: boolean) {
		openKinds[kind] = on
		writeFlag(presetOpenKey(kind), on)
	}

	let nodes = $state.raw<Node[]>([])
	let edges = $state.raw<Edge[]>([])

	// a test run is played on the canvas itself (see workflowRun.svelte.ts); nodes and connections read it from context
	const runView = new RunView(() => edges)
	setContext(RUN_VIEW, runView)
	// lines that share a connection point with another one (made before the one-line rule): drawn as a warning
	const crowded = $derived(crowdedLines(edges))
	setContext(CROWDED_LINES, { has: (id: string) => crowded.has(id) })
	$effect(() => {
		if (runId) untrack(() => runView.follow(runId).then((ended) => ended && onrunended?.()))
		else untrack(() => runView.stop())
	})
	onDestroy(() => runView.stop())
	let counter = 0
	let wrapper: HTMLDivElement

	// ----- saving: shortly after every change, and never when nothing changed -----
	let loaded = $state(false)
	let lastSaved = ''
	let saveTimer: ReturnType<typeof setTimeout> | undefined
	const signature = $derived(JSON.stringify(toGraph(nodes, edges)))

	onMount(() => {
		const flow = fromGraph(initialGraph)
		nodes = flow.nodes
		edges = flow.edges
		counter = nextNodeNumber(initialGraph.nodes.map((n) => n.id))
		api.nodePresets(projectId).then((p) => (presets = p)).catch(() => (presetError = 'Could not load the saved nodes'))
		lastSaved = JSON.stringify(toGraph(nodes, edges)) // the starting point: only a difference from it counts as a change
		loaded = true
		// a link from a ticket ("Edit step") names a node in the address: it is selected, so its panel is open
		const wanted = new URLSearchParams(router.hash).get('node')
		if (wanted && nodes.some((n) => n.id === wanted)) {
			nodes = nodes.map((n) => ({ ...n, selected: n.id === wanted }))
			router.replace(router.path) // used up: reloading the page does not select it again
			setTimeout(() => fitView({ nodes: [{ id: wanted }], maxZoom: 1, padding: 1.5 }), 50)
		} else {
			setTimeout(() => fitView({ maxZoom: 1, padding: 0.08 }), 50)
		}
	})

	$effect(() => {
		if (!loaded || signature === lastSaved) return
		saveState = 'saving'
		clearTimeout(saveTimer)
		saveTimer = setTimeout(flush, 700)
	})

	/** save now, if there is anything to save */
	export async function flush() {
		clearTimeout(saveTimer)
		const sig = signature
		if (!loaded || sig === lastSaved) return
		try {
			await onsave(JSON.parse(sig))
			lastSaved = sig
			saveState = signature === sig ? 'saved' : 'saving'
		} catch {
			saveState = 'error'
		}
	}
	onDestroy(() => void flush())

	/** the graph as it is on the canvas right now */
	export const graph = (): Graph => toGraph(nodes, edges)

	// ----- testing -----
	let testing = $state(false)
	let testError = $state('')
	const hasStart = $derived(nodes.some((n) => ['start', 'trigger'].includes((n.data as WorkflowNodeData).kind)))

	async function test() {
		testError = ''
		testing = true
		try {
			await flush()
			await ontest()
		} catch (e) {
			testError = e instanceof Error ? e.message : 'Could not start the run'
		} finally {
			testing = false
		}
	}

	let clearOpen = $state(false)

	const hasSelection = $derived(nodes.some((n) => n.selected) || edges.some((e) => e.selected))
	// the node window configures the node when exactly one is selected
	const selectedNodes = $derived(nodes.filter((n) => n.selected))
	// not while a selection box is being dragged: a window popping up under the pointer would get in its way
	let selecting = $state(false)
	const active = $derived(!selecting && selectedNodes.length === 1 ? selectedNodes[0] : null)

	// ----- the node window -----
	// It floats over the canvas, so selecting a node never resizes or shifts the canvas. It opens beside the node (on the
	// side with room) and follows the node as it is dragged or the canvas is panned and zoomed. Dragging its title bar
	// pins it where it is left: it then stays put while other nodes are selected, until it is closed.
	const WIN_MAX_W = 640 // wide enough for the Instructions field to read comfortably
	const WIN_GAP = 18 // between the node and the window
	const WIN_EDGE = 12 // the window keeps this far from the canvas edge
	const viewport = useViewport()
	let canvasW = $state(0)
	let canvasH = $state(0)
	// the window gives way on a narrow canvas instead of overflowing it
	const winW = $derived(Math.min(WIN_MAX_W, Math.max(280, canvasW - WIN_EDGE * 2)))
	let winH = $state(0)
	let pin = $state<{ x: number; y: number } | null>(null)
	$effect(() => {
		if (!active) pin = null
	})
	const clamp = (v: number, lo: number, hi: number) => Math.max(lo, Math.min(v, Math.max(lo, hi)))
	const win = $derived.by(() => {
		if (!active) return null
		const maxX = canvasW - winW - WIN_EDGE
		const maxY = canvasH - winH - WIN_EDGE
		if (pin) return { x: clamp(pin.x, WIN_EDGE, maxX), y: clamp(pin.y, WIN_EDGE, maxY), side: null, tail: 0 }
		// the node on screen (nodes are about 208 x 56 until measured)
		const { x: vx, y: vy, zoom } = viewport.current
		const w = (active.measured?.width ?? 208) * zoom
		const h = (active.measured?.height ?? 56) * zoom
		const left = active.position.x * zoom + vx
		const top = active.position.y * zoom + vy
		const onRight = left + w + WIN_GAP + winW <= canvasW - WIN_EDGE
		const x = clamp(onRight ? left + w + WIN_GAP : left - winW - WIN_GAP, WIN_EDGE, maxX)
		const y = clamp(top - 8, WIN_EDGE, maxY)
		// the notch points at the middle of the node, kept inside the window's rounded corners
		return { x, y, side: onRight ? 'right' : 'left', tail: clamp(top + h / 2 - y, 22, winH - 22) }
	})
	function startWindowDrag(e: PointerEvent) {
		if (e.button !== 0 || !win || (e.target as HTMLElement).closest('button')) return
		const from = { x: win.x, y: win.y, px: e.clientX, py: e.clientY }
		const move = (m: PointerEvent) => (pin = { x: from.x + m.clientX - from.px, y: from.y + m.clientY - from.py })
		const stop = () => {
			window.removeEventListener('pointermove', move)
			window.removeEventListener('pointerup', stop)
			window.removeEventListener('pointercancel', stop)
		}
		window.addEventListener('pointermove', move)
		window.addEventListener('pointerup', stop)
		window.addEventListener('pointercancel', stop)
		e.preventDefault() // no text selection while dragging
	}

	function updateNode(id: string, patch: Partial<WorkflowNodeData>) {
		const next = nodes.map((n) => (n.id === id ? { ...n, data: { ...n.data, ...patch } } : n))
		nodes = next
		// fewer branches on a Splitter or Merger take their connection points away, and the lines that were on them
		const changed = next.find((n) => n.id === id)?.data as WorkflowNodeData | undefined
		if (changed && kindInfo(changed.kind).branching && patch.config) {
			const kept = new Set(branchPoints(changed.kind, changed.config).map((p) => p.id))
			const gone = (e: Edge) => (changed.kind === 'split' ? e.source === id && !kept.has(e.sourceHandle ?? '') : e.target === id && !kept.has(e.targetHandle ?? ''))
			if (edges.some(gone)) edges = edges.filter((e) => !gone(e))
		}
	}
	const deselectAll = () => (nodes = nodes.map((n) => ({ ...n, selected: false })))

	// the star in a node's panel: lit while the node is exactly a saved one, and pressing it then takes that one out
	const activeSaved = $derived(active ? presets.find((p) => isSavedNode(p, active.data as WorkflowNodeData)) : undefined)
	async function toggleSaved() {
		if (!active) return
		presetError = ''
		try {
			if (activeSaved) {
				const gone = activeSaved.id
				await api.deleteNodePreset(gone)
				presets = presets.filter((p) => p.id !== gone)
			} else {
				const d = active.data as WorkflowNodeData
				presets = [...presets, await api.createNodePreset(projectId, { kind: d.kind, label: d.label.trim(), config: d.config })]
				setKindOpen(d.kind, true) // so the new one is seen
			}
		} catch (e) {
			presetError = e instanceof Error ? e.message : 'Could not save the node'
		}
	}
	async function removeSaved(p: NodePreset) {
		presetError = ''
		try {
			await api.deleteNodePreset(p.id)
			presets = presets.filter((x) => x.id !== p.id)
		} catch (e) {
			presetError = e instanceof Error ? e.message : 'Could not remove the saved node'
		}
	}

	// a node of a kind starts from the kind's own name and defaults; a saved node starts from what was saved
	function addNode(kind: NodeKind, position: { x: number; y: number }, saved?: NodePreset) {
		const data: WorkflowNodeData = saved ? presetNodeData(saved) : { kind, label: kindInfo(kind).label, config: defaultConfig(kind) }
		nodes = [...nodes.map((n) => ({ ...n, selected: false })), { id: `n${++counter}`, type: 'workflow', position, selected: true, data }]
	}

	// step down until the spot is not on top of another node (nodes are about 208 x 56)
	function freeSpot(at: { x: number; y: number }) {
		const taken = (y: number) => nodes.some((n) => Math.abs(n.position.x - at.x) < 232 && Math.abs(n.position.y - y) < 96)
		let y = at.y
		while (taken(y)) y += 120
		return { x: at.x, y }
	}

	// a click on the palette drops the node in the middle of the canvas, clear of any node already there
	function addAtCenter(kind: NodeKind, saved?: NodePreset) {
		// below the selected (or latest) node, so a flow reads top to bottom; the canvas centre when it is empty
		const anchor = active ?? nodes.at(-1)
		let at: { x: number; y: number }
		if (anchor) at = { x: anchor.position.x, y: anchor.position.y + 120 }
		else {
			const r = wrapper.getBoundingClientRect()
			const p = screenToFlowPosition({ x: r.left + r.width / 2, y: r.top + r.height / 2 })
			at = { x: p.x - 104, y: p.y - 28 }
		}
		addNode(kind, freeSpot(at), saved)
		// bring the whole graph into view, once the new node has been measured
		setTimeout(() => fitView({ maxZoom: 1, padding: 0.2, duration: 350 }), 60)
	}

	function onDrop(e: DragEvent) {
		const saved = presets.find((p) => String(p.id) === e.dataTransfer?.getData(PRESET_DRAG_TYPE))
		const kind = saved?.kind ?? (e.dataTransfer?.getData(DRAG_TYPE) as NodeKind | undefined)
		if (!kind) return
		e.preventDefault()
		const p = screenToFlowPosition({ x: e.clientX, y: e.clientY })
		addNode(kind, { x: p.x - 104, y: p.y - 28 }, saved)
	}

	function onDragOver(e: DragEvent) {
		if (!e.dataTransfer?.types.some((t) => t === DRAG_TYPE || t === PRESET_DRAG_TYPE)) return
		e.preventDefault()
		e.dataTransfer.dropEffect = 'move'
	}

	// a node cannot connect to itself; a Folder only joins an agent's folder point, and nothing else touches a Folder
	const kindOf = (id: string) => (nodes.find((n) => n.id === id)?.data as WorkflowNodeData | undefined)?.kind
	const isValidConnection = (c: Connection | Edge) => c.source !== c.target && canConnect(kindOf(c.source), kindOf(c.target), c.sourceHandle, c.targetHandle)

	// A connection point holds one line, so what happens next is never a guess: to run two things after a step, add a
	// Splitter; to wait for two, a Merger. A new line takes the place of the one that was there, as in most node editors.
	// (A folder may feed several agents, and an agent take several folders: those lines are not steps.)
	function beforeConnect(c: Connection) {
		if (c.sourceHandle === MOUNT || c.targetHandle === MOUNT) return c
		const same = (e: Edge) =>
			e.sourceHandle !== MOUNT &&
			((e.source === c.source && (e.sourceHandle ?? null) === (c.sourceHandle ?? null)) || (e.target === c.target && (e.targetHandle ?? null) === (c.targetHandle ?? null)))
		if (edges.some(same)) edges = edges.filter((e) => !same(e))
		return c
	}

	// a line that hands a folder over looks different from a step: dashed, teal, no arrow, not animated
	const MOUNT_STYLE = 'stroke: #2dd4bf; stroke-width: 2; stroke-dasharray: 6 4'
	$effect(() => {
		const stale = edges.some((e) => e.sourceHandle === MOUNT && (e.style !== MOUNT_STYLE || e.animated || e.markerEnd))
		if (stale) untrack(() => (edges = edges.map((e) => (e.sourceHandle === MOUNT ? { ...e, style: MOUNT_STYLE, animated: false, markerEnd: undefined } : e))))
	})

	// Escape lets go of the selection (unless a field is being typed in)
	function onkeydown(e: KeyboardEvent) {
		if (e.key !== 'Escape' || e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return
		if (nodes.some((n) => n.selected)) nodes = nodes.map((n) => (n.selected ? { ...n, selected: false } : n))
		if (edges.some((e) => e.selected)) edges = edges.map((e) => (e.selected ? { ...e, selected: false } : e))
	}

	// Safety net: Svelte Flow keeps its own idea of which of Shift and Ctrl is held, from key-down and key-up events. If a
	// key-up is ever missed (the window lost focus, a shortcut of the system took it), it believes the key is still down
	// and every click starts a selection box instead of moving a node. A click that says no modifier is held settles it.
	// Only then: Shift, Ctrl and Meta share one "adding to the selection" flag in Svelte Flow, so letting one go while
	// another is really held would switch off the one in use.
	function settleKeys(e: PointerEvent) {
		if (e.shiftKey || e.ctrlKey || e.metaKey) return
		for (const key of ['Shift', 'Control', 'Meta']) window.dispatchEvent(new KeyboardEvent('keyup', { key }))
	}

	const deleteSelectedNodes = () => deleteElements({ nodes: selectedNodes })
	const deleteSelected = () => deleteElements({ nodes: nodes.filter((n) => n.selected), edges: edges.filter((e) => e.selected) })
</script>

<svelte:window {onkeydown} onpointerup={() => (selecting = false)} onblur={() => (selecting = false)} />

<div class="flex min-h-0 flex-1">
	<aside class="flex w-52 shrink-0 flex-col gap-1 border-e p-2">
		<Button class="h-8 w-full" disabled={!loaded || testing || runView.active || !hasStart} onclick={test}>
			{#if testing || runView.active}<LoaderCircleIcon class="animate-spin" />{:else}<PlayIcon />{/if} {runView.active ? 'Running' : 'Test run'}
		</Button>
		{#if runId && onviewrun}
			<Button variant="ghost" size="sm" class="h-7 justify-start px-1.5 text-xs text-muted-foreground" onclick={onviewrun}>Run details</Button>
		{/if}
		{#if testError}
			<p class="px-1 text-xs leading-snug text-destructive" role="alert">{testError}</p>
		{:else if !hasStart}
			<p class="px-1 text-xs leading-snug text-muted-foreground">Add a Start node to test.</p>
		{:else}
			<p class={`px-1 text-xs leading-snug transition-colors ${saveState === 'error' ? 'text-destructive' : 'text-muted-foreground'}`}>
				{saveState === 'saving' ? 'Saving...' : saveState === 'error' ? 'Could not save' : draft ? 'Saved when you change something' : 'All changes saved'}
			</p>
		{/if}
		<div class="my-1.5 border-t"></div>
		<p class="px-1.5 pb-0.5 text-xs font-medium tracking-wide text-muted-foreground uppercase">Nodes</p>
		{#each NODE_KINDS as k (k.kind)}
			{@const Icon = nodeIcons[k.kind]}
			{@const saved = presetsOf(k.kind)}
			{@const open = saved.length > 0 && openKinds[k.kind]}
			<div class="relative">
				<button
					type="button"
					draggable="true"
					title={k.description}
					class="flex w-full cursor-grab items-center gap-2 rounded-md border bg-card px-2 py-1.5 text-start text-sm transition-colors hover:border-primary/50 hover:bg-accent/40 active:cursor-grabbing {saved.length ? 'pe-11' : ''}"
					ondragstart={(e) => {
						e.dataTransfer?.setData(DRAG_TYPE, k.kind)
						if (e.dataTransfer) e.dataTransfer.effectAllowed = 'move'
					}}
					onclick={() => addAtCenter(k.kind)}
				>
					<span class="flex size-5 shrink-0 items-center justify-center rounded bg-primary/15 text-primary"><Icon class="size-3" /></span>
					<span class="truncate">{k.label}</span>
				</button>
				<!-- only a kind with saved nodes can be unfolded: how many there are, and a chevron -->
				{#if saved.length}
					<button
						type="button"
						class="absolute end-1 top-1/2 flex h-6 -translate-y-1/2 items-center gap-0.5 rounded px-1 text-xs text-muted-foreground transition-colors hover:text-foreground"
						aria-expanded={open}
						aria-label="{open ? 'Hide' : 'Show'} the saved {k.label} nodes"
						onclick={() => setKindOpen(k.kind, !open)}
					>
						<span class="tabular-nums">{saved.length}</span>
						<ChevronRightIcon class="size-3 transition-transform {open ? 'rotate-90' : ''}" />
					</button>
				{/if}
			</div>
			{#if open}
				<div transition:slide={{ duration: 160 }} class="ms-3 flex flex-col gap-1 border-s ps-2">
					{#each saved as p (p.id)}
						{@const name = p.label || k.label}
						<div class="group/saved relative">
							<button
								type="button"
								draggable="true"
								title="{k.label} node: {name}"
								class="flex w-full cursor-grab items-center gap-2 rounded-md border bg-card py-1 ps-2 pe-6 text-start text-xs transition-colors hover:border-green-300/50 hover:bg-accent/40 active:cursor-grabbing"
								ondragstart={(e) => {
									e.dataTransfer?.setData(PRESET_DRAG_TYPE, String(p.id))
									if (e.dataTransfer) e.dataTransfer.effectAllowed = 'move'
								}}
								onclick={() => addAtCenter(p.kind, p)}
							>
								<span class="flex size-4 shrink-0 items-center justify-center rounded bg-green-300/15 text-green-300"><Icon class="size-2.5" /></span>
								<span class="truncate">{name}</span>
							</button>
							<button
								type="button"
								class="absolute end-1 top-1/2 hidden size-4 -translate-y-1/2 items-center justify-center rounded text-muted-foreground hover:text-destructive group-hover/saved:flex focus-visible:flex"
								aria-label="Remove {name} from the saved nodes"
								onclick={() => removeSaved(p)}
							>
								<XIcon class="size-3" />
							</button>
						</div>
					{/each}
				</div>
			{/if}
		{/each}
		{#if presetError}<p class="px-1.5 text-xs leading-snug text-destructive" role="alert">{presetError}</p>{/if}
		<p class="px-1.5 pt-1 text-xs leading-snug text-muted-foreground">Click or drag onto the canvas. Star a node in its window to keep it under its kind. Drag between the dots to connect. A Folder joins an agent at the teal squares. The Test run starts at every Start node.</p>
		<div class="mt-auto flex flex-col gap-1.5">
			<Button variant="outline" size="sm" class="h-7 text-xs" disabled={!hasSelection} onclick={deleteSelected}><Trash2Icon class="size-3.5" /> Delete selected</Button>
			<Button variant="outline" size="sm" class="h-7 text-xs text-destructive hover:text-destructive" disabled={nodes.length === 0} onclick={() => (clearOpen = true)}>Clear canvas</Button>
		</div>
	</aside>

	<div class="relative min-w-0 flex-1" bind:this={wrapper} bind:clientWidth={canvasW} bind:clientHeight={canvasH} role="presentation" ondrop={onDrop} ondragover={onDragOver} onpointerdowncapture={settleKeys}>
		<SvelteFlow
			bind:nodes
			bind:edges
			{nodeTypes}
			{edgeTypes}
			{isValidConnection}
			onbeforeconnect={beforeConnect}
			colorMode="dark"
			deleteKey={['Backspace', 'Delete']}
			selectionKey="Shift"
			multiSelectionKey={['Shift', 'Control', 'Meta']}
			onselectionstart={() => (selecting = true)}
			onselectionend={() => (selecting = false)}
			defaultEdgeOptions={{ type: 'workflow', animated: true, style: 'stroke: var(--primary)', markerEnd: { type: MarkerType.ArrowClosed } }}
			fitView
			fitViewOptions={{ maxZoom: 1, padding: 0.12 }}
			minZoom={0.2}
			snapGrid={snapToGrid ? [GRID, GRID] : undefined}
			proOptions={{ hideAttribution: true }}
		>
			<Background gap={GRID} />
			<!-- editor options floating over the canvas: one option per row, stacked in a column. Add new ones as more rows. -->
			<Panel position="top-right">
				<div class="flex flex-col gap-2 rounded-lg border bg-card/90 p-2.5 text-xs shadow-sm backdrop-blur">
					<label class="flex cursor-pointer items-center justify-between gap-3">
						Snap to grid
						<Switch size="sm" bind:checked={snapToGrid} />
					</label>
				</div>
			</Panel>
			<Controls showLock={false} />
			<SelectionBox selected={selectedNodes} ondelete={deleteSelectedNodes} onclear={deselectAll} />
			<MiniMap pannable zoomable class="workflow-minimap max-xl:hidden" nodeColor={(n) => KIND_COLORS[(n.data as WorkflowNodeData).kind] ?? '#888'} nodeStrokeWidth={0} />
		</SvelteFlow>

		{#if active && win}
			<!-- not inside the flow, so a click or a key in it is not the canvas's -->
			<section
				aria-label="{kindInfo((active.data as WorkflowNodeData).kind).label} node settings"
				transition:fade={{ duration: 120 }}
				class="absolute z-10 flex max-h-[calc(100%-1.5rem)] flex-col rounded-xl border bg-card text-card-foreground shadow-float [--text-base:0.8125rem] [--text-sm:0.75rem] [--text-xs:0.6875rem]"
				style:width="{winW}px"
				style:left="{win.x}px"
				style:top="{win.y}px"
				bind:clientHeight={winH}
			>
				{#if win.side}
					<!-- the notch that ties the window to its node -->
					<span
						class="pointer-events-none absolute size-3 -translate-y-1/2 rotate-45 bg-card {win.side === 'right' ? '-left-[7px] border-b border-l' : '-right-[7px] border-t border-r'}"
						style:top="{win.tail}px"
						aria-hidden="true"
					></span>
				{/if}
				{#key active.id}
					<NodeConfigPanel
						{projectId}
						id={active.id}
						data={active.data as WorkflowNodeData}
						attached={mountsFromGraph(nodes, edges, active.id)}
						saved={!!activeSaved}
						onsave={toggleSaved}
						onchange={(patch) => updateNode(active.id, patch)}
						onclose={deselectAll}
						ondelete={() => deleteElements({ nodes: [{ id: active.id }] })}
						onheaddown={startWindowDrag}
					/>
				{/key}
			</section>
		{/if}
	</div>
</div>

<AlertDialog.Root bind:open={clearOpen}>
	<AlertDialog.Content>
		<AlertDialog.Header>
			<AlertDialog.Title>Clear the canvas?</AlertDialog.Title>
			<AlertDialog.Description>Every node and connection in this workflow is removed. Changes are saved as you make them, so this cannot be undone.</AlertDialog.Description>
		</AlertDialog.Header>
		<AlertDialog.Footer>
			<AlertDialog.Cancel>Keep them</AlertDialog.Cancel>
			<AlertDialog.Action
				onclick={() => {
					clearOpen = false
					deleteElements({ nodes, edges })
				}}>Clear canvas</AlertDialog.Action
			>
		</AlertDialog.Footer>
	</AlertDialog.Content>
</AlertDialog.Root>
