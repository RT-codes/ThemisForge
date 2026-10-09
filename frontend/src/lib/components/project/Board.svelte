<script lang="ts">
	import type { PropertyDef, Task, TaskStatus } from '$lib/api'
	import { applyView, type ColumnResult } from '$lib/boardView'
	import type { BoardViewStore } from '$lib/boardView.svelte'
	import type { ColumnInfo } from '$lib/boards'
	import { dragTask } from '$lib/dragTask.svelte'
	import { dropPosition } from '$lib/kanban'
	import * as DropdownMenu from '$lib/components/ui/dropdown-menu/index.js'
	import { router } from '$lib/router.svelte'
	import EyeOffIcon from '@lucide/svelte/icons/eye-off'
	import ZapIcon from '@lucide/svelte/icons/zap'
	import { cn } from '$lib/utils'
	import PlusIcon from '@lucide/svelte/icons/plus'
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
		onopen,
		ondelete,
		onadd,
		onmove,
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
		onopen: (task: Task) => void
		ondelete: (task: Task) => void
		onadd: (status: TaskStatus) => void
		/** a card dropped here; it may come from another board (task.board_id differs from boardId) */
		onmove: (task: Task, status: TaskStatus, position: number, boardId: number) => void
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
	onMount(() => {
		measure()
		const observer = new ResizeObserver(measure)
		if (scroller) observer.observe(scroller)
		return () => observer.disconnect()
	})
</script>

<div class="flex h-full min-h-0 flex-col">
{#if overflowing}
	<div class="relative mb-2 h-1.5 shrink-0 rounded-full bg-muted" onpointerdown={jump} role="presentation">
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
			<header class="flex h-12 items-center gap-2 px-3 pt-1">
				{#if column.color}<span class="size-2 shrink-0 rounded-full" style:background-color={column.color}></span>{/if}
				<h3 class="truncate text-sm font-medium" title={column.hint}>{column.label}</h3>
				<span class="rounded-full bg-muted px-1.5 text-xs text-muted-foreground tabular-nums" title={results[column.id].filtered ? `${items.length} of ${byStatus[column.id].length} tasks match` : undefined}>
					{results[column.id].filtered ? `${items.length} / ${byStatus[column.id].length}` : items.length}
				</span>
				{#if watchers[column.id]?.length}
					<DropdownMenu.Root>
						<DropdownMenu.Trigger
							class="ms-auto inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-xs text-primary transition-colors hover:bg-primary/10"
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
				<button
					type="button"
					class={cn('rounded-md p-1 text-muted-foreground transition-colors hover:bg-accent hover:text-foreground', !watchers[column.id]?.length && 'ms-auto')}
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
			</header>
			<ColumnBar {view} status={column.id} label={column.label} {defs} />
			<div class="flex min-h-24 flex-1 flex-col gap-2 overflow-y-auto px-2 pb-2">
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
						data-card={task.id}
						onopen={() => onopen(task)}
						ondelete={() => ondelete(task)}
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
