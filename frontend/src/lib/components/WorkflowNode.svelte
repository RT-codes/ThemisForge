<script lang="ts">
	import { Handle, Position, useSvelteFlow, useUpdateNodeInternals, type NodeProps } from '@xyflow/svelte'
	import XIcon from '@lucide/svelte/icons/x'
	import { MOUNT, branchPoints, defaultConfig, kindInfo, summary, type WorkflowNodeData } from '$lib/workflow'
	import { nodeIcons } from '$lib/workflowIcons'
	import { pulseWhen } from '$lib/pulse'
	import { RUN_VIEW, type RunView } from '$lib/workflowRun.svelte'
	import { getContext } from 'svelte'

	let { id, data, selected }: NodeProps = $props()

	const { deleteElements } = useSvelteFlow()
	const d = $derived(data as WorkflowNodeData)
	const info = $derived(kindInfo(d.kind))
	const Icon = $derived(nodeIcons[d.kind])
	const line = $derived(summary(d.kind, d.config ?? defaultConfig(d.kind)))
	// Where lines come in and go out. A Merger takes its branches in along the top, a Splitter sends them out along the
	// bottom, a Condition answers yes or no; the points are spread evenly and named by what the person called them.
	const points = $derived(branchPoints(d.kind, d.config ?? defaultConfig(d.kind)))
	const outs = $derived(info.branching === 'out' ? points : (info.outputs ?? []))
	const spread = (i: number, of: number) => `${((i + 1) / (of + 1)) * 100}%`
	// Svelte Flow measures where the connection points are; when their number or place changes it has to be told
	const updateNodeInternals = useUpdateNodeInternals()
	$effect(() => {
		void outs.length
		void points.length
		updateNodeInternals(id)
	})

	// While a test run plays: nodes still to come are dimmed, finished ones are almost fully there, the one playing is
	// fully there with a thicker, shining border. Outside a run none of this applies and everything fades back.
	const run = getContext<RunView | undefined>(RUN_VIEW)
	// (a Folder node is never a step of the run, so it keeps its normal look)
	const phase = $derived(run?.active && !info.mountOut ? (run.shown[id] ?? 'waiting') : null)
	const opacity = $derived(phase === 'waiting' ? 0.5 : phase === 'done' || phase === 'failed' ? 0.85 : 1)
</script>

<div
	style:opacity
	class="group relative flex {info.branching ? 'w-64' : 'w-52'} items-center gap-3 rounded-lg border bg-card px-3 text-card-foreground shadow-sm transition-[color,background-color,border-color,box-shadow,opacity] duration-500 {info.mountOut ? 'border-dashed' : ''} py-2.5 {selected
		? 'border-primary ring-2 ring-primary/30'
		: 'hover:border-primary/50'}"
>
	<!-- the pulse of a node that finished, and the shining border of the one playing; each in its own clipped layer so the
	     handles and labels that stick out of the node are not cut off -->
	<span use:pulseWhen={run?.nodePulses[id] ?? 0} class="pointer-events-none absolute -inset-px overflow-hidden rounded-lg" aria-hidden="true"></span>
	<span class="run-ring" class:on={phase === 'playing' || phase === 'parked'} class:parked={phase === 'parked'} aria-hidden="true"></span>
	{#if info.branching === 'in'}
		{#each points as p, i (p.id)}
			<Handle type="target" id={p.id} position={Position.Top} class="workflow-handle" style="left: {spread(i, points.length)}" />
			<span class="pointer-events-none absolute bottom-full mb-2.5 max-w-12 -translate-x-1/2 truncate text-[11px] font-semibold text-foreground/80" style="left: {spread(i, points.length)}">{p.label}</span>
		{/each}
	{:else if info.hasInput}
		<Handle type="target" position={Position.Top} class="workflow-handle" />
	{/if}
	<!-- the folder points sit on the sides: the top and bottom belong to the flow of steps, which reads downwards -->
	{#if info.mountIn}
		<Handle type="target" id={MOUNT} position={Position.Left} class="workflow-handle mount-handle" title="Hand this agent a folder: drag from a Folder node" />
	{/if}
	{#if info.mountOut}
		<Handle type="source" id={MOUNT} position={Position.Right} class="workflow-handle mount-handle" title="Drag to an agent's folder point to give it this folder" />
	{/if}
	<div class="flex size-8 shrink-0 items-center justify-center rounded-md bg-primary/15 text-primary">
		<Icon class="size-4" />
	</div>
	<div class="min-w-0 flex-1">
		<p class="truncate text-sm font-medium">{d.label}</p>
		<p class="truncate text-xs text-muted-foreground" title={line}>{line}</p>
	</div>
	<button
		type="button"
		class="nodrag absolute -top-2 -right-2 hidden size-5 items-center justify-center rounded-full border bg-card text-muted-foreground hover:text-destructive group-hover:flex"
		aria-label="Delete node"
		onclick={() => deleteElements({ nodes: [{ id }] })}
	>
		<XIcon class="size-3" />
	</button>
	{#if outs.length}
		{#each outs as o, i (o.id)}
			<Handle type="source" id={o.id} position={Position.Bottom} class="workflow-handle" style="left: {spread(i, outs.length)}" />
			<span class="pointer-events-none absolute top-full mt-2.5 max-w-14 -translate-x-1/2 truncate text-xs font-semibold text-foreground/80" style="left: {spread(i, outs.length)}">{o.label}</span>
		{/each}
	{:else if info.hasOutput}
		<Handle type="source" position={Position.Bottom} class="workflow-handle" />
	{/if}
</div>
