<script lang="ts">
	import { Handle, Position, useSvelteFlow, type NodeProps } from '@xyflow/svelte'
	import BotIcon from '@lucide/svelte/icons/bot'
	import FlagIcon from '@lucide/svelte/icons/flag'
	import GitBranchIcon from '@lucide/svelte/icons/git-branch'
	import ListChecksIcon from '@lucide/svelte/icons/list-checks'
	import XIcon from '@lucide/svelte/icons/x'
	import ZapIcon from '@lucide/svelte/icons/zap'
	import { kindInfo, type NodeKind, type WorkflowNodeData } from '$lib/workflow'

	let { id, data, selected }: NodeProps = $props()

	const { deleteElements } = useSvelteFlow()
	const d = $derived(data as WorkflowNodeData)
	const info = $derived(kindInfo(d.kind))
	const icons = { trigger: ZapIcon, task: ListChecksIcon, agent: BotIcon, condition: GitBranchIcon, end: FlagIcon }
	const Icon = $derived(icons[d.kind as NodeKind])
</script>

<div
	class="group relative flex w-52 items-center gap-3 rounded-lg border bg-card px-3 py-2.5 text-card-foreground shadow-sm transition-colors {selected
		? 'border-primary ring-2 ring-primary/30'
		: 'hover:border-primary/50'}"
>
	{#if info.hasInput}
		<Handle type="target" position={Position.Left} />
	{/if}
	<div class="flex size-8 shrink-0 items-center justify-center rounded-md bg-primary/15 text-primary">
		<Icon class="size-4" />
	</div>
	<div class="min-w-0 flex-1">
		<p class="truncate text-sm font-medium">{d.label}</p>
		<p class="truncate text-xs text-muted-foreground">{info.label}</p>
	</div>
	<button
		type="button"
		class="nodrag absolute -top-2 -right-2 hidden size-5 items-center justify-center rounded-full border bg-card text-muted-foreground hover:text-destructive group-hover:flex"
		aria-label="Delete node"
		onclick={() => deleteElements({ nodes: [{ id }] })}
	>
		<XIcon class="size-3" />
	</button>
	{#if info.hasOutput}
		<Handle type="source" position={Position.Right} />
	{/if}
</div>
