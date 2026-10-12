<script lang="ts">
	import { Button } from '$lib/components/ui/button/index.js'
	import type { ProjectDesk } from '$lib/projectDesk.svelte'
	import { cn } from '$lib/utils'
	import WorkflowIcon from '@lucide/svelte/icons/workflow'

	// Workflow steps are tasks an Agent node makes to run its step. They are kept off the boards; this brings them back,
	// for looking at what a workflow did (or at one that is stuck). Small on purpose: it is rarely wanted.
	let { desk }: { desk: ProjectDesk } = $props()
	const label = $derived(desk.showSteps ? 'Hide workflow steps' : 'Show workflow steps')
</script>

<Button
	variant="ghost"
	size="icon-sm"
	class={cn('text-muted-foreground', desk.showSteps && 'bg-primary/15 text-primary hover:bg-primary/20 hover:text-primary')}
	aria-label={label}
	aria-pressed={desk.showSteps}
	title="{label}: the tasks that workflow Agent nodes make to run their steps"
	onclick={() => desk.setShowSteps(!desk.showSteps)}
><WorkflowIcon /></Button>
