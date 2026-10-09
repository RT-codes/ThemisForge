<script lang="ts">
	import type { Task, Workspace } from '$lib/api'
	import { destinationLabel, findBoard, lineage } from '$lib/boards'
	import { Button } from '$lib/components/ui/button/index.js'
	import ArrowRightIcon from '@lucide/svelte/icons/arrow-right'
	import GitBranchPlusIcon from '@lucide/svelte/icons/git-branch-plus'

	// Where a task lives and how it connects to others: send it to another board, create a follow-up there, and see which
	// task it follows and which tasks followed it. Hidden while a project has a single board with no links to show.
	let {
		task,
		tasks,
		workspaces,
		busy,
		onsend,
		onfollowup,
		onopen,
	}: {
		task: Task
		tasks: Task[]
		workspaces: Workspace[]
		busy: boolean
		onsend: () => void
		onfollowup: () => void
		onopen: (task: Task) => void
	} = $props()

	const here = $derived(findBoard(workspaces, task.board_id))
	const links = $derived(lineage(tasks, task))
	const boardOf = (t: Task) => findBoard(workspaces, t.board_id)
</script>

<div class="mx-4 mb-4 grid gap-2 rounded-lg border bg-card/40 p-3 text-sm">
	<div class="flex flex-wrap items-center gap-2">
		<div class="min-w-0 flex-1">
			<p class="text-xs text-muted-foreground">On board</p>
			<p class="truncate font-medium">{here ? destinationLabel(workspaces, here) : '-'}</p>
		</div>
		<Button size="sm" variant="outline" disabled={busy || task.status === 'running' || workspaces.flatMap((w) => w.boards).length < 2} title={task.status === 'running' ? 'Cancel the run before sending it' : undefined} onclick={onsend}>
			<ArrowRightIcon /> Send to...
		</Button>
		<Button size="sm" variant="outline" disabled={busy} onclick={onfollowup}><GitBranchPlusIcon /> Follow-up...</Button>
	</div>
	{#if links.origin || links.followUps.length}
		<ul class="grid gap-1 border-t pt-2 text-xs">
			{#if links.origin}
				<li class="flex items-baseline gap-1.5">
					<span class="text-muted-foreground">Follows</span>
					<button type="button" class="truncate font-medium text-primary hover:underline" onclick={() => onopen(links.origin!)}>{links.origin.title}</button>
					{#if boardOf(links.origin)}<span class="shrink-0 text-muted-foreground">on {destinationLabel(workspaces, boardOf(links.origin)!)}</span>{/if}
				</li>
			{/if}
			{#each links.followUps as f (f.id)}
				<li class="flex items-baseline gap-1.5">
					<span class="text-muted-foreground">Followed by</span>
					<button type="button" class="truncate font-medium text-primary hover:underline" onclick={() => onopen(f)}>{f.title}</button>
					{#if boardOf(f)}<span class="shrink-0 text-muted-foreground">on {destinationLabel(workspaces, boardOf(f)!)}</span>{/if}
				</li>
			{/each}
		</ul>
	{/if}
</div>
