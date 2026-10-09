<script lang="ts">
	import type { Board } from '$lib/api'
	import * as AlertDialog from '$lib/components/ui/alert-dialog/index.js'
	import type { ProjectDesk } from '$lib/projectDesk.svelte'
	import TaskSheet from './TaskSheet.svelte'

	// The task panel and the "delete this task?" question that every page working on tasks shows.
	let { desk, boards }: { desk: ProjectDesk; boards: Board[] } = $props()

	const sheetBoard = $derived(boards.find((b) => b.id === desk.sheetBoardId) ?? boards[0] ?? null)
</script>

{#if desk.project && sheetBoard}
	<TaskSheet
		bind:open={desk.sheetOpen}
		projectId={desk.projectId}
		task={desk.sheetTask}
		board={sheetBoard}
		defaultStatus={desk.sheetStatus}
		defs={desk.project.properties}
		timezone={desk.system?.timezone ?? 'UTC'}
		now={desk.now}
		onchange={() => desk.reload()}
		ondelete={(task) => desk.askDelete(task)}
	/>
{/if}
<AlertDialog.Root open={desk.taskToDelete !== null} onOpenChange={(o) => !o && (desk.taskToDelete = null)}>
	<AlertDialog.Content>
		<AlertDialog.Header>
			<AlertDialog.Title>Delete this task?</AlertDialog.Title>
			<AlertDialog.Description>
				"{desk.taskToDelete?.title}" and its attempt history will be removed. The project's History keeps a note that it was deleted.
			</AlertDialog.Description>
		</AlertDialog.Header>
		{#if desk.deleteError}<p class="text-sm text-destructive" role="alert">{desk.deleteError}</p>{/if}
		<AlertDialog.Footer>
			<AlertDialog.Cancel>Keep it</AlertDialog.Cancel>
			<AlertDialog.Action onclick={(e) => (e.preventDefault(), desk.confirmDelete())}>Delete</AlertDialog.Action>
		</AlertDialog.Footer>
	</AlertDialog.Content>
</AlertDialog.Root>
