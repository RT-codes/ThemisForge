<script lang="ts">
	import { Background, Controls, Position, SvelteFlow, type Edge, type Node } from '@xyflow/svelte'
	import '@xyflow/svelte/dist/style.css'

	const horizontal = { sourcePosition: Position.Right, targetPosition: Position.Left }

	let nodes = $state.raw<Node[]>([
		{ id: '1', type: 'input', position: { x: 0, y: 0 }, data: { label: 'Idea' }, ...horizontal },
		{ id: '2', position: { x: 240, y: 0 }, data: { label: 'Forge' }, ...horizontal },
		{ id: '3', type: 'output', position: { x: 480, y: 0 }, data: { label: 'Ship' }, ...horizontal },
	])
	let edges = $state.raw<Edge[]>([
		{ id: 'e1-2', source: '1', target: '2', animated: true, style: 'stroke: var(--primary)' },
		{ id: 'e2-3', source: '2', target: '3', animated: true, style: 'stroke: var(--primary)' },
	])
</script>

<SvelteFlow bind:nodes bind:edges colorMode="dark" fitView>
	<Background gap={24} />
	<Controls showLock={false} />
</SvelteFlow>
