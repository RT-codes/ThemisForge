<script lang="ts">
	import type { Board as BoardInfo } from '$lib/api'
	import { MIN_BOARD_HEIGHT, clampHeight, columnsOf, statusTone } from '$lib/boards'
	import StatusIcon from '$lib/components/StatusIcon.svelte'
	import AnvilIcon from '@lucide/svelte/icons/anvil'
	import { isDefaultView } from '$lib/boardView'
	import { BoardViewStore } from '$lib/boardView.svelte'
	import { Button } from '$lib/components/ui/button/index.js'
	import * as DropdownMenu from '$lib/components/ui/dropdown-menu/index.js'
	import type { ProjectDesk } from '$lib/projectDesk.svelte'
	import { pulseWhen } from '$lib/pulse'
	import { cn } from '$lib/utils'
	import { watchersByStatus } from '$lib/workflow'
	import ChevronDownIcon from '@lucide/svelte/icons/chevron-down'
	import ChevronRightIcon from '@lucide/svelte/icons/chevron-right'
	import EllipsisIcon from '@lucide/svelte/icons/ellipsis'
	import ExternalLinkIcon from '@lucide/svelte/icons/external-link'
	import PlusIcon from '@lucide/svelte/icons/plus'
	import { untrack } from 'svelte'
	import Board from './Board.svelte'

	// One board inside a workspace page: a header that folds the board away, and the board itself below it. The
	// full toolbar (search, filters) is on the board's own page; what was chosen there applies here too.
	let {
		board,
		desk,
		legacyProjectId,
		collapsed,
		canMoveUp,
		canMoveDown,
		fill = false,
		ontoggle,
		onmove,
		onedit,
		onstatuses,
		onduplicate,
		onremove,
	}: {
		board: BoardInfo
		desk: ProjectDesk
		/** set for the project's first board, which inherits the view that used to be remembered per project */
		legacyProjectId?: number
		collapsed: boolean
		canMoveUp: boolean
		canMoveDown: boolean
		/** the only board of its workspace: it takes the height of the page, like a board page */
		fill?: boolean
		ontoggle: () => void
		onmove: (step: -1 | 1) => void
		onedit: () => void
		onstatuses: () => void
		onduplicate: () => void
		onremove: () => void
	} = $props()

	const view = new BoardViewStore(
		untrack(() => board.id),
		untrack(() => legacyProjectId)
	)
	const columns = $derived(columnsOf(board))
	const tasks = $derived(desk.tasks.filter((t) => t.board_id === board.id))
	const filtered = $derived(!isDefaultView(view.board))

	// counted from the live tasks (not the board's stored counts), so the bar follows every move within seconds
	const segments = $derived(
		columns.map((c) => ({
			id: c.id,
			label: c.label,
			color: c.color,
			tone: statusTone(c.id),
			icon: c.icon,
			count: tasks.filter((t) => t.status === c.id).length,
		}))
	)

	const total = $derived(tasks.length)

	// The height of the open board. Until the handle is used it is the default (set by classes); after that it is a number
	// of pixels, kept per board in this browser.
	const heightKey = `themis.boardHeight.b${untrack(() => board.id)}`
	let height = $state<number | null>(readHeight())
	function readHeight(): number | null {
		try {
			const n = Number(localStorage.getItem(heightKey))
			return Number.isFinite(n) && n > 0 ? clampHeight(n, window.innerHeight) : null
		} catch {
			return null
		}
	}
	function setHeight(px: number | null) {
		height = px === null ? null : clampHeight(px, window.innerHeight)
		try {
			if (height === null) localStorage.removeItem(heightKey)
			else localStorage.setItem(heightKey, String(height))
		} catch {
			// remembering is a convenience
		}
	}
	let drag: { startY: number; startHeight: number } | null = null
	function startResize(e: PointerEvent) {
		const board = (e.currentTarget as HTMLElement).previousElementSibling as HTMLElement | null
		if (!board) return
		drag = { startY: e.clientY, startHeight: board.getBoundingClientRect().height }
		;(e.currentTarget as HTMLElement).setPointerCapture(e.pointerId)
	}
	function resize(e: PointerEvent) {
		if (drag) setHeight(drag.startHeight + e.clientY - drag.startY)
	}
	const endResize = () => (drag = null)
	function resizeByKey(e: KeyboardEvent) {
		if (e.key !== 'ArrowUp' && e.key !== 'ArrowDown') return
		e.preventDefault()
		const current = height ?? (e.currentTarget as HTMLElement).previousElementSibling?.getBoundingClientRect().height ?? 456
		setHeight(current + (e.key === 'ArrowDown' ? 32 : -32))
	}

	// Whenever the numbers change after the board has loaded (a task moved, was made or deleted) the taskbar pulses once,
	// so a folded board still says that something just happened on it.
	let pulses = $state(0)
	let last: string | null = null
	$effect(() => {
		const now = segments.map((s) => s.count).join(',')
		if (desk.revision === 0) return // still loading: the first numbers are not news
		if (last !== null && last !== now) pulses++
		last = now
	})
</script>

<section class="overflow-hidden rounded-xl border bg-card/30" aria-label={board.name}>
	<!-- the board's taskbar: always visible, so a workspace with every board folded still shows how each one is doing -->
	<header
		class={cn('relative flex flex-wrap items-center gap-x-4 gap-y-2 overflow-hidden bg-muted/30 px-3 py-2.5', collapsed ? 'rounded-xl' : 'rounded-t-xl border-b')}
		use:pulseWhen={pulses}
	>
		<Button variant="ghost" size="icon-sm" aria-label={collapsed ? `Show ${board.name}` : `Fold ${board.name}`} aria-expanded={!collapsed} onclick={ontoggle}>
			{#if collapsed}<ChevronRightIcon />{:else}<ChevronDownIcon />{/if}
		</Button>
		<div class="flex min-w-0 flex-1 items-center gap-2.5 sm:max-w-64 sm:flex-none">
			<AnvilIcon class="size-5 shrink-0 text-muted-foreground" />
			<div class="min-w-0">
				<h3 class="truncate text-sm font-semibold tracking-tight" title={board.name}>{board.name}</h3>
				<p class="truncate text-xs text-muted-foreground" title={board.purpose || undefined}>{board.purpose || `${total} ${total === 1 ? 'task' : 'tasks'}`}</p>
			</div>
		</div>
		<div class="hidden h-7 w-px shrink-0 bg-border sm:block" aria-hidden="true"></div>
		<!-- one segment per status with the number of tasks in it -->
		<!-- a quarter of the taskbar: counts only (the name of a status is in its tooltip), the full words on a narrow screen -->
		<ul class="no-scrollbar order-last flex min-w-0 basis-full items-stretch divide-x divide-border/60 overflow-x-auto rounded-lg border bg-background/60 sm:order-none sm:w-1/4 sm:min-w-64 sm:flex-none sm:basis-auto" aria-label="Tasks per status">
			{#each segments as seg (seg.id)}
				<li
					class={cn('flex min-w-fit flex-1 items-center justify-center gap-1.5 px-2 py-1.5 text-xs transition-[opacity,background-color] first:ps-2.5 last:pe-2.5 hover:bg-accent/40', seg.count === 0 && 'opacity-40')}
					title="{seg.label}: {seg.count} {seg.count === 1 ? 'task' : 'tasks'}"
				>
					<span class={cn('shrink-0', !seg.color && seg.tone.text, seg.id === 'running' && seg.count > 0 && 'animate-pulse')} style:color={seg.color ?? undefined}>
						<StatusIcon status={seg.id} icon={seg.icon} class="size-3.5" />
					</span>
					<span class="text-muted-foreground sm:hidden">{seg.label}</span>
					<span class={cn('font-semibold tabular-nums', seg.count > 0 ? seg.tone.text : 'text-muted-foreground')}>{seg.count}</span>
				</li>
			{/each}
		</ul>
		{#if filtered && !collapsed}
			<span class="rounded-full border px-2 py-0.5 text-xs text-muted-foreground" title="A search or filter chosen on this board's page is applied">Filtered</span>
		{/if}
		<div class="ms-auto flex items-center gap-0.5">
			<Button variant="ghost" size="sm" onclick={() => desk.addTask(board.id)}><PlusIcon /> Task</Button>
			<Button variant="ghost" size="sm" href="/projects/{board.project_id}/boards/{board.id}" aria-label={`Open ${board.name} on its own page`}><ExternalLinkIcon /> Open</Button>
			<DropdownMenu.Root>
				<DropdownMenu.Trigger>
					{#snippet child({ props })}
						<Button variant="ghost" size="icon-sm" aria-label={`${board.name} menu`} {...props}><EllipsisIcon /></Button>
					{/snippet}
				</DropdownMenu.Trigger>
				<DropdownMenu.Content align="end" class="w-48">
					<DropdownMenu.Item onSelect={onedit}>Edit board</DropdownMenu.Item>
					<DropdownMenu.Item onSelect={onstatuses}>Add or edit statuses</DropdownMenu.Item>
					<DropdownMenu.Item onSelect={onduplicate}>Duplicate</DropdownMenu.Item>
					<DropdownMenu.Separator />
					<DropdownMenu.Item disabled={!canMoveUp} onSelect={() => onmove(-1)}>Move up</DropdownMenu.Item>
					<DropdownMenu.Item disabled={!canMoveDown} onSelect={() => onmove(1)}>Move down</DropdownMenu.Item>
					<DropdownMenu.Separator />
					<DropdownMenu.Item class="text-destructive focus:text-destructive" onSelect={onremove}>Delete board</DropdownMenu.Item>
				</DropdownMenu.Content>
			</DropdownMenu.Root>
		</div>
	</header>
	{#if !collapsed && desk.project}
		<div
			class={cn('px-3 pt-3', height === null && (fill ? 'h-[max(28.25rem,calc(100svh-20rem))]' : 'h-[28.25rem]'))}
			style:height={height === null ? undefined : `${height}px`}
		>
			<Board
				{tasks}
				boardId={board.id}
				{columns}
				defs={desk.project.properties}
				now={desk.now}
				{view}
				projectId={desk.projectId}
				watchers={watchersByStatus(desk.workflows, board)}
				selectedId={desk.sheetOpen ? desk.sheetTaskId : null}
				onopen={(t) => desk.openTask(t)}
				ondelete={(t) => desk.askDelete(t)}
				onadd={(status) => desk.addTask(board.id, status)}
				onmove={(t, status, position, to) => desk.moveTask(t, status, position, to)}
				onstatuschange={() => desk.reload()}
			/>
		</div>
		<!-- drag this handle to make the board taller or shorter; the height is remembered for this board in this browser -->
		<!-- svelte-ignore a11y_no_noninteractive_tabindex, a11y_no_noninteractive_element_interactions -- a focusable separator is the ARIA window splitter -->
		<div
			class="group flex h-4 cursor-ns-resize touch-none items-center justify-center outline-none"
			role="separator"
			aria-orientation="horizontal"
			aria-label="Resize {board.name}"
			aria-valuenow={height ?? undefined}
			aria-valuemin={MIN_BOARD_HEIGHT}
			tabindex="0"
			onpointerdown={startResize}
			onpointermove={resize}
			onpointerup={endResize}
			onpointercancel={endResize}
			onkeydown={resizeByKey}
			ondblclick={() => setHeight(null)}
			title="Drag to resize, double-click to reset"
		>
			<span class="h-1 w-12 rounded-full bg-border transition-colors group-hover:bg-primary/60 group-focus-visible:bg-primary group-active:bg-primary"></span>
		</div>
	{/if}
</section>
