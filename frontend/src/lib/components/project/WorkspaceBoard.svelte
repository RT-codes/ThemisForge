<script lang="ts">
	import type { Board as BoardInfo } from '$lib/api'
	import { boardSummary, columnsOf } from '$lib/boards'
	import { isDefaultView } from '$lib/boardView'
	import { BoardViewStore } from '$lib/boardView.svelte'
	import { Button } from '$lib/components/ui/button/index.js'
	import * as DropdownMenu from '$lib/components/ui/dropdown-menu/index.js'
	import type { ProjectDesk } from '$lib/projectDesk.svelte'
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
</script>

<section class="rounded-xl border bg-card/30" aria-label={board.name}>
	<header class="flex flex-wrap items-center gap-2 px-3 py-2">
		<Button variant="ghost" size="icon-sm" aria-label={collapsed ? `Show ${board.name}` : `Fold ${board.name}`} aria-expanded={!collapsed} onclick={ontoggle}>
			{#if collapsed}<ChevronRightIcon />{:else}<ChevronDownIcon />{/if}
		</Button>
		<div class="min-w-0 flex-1">
			<h3 class="truncate text-sm font-semibold">{board.name}</h3>
			<p class="truncate text-xs text-muted-foreground">{board.purpose || boardSummary(board)}</p>
		</div>
		{#if filtered && !collapsed}
			<span class="rounded-full border px-2 py-0.5 text-xs text-muted-foreground" title="A search or filter chosen on this board's page is applied">Filtered</span>
		{/if}
		{#if board.purpose}<span class="hidden text-xs text-muted-foreground sm:block">{boardSummary(board)}</span>{/if}
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
	</header>
	{#if !collapsed && desk.project}
		<div class={fill ? 'h-[max(28rem,calc(100svh-22rem))] px-3 pb-3' : 'h-[28rem] px-3 pb-3'}>
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
