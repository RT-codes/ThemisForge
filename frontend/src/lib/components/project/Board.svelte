<script lang="ts">
	import type { PropertyDef, Task, TaskStatus } from '$lib/api'
	import { applyView, type ColumnResult } from '$lib/boardView'
	import type { BoardViewStore } from '$lib/boardView.svelte'
	import type { Board as BoardInfo } from '$lib/api'
	import { statusTone, type ColumnInfo } from '$lib/boards'
	import StatusIcon from '$lib/components/StatusIcon.svelte'
	import * as Tooltip from '$lib/components/ui/tooltip/index.js'
	import InfoIcon from '@lucide/svelte/icons/info'
	import StatusEditPopover from './StatusEditPopover.svelte'
	import { dragTask } from '$lib/dragTask.svelte'
	import { appendPositions, dropPosition, rangePick, togglePick } from '$lib/kanban'
	import { onClickAway } from '$lib/clickAway'
	import { Button } from '$lib/components/ui/button/index.js'
	import * as DropdownMenu from '$lib/components/ui/dropdown-menu/index.js'
	import { router } from '$lib/router.svelte'
	import EyeOffIcon from '@lucide/svelte/icons/eye-off'
	import ZapIcon from '@lucide/svelte/icons/zap'
	import { cn } from '$lib/utils'
	import ArrowRightIcon from '@lucide/svelte/icons/arrow-right'
	import ChevronDownIcon from '@lucide/svelte/icons/chevron-down'
	import PlusIcon from '@lucide/svelte/icons/plus'
	import Trash2Icon from '@lucide/svelte/icons/trash-2'
	import { slide } from 'svelte/transition'
	import { onMount } from 'svelte'
	import ColumnBar from './ColumnBar.svelte'
	import TaskCard from './TaskCard.svelte'

	let {
		tasks,
		boardId,
		columns,
		defs,
		now,
		view,
		projectId,
		watchers,
		selectedId = null,
		focusedId = null,
		onfocus,
		onopen,
		onclosedetails,
		ondelete,
		onadd,
		onmove,
		onmovemany,
		onstatuschange,
	}: {
		tasks: Task[]
		boardId: number
		/** the board's columns left to right: the built-in statuses and its own */
		columns: ColumnInfo[]
		defs: PropertyDef[]
		now: number
		view: BoardViewStore
		projectId: number
		/** the workflows that start by themselves when a task moves into each status */
		watchers: Record<string, { id: number; name: string }[]>
		/** the task whose details are open in the side panel */
		selectedId?: number | null
		/** the card selected on its own (a plain click), shown unfolded */
		focusedId?: number | null
		/** a card was selected on its own (or let go of: null) */
		onfocus: (id: number | null) => void
		/** the pencil on a card: open its details in the panel */
		onopen: (task: Task) => void
		/** a selection is being made: the details panel steps aside, then `then` runs (not if the person keeps editing) */
		onclosedetails: (then: () => void) => void
		/** ask to delete these tasks: one from a card's trash button, or the whole selection */
		ondelete: (tasks: Task[]) => void
		onadd: (status: TaskStatus) => void
		/** a card dropped here; it may come from another board (task.board_id differs from boardId) */
		onmove: (task: Task, status: TaskStatus, position: number, boardId: number) => void
		/** the selection sent to a status, each at its position at the end of that column */
		onmovemany: (moves: { task: Task; position: number }[], status: TaskStatus) => void
		/** a status of this board was edited from its column: the board as it is now */
		onstatuschange: (board: BoardInfo) => void
	} = $props()

	const byStatus = $derived(
		Object.fromEntries(
			columns.map((s) => [s.id, tasks.filter((t) => t.status === s.id).sort((a, b) => a.position - b.position)])
		) as Record<TaskStatus, Task[]>
	)

	// each column as it is displayed: after the board's search and filters, its own, and the order
	const results = $derived(
		Object.fromEntries(columns.map((s) => [s.id, applyView(byStatus[s.id], view.board, view.column(s.id))])) as Record<TaskStatus, ColumnResult>
	)

	// Ctrl (or cmd) and click picks several cards, to act on them together; shift and click picks a run of them. The
	// selection belongs to this board: cards of another board on the same page are not part of it. A running task cannot
	// be moved or deleted, so it is never picked, and a picked one that starts running drops out by itself.
	let pickedIds = $state<number[]>([])
	// where a shift+click range starts: the card last opened or ctrl+clicked
	let anchorId = $state<number | null>(null)
	const picked = $derived(tasks.filter((t) => pickedIds.includes(t.id) && t.status !== 'running'))
	const pickedSet = $derived(new Set(picked.map((t) => t.id)))
	// a task cannot be sent to Running by hand: only the scheduler starts tasks
	const targets = $derived(columns.filter((c) => c.id !== 'running'))

	function clearPicked() {
		pickedIds = []
		anchorId = null
	}

	// a plain click: select the card on its own, which unfolds it, or let go of it again
	function select(task: Task) {
		pickedIds = []
		anchorId = task.id
		onfocus(focusedId === task.id ? null : task.id)
	}

	function pick(task: Task, e: MouseEvent | KeyboardEvent) {
		if (task.status === 'running') return
		let ids: number[]
		let anchor: number | null
		// the card that was selected on its own (or open in the panel) was chosen first: it is where a range starts, and
		// it is part of the selection too
		const first = focusedId ?? selectedId
		if (e.shiftKey) {
			// A range stays inside one status: its ends are two cards of the same column, in the order it is shown. A card
			// of another status (or no start at all) is not the end of a range, so shift never reaches across: the card
			// is picked on its own, and becomes where the next range starts.
			const from = anchorId ?? first
			const range = from === null ? null : rangePick((results[task.status]?.shown ?? []).map((t) => t.id), from, task.id)
			const add = e.ctrlKey || e.metaKey // shift alone makes it the whole selection; with ctrl it is added to it
			const made = (range ?? [task.id]).filter((id) => tasks.find((t) => t.id === id)?.status !== 'running')
			ids = add ? [...new Set([...pickedIds, ...made])] : made
			anchor = range ? from : task.id
		} else {
			const open = first === null ? undefined : tasks.find((t) => t.id === first)
			ids = togglePick(pickedIds, task.id, open && open.status !== 'running' ? open.id : null)
			anchor = task.id
		}
		// A selection of several shows nothing extra on its cards, so the unfolded one folds. The panel closes too: a
		// selection and one task's details do not belong side by side. If the panel holds changes that are not saved the
		// person is asked, and the selection only changes once the panel goes.
		const apply = () => {
			pickedIds = ids
			anchorId = anchor
			onfocus(null)
		}
		if (selectedId !== null) onclosedetails(apply)
		else apply()
	}

	function sendPicked(status: TaskStatus) {
		const rank = new Map(columns.map((c, i) => [c.id, i]))
		// in the order they are seen on the board, so they keep it in the new column
		const movers = picked
			.filter((t) => t.status !== status)
			.sort((a, b) => (rank.get(a.status) ?? 0) - (rank.get(b.status) ?? 0) || a.position - b.position)
		if (movers.length === 0) return
		const positions = appendPositions(byStatus[status].map((t) => t.position), movers.length)
		onmovemany(movers.map((task, i) => ({ task, position: positions[i] })), status)
		clearPicked()
	}

	function escape(e: KeyboardEvent) {
		const typing = e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement
		if (e.key === 'Escape' && (picked.length || focusedId !== null) && !typing) {
			clearPicked()
			onfocus(null)
		}
	}

	let overColumn = $state<TaskStatus | null>(null)
	let overIndex = $state(0)

	// the card in hand may belong to another board of the page: it can be dropped here
	const dragged = $derived(dragTask.task)
	const dragId = $derived(dragged?.id ?? null)

	function canDrop(status: TaskStatus) {
		return dragged !== null && status !== 'running' // only the scheduler starts tasks
	}

	function dragOver(e: DragEvent, status: TaskStatus, column: HTMLElement) {
		if (!canDrop(status)) return
		e.preventDefault()
		overColumn = status
		const cards = [...column.querySelectorAll<HTMLElement>('[data-card]')].filter((c) => Number(c.dataset.card) !== dragId)
		let index = cards.length
		if (!results[status].reorderable) {
			overIndex = index // the cards are not in your order, so a card can only go to the end
			return
		}
		for (let i = 0; i < cards.length; i++) {
			const box = cards[i].getBoundingClientRect()
			if (e.clientY < box.top + box.height / 2) {
				index = i
				break
			}
		}
		overIndex = index
	}

	function drop(status: TaskStatus) {
		const task = dragged
		const index = overIndex
		const allowed = canDrop(status) // before reset(): it clears the drag, so `dragged` becomes null
		reset()
		if (!task || !allowed) return
		const siblings = byStatus[status].filter((t) => t.id !== task.id)
		const reorderable = results[status].reorderable
		const here = task.board_id === boardId
		if (here && status === task.status && !reorderable) return // a sorted or filtered column has no order of its own to change
		if (here && status === task.status && byStatus[status].findIndex((t) => t.id === task.id) === index) return // same spot
		const position = dropPosition(
			siblings.map((t) => t.position),
			reorderable ? index : siblings.length // not in your order: to the end of the column
		)
		onmove(task, status, position, boardId)
	}

	function reset() {
		dragTask.end()
		overColumn = null
	}

	// the board scrolls sideways: a soft fade on an edge says there is more that way
	let scroller = $state<HTMLDivElement>()
	let moreLeft = $state(false)
	let moreRight = $state(false)
	// the scrollbar sits above the columns: a slim track whose thumb follows the board and can be dragged
	let clientWidth = $state(0)
	let scrollWidth = $state(0)
	let scrollLeft = $state(0)
	const overflowing = $derived(scrollWidth > clientWidth + 1)
	const thumbWidth = $derived(Math.max(32, (clientWidth / Math.max(scrollWidth, 1)) * clientWidth))
	const thumbLeft = $derived(
		scrollWidth > clientWidth ? (scrollLeft / (scrollWidth - clientWidth)) * (clientWidth - thumbWidth) : 0
	)
	let drag: { startX: number; startLeft: number } | null = null
	function scrollToThumb(left: number) {
		if (!scroller) return
		const room = clientWidth - thumbWidth
		scroller.scrollLeft = room > 0 ? (Math.min(Math.max(left, 0), room) / room) * (scrollWidth - clientWidth) : 0
	}
	function grab(e: PointerEvent) {
		drag = { startX: e.clientX, startLeft: thumbLeft }
		;(e.currentTarget as HTMLElement).setPointerCapture(e.pointerId)
		e.stopPropagation()
	}
	function moveThumb(e: PointerEvent) {
		if (drag) scrollToThumb(drag.startLeft + e.clientX - drag.startX)
	}
	function jump(e: PointerEvent) {
		// a click on the track itself centres the thumb there
		if (e.target === e.currentTarget) scrollToThumb(e.offsetX - thumbWidth / 2)
	}
	function measure() {
		if (!scroller) return
		scrollWidth = scroller.scrollWidth
		clientWidth = scroller.clientWidth
		scrollLeft = scroller.scrollLeft
		moreLeft = scroller.scrollLeft > 4
		moreRight = scroller.scrollLeft + scroller.clientWidth < scroller.scrollWidth - 4
	}
	// clicking on empty space lets go of the selection
	onMount(() =>
		onClickAway(() => {
			if (pickedIds.length || focusedId !== null) {
				clearPicked()
				onfocus(null)
			}
		})
	)
	onMount(() => {
		measure()
		const observer = new ResizeObserver(measure)
		if (scroller) observer.observe(scroller)
		return () => observer.disconnect()
	})
</script>

<svelte:window onkeydown={escape} />

<div class="flex h-full min-h-0 flex-col">
{#if picked.length}
	<!-- what can be done with the selected cards; it sits above the columns so it is always where you are looking -->
	<div
		class="mb-2 flex shrink-0 flex-wrap items-center gap-2 rounded-lg border border-primary/40 bg-primary/5 px-3 py-1.5 text-sm"
		role="toolbar"
		aria-label="Selected tasks"
		transition:slide={{ duration: 120 }}
	>
		<span class="font-medium tabular-nums">{picked.length} selected</span>
		<DropdownMenu.Root>
			<DropdownMenu.Trigger>
				{#snippet child({ props })}
					<Button {...props} variant="outline" size="sm" class="h-7 gap-1.5"><ArrowRightIcon />Move to<ChevronDownIcon /></Button>
				{/snippet}
			</DropdownMenu.Trigger>
			<DropdownMenu.Content align="start" class="w-52">
				<DropdownMenu.Label class="text-xs font-normal text-muted-foreground">Send the selected tasks to</DropdownMenu.Label>
				{#each targets as c (c.id)}
					<DropdownMenu.Item disabled={picked.every((t) => t.status === c.id)} onSelect={() => sendPicked(c.id)}>
						<span class={cn('shrink-0', !c.color && statusTone(c.id).text)} style:color={c.color ?? undefined}>
							<StatusIcon status={c.id} icon={c.icon} class="size-4" />
						</span>
						{c.label}
					</DropdownMenu.Item>
				{/each}
			</DropdownMenu.Content>
		</DropdownMenu.Root>
		<Button variant="outline" size="sm" class="h-7 gap-1.5 text-destructive hover:text-destructive" onclick={() => ondelete(picked)}>
			<Trash2Icon />Delete
		</Button>
		<Button variant="ghost" size="sm" class="ms-auto h-7 text-muted-foreground" onclick={clearPicked}>Clear</Button>
	</div>
{/if}
{#if overflowing}
	<div class="relative mb-2 h-1.5 shrink-0 rounded-full bg-muted" data-keep-selection onpointerdown={jump} role="presentation">
		<div
			class="absolute inset-y-0 rounded-full bg-muted-foreground/50 transition-colors hover:bg-primary active:bg-primary"
			style:width="{thumbWidth}px"
			style:left="{thumbLeft}px"
			onpointerdown={grab}
			onpointermove={moveThumb}
			onpointerup={() => (drag = null)}
			onpointercancel={() => (drag = null)}
			role="presentation"
		></div>
	</div>
{/if}
<div class="relative min-h-0 flex-1">
<div bind:this={scroller} onscroll={measure} class="no-scrollbar flex h-full items-start gap-3 overflow-x-auto">
	{#each columns.filter((s) => !view.hidden.includes(s.id)) as column (column.id)}
		{@const items = results[column.id].shown}
		{@const target = overColumn === column.id}
		{@const slots = new Map(items.filter((t) => t.id !== dragId).map((t, i) => [t.id, i]))}
		<section
			role="list"
			aria-label={column.label}
			class={cn(
				'flex max-h-full min-h-44 w-[17rem] shrink-0 flex-col rounded-xl border bg-card/40 transition-colors',
				target && 'border-primary/50 bg-primary/5',
				dragged && column.id === 'running' && 'opacity-50'
			)}
			ondragover={(e) => dragOver(e, column.id, e.currentTarget)}
			ondragleave={(e) => {
				if (!e.currentTarget.contains(e.relatedTarget as Node)) overColumn = null
			}}
			ondrop={(e) => (e.preventDefault(), drop(column.id))}
		>
			<header class="flex h-12 items-center gap-1.5 px-3 pt-1">
				<span class={cn('shrink-0', !column.color && statusTone(column.id).text)} style:color={column.color ?? undefined}>
					<StatusIcon status={column.id} icon={column.icon} class="size-4" />
				</span>
				<h3 class="truncate text-sm font-medium">{column.label}</h3>
				<span class="rounded-full bg-muted px-1.5 text-xs text-muted-foreground tabular-nums" title={results[column.id].filtered ? `${items.length} of ${byStatus[column.id].length} tasks match` : undefined}>
					{results[column.id].filtered ? `${items.length} / ${byStatus[column.id].length}` : items.length}
				</span>
				<!-- what the status is for: fixed for the built-in ones, the owner's own words for a status of your own -->
				<Tooltip.Root>
					<Tooltip.Trigger>
						{#snippet child({ props })}
							<button type="button" class="rounded-full p-0.5 text-muted-foreground/70 transition-colors hover:text-foreground focus-visible:text-foreground" aria-label={`What ${column.label} is for`} {...props}>
								<InfoIcon class="size-3.5" />
							</button>
						{/snippet}
					</Tooltip.Trigger>
					<Tooltip.Content side="bottom" class="max-w-64">{column.hint}</Tooltip.Content>
				</Tooltip.Root>
				{#if watchers[column.id]?.length}
					<DropdownMenu.Root>
						<DropdownMenu.Trigger
							class="inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-xs text-primary transition-colors hover:bg-primary/10"
							title="Moving a task here starts a workflow"
						>
							<ZapIcon class="size-3" />{watchers[column.id].length}
						</DropdownMenu.Trigger>
						<DropdownMenu.Content align="start" class="w-56">
							<DropdownMenu.Label class="text-xs font-normal text-muted-foreground">A task moved into {column.label} starts</DropdownMenu.Label>
							{#each watchers[column.id] as w (w.id)}
								<DropdownMenu.Item onSelect={() => router.navigate(`/projects/${projectId}/workflows/${w.id}`)}>{w.name}</DropdownMenu.Item>
							{/each}
						</DropdownMenu.Content>
					</DropdownMenu.Root>
				{/if}
				<div class="ms-auto flex items-center">
					<StatusEditPopover {boardId} {column} onchange={onstatuschange} />
					<button
						type="button"
						class="rounded-md p-1 text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
						aria-label={`Hide ${column.label}`}
						title={`Hide ${column.label} (bring it back with Statuses)`}
						onclick={() => view.toggleHidden(column.id)}
					>
						<EyeOffIcon class="size-4" />
					</button>
					{#if column.id !== 'running'}
						<button
							type="button"
							class="rounded-md p-1 text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
							aria-label={`Add task to ${column.label}`}
							onclick={() => onadd(column.id)}
						>
							<PlusIcon class="size-4" />
						</button>
					{/if}
				</div>
			</header>
			<ColumnBar {view} status={column.id} label={column.label} {defs} />
			<div class="slim-scrollbar flex min-h-24 flex-1 flex-col gap-2 overflow-y-auto px-2 pb-2">
				{#each items as task (task.id)}
					{@const slot = slots.get(task.id)}
					{#if target && slot !== undefined && overIndex === slot}
						<div class="h-1 shrink-0 rounded-full bg-primary"></div>
					{/if}
					<TaskCard
						{task}
						{defs}
						{now}
						dragging={task.id === dragId}
						selected={task.id === selectedId}
						expanded={task.id === focusedId}
						picked={pickedSet.has(task.id)}
						data-card={task.id}
						onselect={() => select(task)}
						onedit={() => (clearPicked(), onopen(task))}
						onpick={(e: MouseEvent | KeyboardEvent) => pick(task, e)}
						ondelete={() => ondelete([task])}
						ondragstart={(e: DragEvent) => {
							dragTask.start(task)
							e.dataTransfer?.setData('text/plain', String(task.id))
							if (e.dataTransfer) e.dataTransfer.effectAllowed = 'move'
						}}
						ondragend={reset}
					/>
				{/each}
				{#if target && overIndex >= items.length - (items.some((t) => t.id === dragId) ? 1 : 0)}
					<div class="h-1 shrink-0 rounded-full bg-primary"></div>
				{/if}
				{#if items.length === 0 && !target}
					<p class="m-auto px-2 py-6 text-center text-xs text-muted-foreground/70">
						{results[column.id].filtered ? 'No tasks match' : column.id === 'running' ? 'Running tasks show up here' : 'Drop tasks here'}
					</p>
				{/if}
			</div>
		</section>
	{/each}
</div>
<div class={cn('pointer-events-none absolute inset-y-0 start-0 w-10 bg-gradient-to-r from-background to-transparent transition-opacity duration-200', !moreLeft && 'opacity-0')}></div>
<div class={cn('pointer-events-none absolute inset-y-0 end-0 w-14 bg-gradient-to-l from-background to-transparent transition-opacity duration-200', !moreRight && 'opacity-0')}></div>
</div>
</div>
