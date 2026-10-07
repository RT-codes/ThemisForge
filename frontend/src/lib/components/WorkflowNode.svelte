<script lang="ts">
	import { Handle, Position, useSvelteFlow, type NodeProps } from '@xyflow/svelte'
	import XIcon from '@lucide/svelte/icons/x'
	import { MOUNT, defaultConfig, kindInfo, summary, type WorkflowNodeData } from '$lib/workflow'
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

	// While a test run plays: nodes still to come are dimmed, finished ones are almost fully there, the one playing is
	// fully there with a thicker, shining border. Outside a run none of this applies and everything fades back.
	const run = getContext<RunView | undefined>(RUN_VIEW)
	// (a Folder node is never a step of the run, so it keeps its normal look)
	const phase = $derived(run?.active && !info.mountOut ? (run.shown[id] ?? 'waiting') : null)
	const opacity = $derived(phase === 'waiting' ? 0.5 : phase === 'done' || phase === 'failed' ? 0.85 : 1)
</script>

<div
	style:opacity
	class="group relative flex w-52 items-center gap-3 rounded-lg border bg-card px-3 text-card-foreground shadow-sm transition-[color,background-color,border-color,box-shadow,opacity] duration-500 {info.mountOut ? 'border-dashed' : ''} {info.outputs ? 'py-4' : 'py-2.5'} {selected
		? 'border-primary ring-2 ring-primary/30'
		: 'hover:border-primary/50'}"
>
	<!-- the pulse of a node that finished, and the shining border of the one playing; each in its own clipped layer so the
	     handles and labels that stick out of the node are not cut off -->
	<span use:pulseWhen={run?.nodePulses[id] ?? 0} class="pointer-events-none absolute -inset-px overflow-hidden rounded-lg" aria-hidden="true"></span>
	<span class="run-ring" class:on={phase === 'playing'} aria-hidden="true"></span>
	{#if info.hasInput}
		<Handle type="target" position={Position.Left} class="workflow-handle" />
	{/if}
	{#if info.mountIn}
		<Handle type="target" id={MOUNT} position={Position.Bottom} class="workflow-handle mount-handle" title="Hand this agent a folder: drag from a Folder node" />
	{/if}
	{#if info.mountOut}
		<Handle type="source" id={MOUNT} position={Position.Top} class="workflow-handle mount-handle" title="Drag to an agent's folder point to give it this folder" />
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
	{#if info.outputs}
		{#each info.outputs as o, i (o.id)}
			{@const top = i === 0 ? '30%' : '70%'}
			<Handle type="source" id={o.id} position={Position.Right} class="workflow-handle" style="top: {top}" />
			<span class="pointer-events-none absolute left-full ms-3 -translate-y-1/2 text-xs font-semibold text-foreground/80" style="top: {top}">{o.label}</span>
		{/each}
	{:else if info.hasOutput}
		<Handle type="source" position={Position.Right} class="workflow-handle" />
	{/if}
</div>
