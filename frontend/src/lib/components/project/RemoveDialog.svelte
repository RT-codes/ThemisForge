<script lang="ts">
	import { api, ApiError, type Board, type Workspace } from '$lib/api'
	import { destinationLabel, survivingBoards, taskTotal } from '$lib/boards'
	import * as AlertDialog from '$lib/components/ui/alert-dialog/index.js'
	import * as Select from '$lib/components/ui/select/index.js'

	// Deleting a board or a whole workspace. Tasks are never deleted with it: they move to a board the person picks, and a
	// project always keeps at least one board.
	let {
		target = $bindable(null),
		workspaces,
		ondeleted,
	}: {
		target: { kind: 'board'; board: Board } | { kind: 'workspace'; workspace: Workspace } | null
		workspaces: Workspace[]
		ondeleted: () => void
	} = $props()

	let moveTo = $state('')
	let error = $state('')
	let busy = $state(false)

	const tasks = $derived(target === null ? 0 : target.kind === 'board' ? taskTotal(target.board) : target.workspace.boards.reduce((n, b) => n + taskTotal(b), 0))
	const name = $derived(target === null ? '' : target.kind === 'board' ? target.board.name : target.workspace.name)
	const destinations = $derived(
		target === null ? [] : survivingBoards(workspaces, target.kind === 'board' ? { board: target.board.id } : { workspace: target.workspace.id })
	)

	const where = (b: Board) => destinationLabel(workspaces, b)

	$effect(() => {
		if (target) {
			moveTo = String(destinations[0]?.id ?? '')
			error = ''
		}
	})

	async function remove() {
		if (!target) return
		busy = true
		error = ''
		try {
			const to = tasks > 0 ? Number(moveTo) : undefined
			if (target.kind === 'board') await api.deleteBoard(target.board.id, to)
			else await api.deleteWorkspace(target.workspace.id, to)
			target = null
			ondeleted()
		} catch (e) {
			error = e instanceof ApiError || e instanceof Error ? e.message : 'Could not delete it'
		} finally {
			busy = false
		}
	}
</script>

<AlertDialog.Root open={target !== null} onOpenChange={(o) => !o && (target = null)}>
	<AlertDialog.Content>
		<AlertDialog.Header>
			<AlertDialog.Title>Delete "{name}"?</AlertDialog.Title>
			<AlertDialog.Description>
				{#if destinations.length === 0}
					A project needs at least one board, so the last one cannot be deleted.
				{:else if tasks > 0}
					Its {tasks} {tasks === 1 ? 'task is' : 'tasks are'} not deleted. Choose the board they move to. A task in a status that only this {target?.kind === 'board' ? 'board' : 'workspace'} has goes to the Backlog.
				{:else}
					It has no tasks. This cannot be undone.
				{/if}
			</AlertDialog.Description>
		</AlertDialog.Header>
		{#if tasks > 0 && destinations.length > 0}
			<Select.Root type="single" bind:value={moveTo}>
				<Select.Trigger class="w-full">{where(destinations.find((b) => String(b.id) === moveTo) ?? destinations[0])}</Select.Trigger>
				<Select.Content>
					{#each destinations as d (d.id)}
						<Select.Item value={String(d.id)} label={where(d)}>{where(d)}</Select.Item>
					{/each}
				</Select.Content>
			</Select.Root>
		{/if}
		{#if error}<p class="text-sm text-destructive" role="alert">{error}</p>{/if}
		<AlertDialog.Footer>
			<AlertDialog.Cancel>Keep it</AlertDialog.Cancel>
			<AlertDialog.Action disabled={busy || destinations.length === 0} onclick={(e) => (e.preventDefault(), remove())}>Delete</AlertDialog.Action>
		</AlertDialog.Footer>
	</AlertDialog.Content>
</AlertDialog.Root>
