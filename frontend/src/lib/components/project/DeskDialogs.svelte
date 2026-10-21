<script lang="ts">
	import type { Board, Workspace } from '$lib/api/projects'
	import * as AlertDialog from '$lib/components/ui/alert-dialog/index.js'
	import type { ProjectDesk } from '$lib/projectDesk.svelte'
	import { onClickAway } from '$lib/clickAway'
	import { onMount } from 'svelte'
	import TaskSheet from './TaskSheet.svelte'

	// The task panel and the "delete this task?" question that every page working on tasks shows.
	let { desk, workspaces }: { desk: ProjectDesk; workspaces: Workspace[] } = $props()

	// Clicking on empty space lets go of the task open in the panel (a new task is a draft and stays). Unsaved changes
	// are asked about first, as for anything else that would take the panel away.
	onMount(() =>
		onClickAway(() => {
			if (desk.sheetOpen && desk.sheetTaskId !== null) desk.closeTask()
		})
	)

	const boards = $derived(workspaces.flatMap((w) => w.boards))
	// an open task is on the board it is on now (it may just have been sent elsewhere); a new task goes to the board asked for
	const sheetBoard = $derived(boards.find((b) => b.id === (desk.sheetTask?.board_id ?? desk.sheetBoardId)) ?? boards[0] ?? null)
</script>

{#if desk.project && sheetBoard}
	<TaskSheet
		bind:open={desk.sheetOpen}
		bind:dirty={desk.sheetDirty}
		bind:save={desk.saveSheet}
		projectId={desk.projectId}
		task={desk.sheetTask}
		board={sheetBoard}
		tasks={desk.tasks}
		{workspaces}
		defaultStatus={desk.sheetStatus}
		initialTab={desk.sheetTab}
		defs={desk.project.properties}
		timezone={desk.system?.timezone ?? 'UTC'}
		now={desk.now}
		revision={desk.revision}
		onchange={() => desk.reload()}
		ondelete={(task) => desk.askDelete(task)}
		onduplicate={(task) => desk.duplicateTask(task)}
		onopen={(task) => desk.openTask(task)}
		onopenworkflow={(id, nodeId) => desk.openWorkflow(id, nodeId)}
	/>
{/if}
<AlertDialog.Root open={desk.tasksToDelete.length > 0} onOpenChange={(o) => !o && (desk.tasksToDelete = [])}>
	<AlertDialog.Content>
		<AlertDialog.Header>
			<AlertDialog.Title>{desk.tasksToDelete.length > 1 ? `Delete ${desk.tasksToDelete.length} tasks?` : 'Delete this task?'}</AlertDialog.Title>
			<AlertDialog.Description>
				{#if desk.tasksToDelete.length > 1}
					These tasks and their attempt history will be removed. The project's History keeps a note of each one that was deleted.
				{:else}
					"{desk.tasksToDelete[0]?.title}" and its attempt history will be removed. The project's History keeps a note that it was deleted.
				{/if}
			</AlertDialog.Description>
		</AlertDialog.Header>
		{#if desk.tasksToDelete.length > 1}
			<ul class="slim-scrollbar max-h-40 list-disc overflow-y-auto ps-5 text-sm text-muted-foreground">
				{#each desk.tasksToDelete as t (t.id)}<li class="truncate">{t.title}</li>{/each}
			</ul>
		{/if}
		{#if desk.deleteError}<p class="text-sm text-destructive" role="alert">{desk.deleteError}</p>{/if}
		<AlertDialog.Footer>
			<AlertDialog.Cancel>Keep {desk.tasksToDelete.length > 1 ? 'them' : 'it'}</AlertDialog.Cancel>
			<AlertDialog.Action onclick={(e) => (e.preventDefault(), desk.confirmDelete())}>Delete</AlertDialog.Action>
		</AlertDialog.Footer>
	</AlertDialog.Content>
</AlertDialog.Root>

<AlertDialog.Root open={desk.leaving !== null} onOpenChange={(o) => !o && desk.keepEditing()}>
	<AlertDialog.Content>
		<AlertDialog.Header>
			<AlertDialog.Title>Save your changes?</AlertDialog.Title>
			<AlertDialog.Description>
				{desk.sheetTask ? `"${desk.sheetTask.title}" has` : 'This new task has'} changes that are not saved yet. Save them, discard them, or go back and keep editing.
			</AlertDialog.Description>
		</AlertDialog.Header>
		<AlertDialog.Footer>
			<AlertDialog.Cancel>Keep editing</AlertDialog.Cancel>
			<AlertDialog.Action
				class="bg-secondary text-secondary-foreground hover:bg-secondary/80"
				disabled={desk.leaveSaving}
				onclick={(e) => (e.preventDefault(), desk.discardAndLeave())}
			>
				Discard
			</AlertDialog.Action>
			<AlertDialog.Action disabled={desk.leaveSaving} onclick={(e) => (e.preventDefault(), desk.saveAndLeave())}>
				{desk.leaveSaving ? 'Saving...' : 'Save'}
			</AlertDialog.Action>
		</AlertDialog.Footer>
	</AlertDialog.Content>
</AlertDialog.Root>
