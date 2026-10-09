<script lang="ts">
	import { api, ApiError, type Board } from '$lib/api'
	import { Button } from '$lib/components/ui/button/index.js'
	import * as Dialog from '$lib/components/ui/dialog/index.js'
	import { Input } from '$lib/components/ui/input/index.js'
	import { Label } from '$lib/components/ui/label/index.js'

	// Create a board in a workspace, or rename and describe one (`board`).
	let {
		open = $bindable(false),
		workspaceId,
		board = null,
		onsaved,
	}: { open: boolean; workspaceId: number; board?: Board | null; onsaved: (board: Board) => void } = $props()

	let name = $state('')
	let purpose = $state('')
	let error = $state('')
	let saving = $state(false)

	$effect(() => {
		if (open) {
			name = board?.name ?? ''
			purpose = board?.purpose ?? ''
			error = ''
		}
	})

	async function save(e: SubmitEvent) {
		e.preventDefault()
		error = ''
		saving = true
		try {
			onsaved(board ? await api.updateBoard(board.id, { name, purpose }) : await api.createBoard(workspaceId, { name, purpose }))
			open = false
		} catch (err) {
			error = err instanceof ApiError || err instanceof Error ? err.message : 'Could not save the board'
		} finally {
			saving = false
		}
	}
</script>

<Dialog.Root bind:open>
	<Dialog.Content class="sm:max-w-md">
		<Dialog.Header>
			<Dialog.Title>{board ? 'Edit board' : 'New board'}</Dialog.Title>
			<Dialog.Description>A board is one Kanban with its own statuses. A new one starts with the seven built-in statuses.</Dialog.Description>
		</Dialog.Header>
		<form onsubmit={save} class="grid gap-4">
			<div class="grid gap-2">
				<Label for="board-name">Name</Label>
				<Input id="board-name" bind:value={name} required maxlength={60} placeholder="Research" />
			</div>
			<div class="grid gap-2">
				<Label for="board-purpose">What it is for</Label>
				<Input id="board-purpose" bind:value={purpose} maxlength={200} placeholder="Find out what to build" />
			</div>
			{#if error}<p class="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive" role="alert">{error}</p>{/if}
			<Dialog.Footer>
				<Button type="button" variant="ghost" onclick={() => (open = false)}>Cancel</Button>
				<Button type="submit" disabled={saving || !name.trim()}>{board ? 'Save' : 'Create'}</Button>
			</Dialog.Footer>
		</form>
	</Dialog.Content>
</Dialog.Root>
