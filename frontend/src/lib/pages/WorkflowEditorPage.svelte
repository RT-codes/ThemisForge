<script lang="ts">
	import { SvelteFlowProvider } from '@xyflow/svelte'
	import FlowCanvas from '$lib/components/FlowCanvas.svelte'
	import WorkflowRuns from '$lib/components/WorkflowRuns.svelte'
	import * as Tabs from '$lib/components/ui/tabs/index.js'
	import { projects } from '$lib/projects.svelte'

	let { id }: { id: number } = $props()

	const project = $derived(projects.get(id))
	let tab = $state<'editor' | 'runs'>('editor')
	let selectedRun = $state<number | null>(null)

	function showRun(runId: number) {
		selectedRun = runId
		tab = 'runs'
	}
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
		<div class="flex items-center gap-4 border-b px-6 py-3">
			<div class="min-w-0">
				<h2 class="text-lg font-semibold tracking-tight">Workflow editor</h2>
				<p class="truncate text-sm text-muted-foreground">{project.name}</p>
			</div>
			<Tabs.Root bind:value={tab} class="ms-auto">
				<Tabs.List>
					<Tabs.Trigger value="editor">Editor</Tabs.Trigger>
					<Tabs.Trigger value="runs">Runs</Tabs.Trigger>
				</Tabs.List>
			</Tabs.Root>
		</div>
		{#if tab === 'editor'}
			<SvelteFlowProvider>
				<FlowCanvas projectId={id} onrun={showRun} />
			</SvelteFlowProvider>
		{:else}
			<WorkflowRuns projectId={id} bind:selected={selectedRun} />
		{/if}
	</div>
{/if}
