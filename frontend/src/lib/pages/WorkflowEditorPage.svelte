<script lang="ts">
	import { SvelteFlowProvider } from '@xyflow/svelte'
	import FlowCanvas from '$lib/components/FlowCanvas.svelte'
	import { projects } from '$lib/projects.svelte'

	let { id }: { id: number } = $props()

	const project = $derived(projects.get(id))
</script>

{#if !projects.loaded}
	<div class="min-h-0 flex-1"></div>
{:else if !project}
	<div class="m-auto text-center">
		<p class="text-lg font-medium">Project not found</p>
		<a href="/" class="mt-2 inline-block text-sm text-primary hover:underline">Back home</a>
	</div>
{:else}
	<div class="flex min-h-0 flex-1 flex-col">
		<div class="border-b px-6 py-3">
			<h2 class="text-lg font-semibold tracking-tight">Workflow editor</h2>
			<p class="text-sm text-muted-foreground">{project.name}</p>
		</div>
		<SvelteFlowProvider>
			<FlowCanvas />
		</SvelteFlowProvider>
	</div>
{/if}
