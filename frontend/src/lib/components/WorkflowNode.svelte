<script lang="ts">
	import { Handle, Position, useSvelteFlow, type NodeProps } from '@xyflow/svelte'
	import XIcon from '@lucide/svelte/icons/x'
	import { defaultConfig, kindInfo, summary, type WorkflowNodeData } from '$lib/workflow'
	import { nodeIcons } from '$lib/workflowIcons'

	let { id, data, selected }: NodeProps = $props()

	const { deleteElements } = useSvelteFlow()
	const d = $derived(data as WorkflowNodeData)
	const info = $derived(kindInfo(d.kind))
	const Icon = $derived(nodeIcons[d.kind])
	const line = $derived(summary(d.kind, d.config ?? defaultConfig(d.kind)))
</script>

<div
	class="group relative flex w-52 items-center gap-3 rounded-lg border bg-card px-3 text-card-foreground shadow-sm transition-colors {info.outputs ? 'py-4' : 'py-2.5'} {selected
		? 'border-primary ring-2 ring-primary/30'
		: 'hover:border-primary/50'}"
>
	{#if info.hasInput}
		<Handle type="target" position={Position.Left} class="workflow-handle" />
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
