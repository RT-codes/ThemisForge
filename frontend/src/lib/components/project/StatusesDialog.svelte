<script lang="ts">
	import { api, ApiError, type Board, type Task, type TaskStatus } from '$lib/api'
	import { columnsOf, customId } from '$lib/boards'
	import ColorPicker from '$lib/components/ColorPicker.svelte'
	import StatusIcon from '$lib/components/StatusIcon.svelte'
	import { Button } from '$lib/components/ui/button/index.js'
	import * as Dialog from '$lib/components/ui/dialog/index.js'
	import { Input } from '$lib/components/ui/input/index.js'
	import * as Select from '$lib/components/ui/select/index.js'
	import ArrowDownIcon from '@lucide/svelte/icons/arrow-down'
	import ArrowUpIcon from '@lucide/svelte/icons/arrow-up'
	import LockIcon from '@lucide/svelte/icons/lock'
	import PlusIcon from '@lucide/svelte/icons/plus'
	import Trash2Icon from '@lucide/svelte/icons/trash-2'

	// Add, rename, colour, place and delete the custom statuses of a board. Every change is saved at once (it moves
	// columns and sometimes tasks), and the server answers with the board as it now is.
	let {
		open = $bindable(false),
		board,
		tasks,
		onchange,
	}: {
		open: boolean
		board: Board
		tasks: Task[]
		/** the board after a change, so the page can show its new columns (and reload the tasks) */
		onchange: (board: Board) => void
	} = $props()

	const columns = $derived(columnsOf(board))
	let newName = $state('')
	let busy = $state(false)
	let error = $state('')
	// the status being deleted, and where its tasks go
	let removing = $state<TaskStatus | null>(null)
	let moveTo = $state<TaskStatus>('backlog')

	// Ready and Running would start work, so tasks leaving a deleted status can only go to a parking status
	const destinations = $derived(columns.filter((c) => c.id !== removing && c.id !== 'ready' && c.id !== 'running'))
	const countIn = (status: TaskStatus) => tasks.filter((t) => t.board_id === board.id && t.status === status).length

	$effect(() => {
		if (!open) {
			removing = null
			error = ''
			newName = ''
		}
	})

	async function run(action: () => Promise<Board>) {
		busy = true
		error = ''
		try {
			onchange(await action())
			return true
		} catch (e) {
			error = e instanceof ApiError || e instanceof Error ? e.message : 'Could not save'
			return false
		} finally {
			busy = false
		}
	}

	async function add(e: SubmitEvent) {
		e.preventDefault()
		const name = newName.trim()
		if (!name) return
		// right after Backlog, where a status for work that has not started yet usually belongs; it can be moved from here
		if (await run(() => api.addStatus(board.id, { name, index: 1 }))) newName = ''
	}

	function rename(key: TaskStatus, name: string, current: string) {
		const id = customId(key)
		if (id !== null && name.trim() && name.trim() !== current) run(() => api.updateStatus(board.id, id, { name: name.trim() }))
	}

	const recolor = (key: TaskStatus, color: string | undefined) => {
		const id = customId(key)
		if (id !== null) run(() => api.updateStatus(board.id, id, { color: color ?? null }))
	}

	// the server counts the index without the status itself, so one step up is the slot above it and one step down the slot below
	const shift = (key: TaskStatus, from: number, step: -1 | 1) => {
		const id = customId(key)
		if (id !== null) run(() => api.updateStatus(board.id, id, { index: from + step }))
	}

	function askRemove(key: TaskStatus) {
		moveTo = 'backlog'
		removing = key
	}

	async function remove() {
		const id = removing === null ? null : customId(removing)
		if (id === null) return
		if (await run(() => api.removeStatus(board.id, id, moveTo))) removing = null
	}
</script>

<Dialog.Root bind:open>
	<Dialog.Content class="sm:max-w-lg">
		<Dialog.Header>
			<Dialog.Title>Statuses of {board.name}</Dialog.Title>
			<Dialog.Description>
				The seven built-in statuses are fixed. Add your own and place them anywhere around them. Tasks wait in a status of yours until you move them on.
			</Dialog.Description>
		</Dialog.Header>

		<ul class="grid max-h-[50vh] gap-1.5 overflow-y-auto pe-1">
			{#each columns as c, i (c.id)}
				<li class="rounded-lg border bg-card/40">
					<div class="flex items-center gap-2 px-2.5 py-1.5">
						{#if c.builtin}
							<LockIcon class="size-3.5 shrink-0 text-muted-foreground/60" aria-label="Built-in" />
							<StatusIcon status={c.id} class="size-4 shrink-0 text-muted-foreground" />
							<span class="flex-1 text-sm">{c.label}</span>
							<span class="hidden truncate text-xs text-muted-foreground sm:block">{c.hint}</span>
						{:else}
							<ColorPicker value={c.color ?? undefined} label={`Colour of ${c.label}`} onchange={(colour) => recolor(c.id, colour)} />
							<StatusIcon status={c.id} icon={c.icon} class="size-4 shrink-0 text-muted-foreground" />
							<Input
								class="h-8 flex-1"
								value={c.label}
								maxlength={40}
								aria-label="Status name"
								disabled={busy}
								onchange={(e) => rename(c.id, e.currentTarget.value, c.label)}
							/>
							<Button type="button" variant="ghost" size="icon-sm" aria-label={`Move ${c.label} earlier`} disabled={busy || i === 0} onclick={() => shift(c.id, i, -1)}><ArrowUpIcon /></Button>
							<Button type="button" variant="ghost" size="icon-sm" aria-label={`Move ${c.label} later`} disabled={busy || i === columns.length - 1} onclick={() => shift(c.id, i, 1)}><ArrowDownIcon /></Button>
							<Button type="button" variant="ghost" size="icon-sm" aria-label={`Delete ${c.label}`} disabled={busy} onclick={() => askRemove(c.id)}><Trash2Icon /></Button>
						{/if}
					</div>
					{#if removing === c.id}
						<div class="grid gap-2 border-t px-2.5 py-2 text-sm">
							{#if countIn(c.id) > 0}
								<p>Move its {countIn(c.id)} {countIn(c.id) === 1 ? 'task' : 'tasks'} to:</p>
								<Select.Root type="single" bind:value={moveTo}>
									<Select.Trigger class="w-full">{destinations.find((d) => d.id === moveTo)?.label}</Select.Trigger>
									<Select.Content>
										{#each destinations as d (d.id)}<Select.Item value={d.id} label={d.label}>{d.label}</Select.Item>{/each}
									</Select.Content>
								</Select.Root>
							{:else}
								<p>No tasks are in it.</p>
							{/if}
							<div class="flex justify-end gap-2">
								<Button type="button" variant="ghost" size="sm" onclick={() => (removing = null)}>Keep it</Button>
								<Button type="button" variant="destructive" size="sm" disabled={busy} onclick={remove}>Delete status</Button>
							</div>
						</div>
					{/if}
				</li>
			{/each}
		</ul>

		<form onsubmit={add} class="flex gap-2">
			<Input bind:value={newName} placeholder="New status, e.g. Investigating" maxlength={40} aria-label="New status name" disabled={busy} />
			<Button type="submit" disabled={busy || !newName.trim()}><PlusIcon /> Add</Button>
		</form>
		{#if error}
			<p class="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive" role="alert">{error}</p>
		{/if}
		<Dialog.Footer>
			<Button type="button" onclick={() => (open = false)}>Done</Button>
		</Dialog.Footer>
	</Dialog.Content>
</Dialog.Root>
