<script lang="ts">
	import type { Board as BoardInfo } from '$lib/api'
	import { columnsOf } from '$lib/boards'
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

	// How each status looks in the taskbar. Done is green, Blocked and Failed are red; a status of your own brings its colour.
	const TONES: Record<string, { dot: string; text: string }> = {
		backlog: { dot: 'bg-muted-foreground/60', text: 'text-foreground' },
		ready: { dot: 'bg-sky-400', text: 'text-sky-300' },
		running: { dot: 'bg-primary', text: 'text-primary' },
		review: { dot: 'bg-violet-400', text: 'text-violet-300' },
		done: { dot: 'bg-emerald-400', text: 'text-emerald-300' },
		blocked: { dot: 'bg-red-400', text: 'text-red-300' },
		failed: { dot: 'bg-rose-500', text: 'text-rose-400' },
	}
	const OWN_TONE = { dot: 'bg-muted-foreground/60', text: 'text-foreground' }
	// counted from the live tasks (not the board's stored counts), so the bar follows every move within seconds
	const segments = $derived(
		columns.map((c) => ({
			id: c.id,
			label: c.label,
			color: c.color,
			tone: TONES[c.id] ?? OWN_TONE,
			count: tasks.filter((t) => t.status === c.id).length,
		}))
	)

	const total = $derived(tasks.length)

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
		<!-- a fixed width, so the status bars of the boards in a workspace line up -->
		<div class="min-w-0 flex-1 sm:w-52 sm:flex-none">
			<h3 class="truncate text-sm font-semibold tracking-tight" title={board.name}>{board.name}</h3>
			<p class="truncate text-xs text-muted-foreground" title={board.purpose || undefined}>{board.purpose || `${total} ${total === 1 ? 'task' : 'tasks'}`}</p>
		</div>
		<div class="hidden h-7 w-px shrink-0 bg-border sm:block" aria-hidden="true"></div>
		<!-- one segment per status with the number of tasks in it -->
		<ul class="no-scrollbar order-last flex min-w-0 basis-full items-stretch divide-x divide-border/60 overflow-x-auto rounded-lg border bg-background/60 sm:order-none sm:basis-auto sm:flex-1" aria-label="Tasks per status">
			{#each segments as seg (seg.id)}
				<li
					class={cn('flex min-w-fit flex-1 items-center justify-center gap-1.5 px-3 py-1.5 text-xs transition-[opacity,background-color] hover:bg-accent/40', seg.count === 0 && 'opacity-40')}
					title="{seg.label}: {seg.count} {seg.count === 1 ? 'task' : 'tasks'}"
				>
					<span class={cn('size-2 rounded-full', seg.tone.dot, seg.id === 'running' && seg.count > 0 && 'animate-pulse')} style:background-color={seg.color ?? undefined}></span>
					<span class="hidden text-muted-foreground lg:inline">{seg.label}</span>
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
		<!-- the same numbers as a small proportional strip under the title: how the board is doing at a glance -->
		{#if total > 0}
			<div class="pointer-events-none absolute bottom-0 left-3 flex h-[3px] w-1/4 overflow-hidden rounded-full" aria-hidden="true">
				{#each segments as seg (seg.id)}
					{#if seg.count > 0}<span class={cn('h-full', seg.tone.dot)} style:flex="{seg.count} 1 0%" style:background-color={seg.color ?? undefined}></span>{/if}
				{/each}
			</div>
		{/if}
	</header>
	{#if !collapsed && desk.project}
		<div class={fill ? 'h-[max(29rem,calc(100svh-21rem))] p-3' : 'h-[29rem] p-3'}>
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
			/>
		</div>
	{/if}
</section>
