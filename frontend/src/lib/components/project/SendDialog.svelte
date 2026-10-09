<script lang="ts">
	import { api, ApiError, type Task, type TaskStatus, type Workspace } from '$lib/api'
	import { columnsOf, destinationLabel } from '$lib/boards'
	import { Button } from '$lib/components/ui/button/index.js'
	import * as Dialog from '$lib/components/ui/dialog/index.js'
	import { Input } from '$lib/components/ui/input/index.js'
	import { Label } from '$lib/components/ui/label/index.js'
	import * as Select from '$lib/components/ui/select/index.js'
	import { Textarea } from '$lib/components/ui/textarea/index.js'

	// Two ways to get work onto another board. Send: the same task continues there. Follow-up: a new task is created
	// there and linked to this one, which stays where it is.
	let {
		open = $bindable(false),
		mode,
		task,
		workspaces,
		ondone,
	}: { open: boolean; mode: 'move' | 'spawn'; task: Task; workspaces: Workspace[]; ondone: () => void } = $props()

	let boardId = $state('')
	let status = $state<string>('backlog')
	let title = $state('')
	let description = $state('')
	let error = $state('')
	let busy = $state(false)

	const boards = $derived(workspaces.flatMap((w) => w.boards).filter((b) => mode === 'spawn' || b.id !== task.board_id))
	const board = $derived(boards.find((b) => String(b.id) === boardId) ?? null)
	// the scheduler is the only thing that starts a task, so Running is never a place to send one
	const columns = $derived(board ? columnsOf(board).filter((c) => c.id !== 'running') : [])

	$effect(() => {
		if (open) {
			boardId = String(boards[0]?.id ?? '')
			title = `Follow-up: ${task.title}`.slice(0, 200)
			description = ''
			error = ''
		}
	})

	// a task keeps its status when the board has it; a follow-up starts in the Backlog
	$effect(() => {
		if (board) status = mode === 'move' && columns.some((c) => c.id === task.status) ? task.status : 'backlog'
	})

	async function submit(e: SubmitEvent) {
		e.preventDefault()
		if (!board) return
		busy = true
		error = ''
		try {
			if (mode === 'move') await api.moveTask(task.id, { board_id: board.id, status: status as TaskStatus })
			else await api.spawnTask(task.id, { board_id: board.id, title, description, status: status as TaskStatus })
			open = false
			ondone()
		} catch (err) {
			error = err instanceof ApiError || err instanceof Error ? err.message : 'That did not work'
		} finally {
			busy = false
		}
	}
</script>

<Dialog.Root bind:open>
	<Dialog.Content class="sm:max-w-md">
		<Dialog.Header>
			<Dialog.Title>{mode === 'move' ? 'Send to another board' : 'Create a follow-up'}</Dialog.Title>
			<Dialog.Description>
				{#if mode === 'move'}
					"{task.title}" continues on the board you choose, with its history, schedule and properties.
				{:else}
					A new task is created on the board you choose and linked to "{task.title}", which stays where it is.
				{/if}
			</Dialog.Description>
		</Dialog.Header>
		<form onsubmit={submit} class="grid gap-4">
			<div class="grid gap-2">
				<Label>Board</Label>
				<Select.Root type="single" bind:value={boardId}>
					<Select.Trigger class="w-full">{board ? destinationLabel(workspaces, board) : 'Choose a board'}</Select.Trigger>
					<Select.Content>
						{#each boards as b (b.id)}
							<Select.Item value={String(b.id)} label={destinationLabel(workspaces, b)}>{destinationLabel(workspaces, b)}</Select.Item>
						{/each}
					</Select.Content>
				</Select.Root>
			</div>
			<div class="grid gap-2">
				<Label>Status</Label>
				<Select.Root type="single" bind:value={status}>
					<Select.Trigger class="w-full">{columns.find((c) => c.id === status)?.label ?? ''}</Select.Trigger>
					<Select.Content>
						{#each columns as c (c.id)}<Select.Item value={c.id} label={c.label}>{c.label}</Select.Item>{/each}
					</Select.Content>
				</Select.Root>
			</div>
			{#if mode === 'spawn'}
				<div class="grid gap-2">
					<Label for="follow-title">Title</Label>
					<Input id="follow-title" bind:value={title} required maxlength={200} />
				</div>
				<div class="grid gap-2">
					<Label for="follow-description">Description</Label>
					<Textarea id="follow-description" bind:value={description} rows={4} maxlength={20000} placeholder="What the follow-up should do" />
				</div>
			{/if}
			{#if error}<p class="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive" role="alert">{error}</p>{/if}
			<Dialog.Footer>
				<Button type="button" variant="ghost" onclick={() => (open = false)}>Cancel</Button>
				<Button type="submit" disabled={busy || !board || (mode === 'spawn' && !title.trim())}>{mode === 'move' ? 'Send' : 'Create follow-up'}</Button>
			</Dialog.Footer>
		</form>
	</Dialog.Content>
</Dialog.Root>
