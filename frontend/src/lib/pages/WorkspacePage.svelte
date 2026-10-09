<script lang="ts">
	import { api, type Board as BoardInfo, type Workspace } from '$lib/api'
	import { defaultBoard, parseCollapsed } from '$lib/boards'
	import BoardDialog from '$lib/components/project/BoardDialog.svelte'
	import DeskDialogs from '$lib/components/project/DeskDialogs.svelte'
	import HistoryList from '$lib/components/project/HistoryList.svelte'
	import RemoveDialog from '$lib/components/project/RemoveDialog.svelte'
	import StatusesDialog from '$lib/components/project/StatusesDialog.svelte'
	import WorkspaceBoard from '$lib/components/project/WorkspaceBoard.svelte'
	import WorkspaceDialog from '$lib/components/project/WorkspaceDialog.svelte'
	import { Button } from '$lib/components/ui/button/index.js'
	import * as DropdownMenu from '$lib/components/ui/dropdown-menu/index.js'
	import * as Tabs from '$lib/components/ui/tabs/index.js'
	import { dropPosition } from '$lib/kanban'
	import { ProjectDesk } from '$lib/projectDesk.svelte'
	import { router } from '$lib/router.svelte'
	import { structure } from '$lib/structure.svelte'
	import EllipsisIcon from '@lucide/svelte/icons/ellipsis'
	import PlusIcon from '@lucide/svelte/icons/plus'
	import { onMount, untrack } from 'svelte'
	import { fade } from 'svelte/transition'

	// A workspace: its boards stacked in the order the person chose, each one foldable and open on its own page.
	// `workspaceId` null is the old address /tasks: the project's first workspace, which it moves to.
	let { id, workspaceId }: { id: number; workspaceId: number | null } = $props()

	const desk = new ProjectDesk(untrack(() => id))
	onMount(() => desk.start())

	const workspaces = $derived<Workspace[]>(structure.get(id) ?? [])
	const workspace = $derived((workspaceId === null ? workspaces[0] : workspaces.find((w) => w.id === workspaceId)) ?? null)
	$effect(() => {
		if (workspaceId === null && workspace) router.replace(`/projects/${id}/workspaces/${workspace.id}`)
	})
	const allBoards = $derived(workspaces.flatMap((w) => w.boards))
	const firstBoardId = $derived(defaultBoard(workspaces)?.id)

	// folded boards are remembered in this browser, per workspace
	const foldedKey = `themis.workspace.${untrack(() => workspaceId)}.folded`
	let folded = $state<number[]>(parseCollapsed(readFolded()))
	function readFolded() {
		try {
			return localStorage.getItem(foldedKey)
		} catch {
			return null
		}
	}
	function toggle(boardId: number) {
		folded = folded.includes(boardId) ? folded.filter((b) => b !== boardId) : [...folded, boardId]
		try {
			localStorage.setItem(foldedKey, JSON.stringify(folded))
		} catch {
			// remembering is a convenience
		}
	}

	let error = $state('')
	let boardDialog = $state<BoardInfo | 'new' | null>(null)
	let boardDialogOpen = $state(false)
	let workspaceDialog = $state<'new' | 'edit'>('edit')
	let workspaceDialogOpen = $state(false)
	let statusesBoard = $state<BoardInfo | null>(null)
	let statusesOpen = $state(false)
	let removing = $state<{ kind: 'board'; board: BoardInfo } | { kind: 'workspace'; workspace: Workspace } | null>(null)

	async function run(action: () => Promise<unknown>) {
		error = ''
		try {
			await action()
			await desk.reload()
		} catch (e) {
			error = e instanceof Error ? e.message : 'That did not work'
		}
	}

	/** one step up or down: the board takes a position between its new neighbours, so only it is saved */
	function shift(board: BoardInfo, step: -1 | 1) {
		const others = workspace!.boards.filter((b) => b.id !== board.id)
		const index = workspace!.boards.findIndex((b) => b.id === board.id) + step
		run(() => api.updateBoard(board.id, { position: dropPosition(others.map((b) => b.position), index) }))
	}

	function edit(board: BoardInfo) {
		boardDialog = board
		boardDialogOpen = true
	}

	function openStatuses(board: BoardInfo) {
		statusesBoard = board
		statusesOpen = true
	}

	async function duplicate(board: BoardInfo) {
		await run(() => api.duplicateBoard(board.id))
	}
</script>

{#if desk.notFound}
	<div class="m-auto text-center">
		<p class="text-lg font-medium">Project not found</p>
		<Button class="mt-4" onclick={() => router.navigate('/')}>Back home</Button>
	</div>
{:else if desk.project && structure.get(id) && !workspace}
	<div class="m-auto text-center">
		<p class="text-lg font-medium">Workspace not found</p>
		<p class="mt-1 text-sm text-muted-foreground">It may have been deleted.</p>
		<Button class="mt-4" onclick={() => router.navigate(`/projects/${id}`)}>Back to the project</Button>
	</div>
{:else if desk.project && workspace}
	<div class="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto px-6 py-6" in:fade={{ duration: 350 }}>
		<div class="flex flex-wrap items-start gap-x-6 gap-y-3">
			<div class="min-w-0 flex-1">
				<h2 class="truncate text-2xl font-semibold tracking-tight">{workspace.name}</h2>
				{#if workspace.purpose}<p class="mt-0.5 text-sm text-muted-foreground">{workspace.purpose}</p>{/if}
				{#if workspace.description}<p class="mt-2 max-w-3xl text-sm whitespace-pre-line text-muted-foreground/80">{workspace.description}</p>{/if}
			</div>
			<div class="flex items-center gap-2">
				<Button onclick={() => ((boardDialog = 'new'), (boardDialogOpen = true))}><PlusIcon /> New board</Button>
				<DropdownMenu.Root>
					<DropdownMenu.Trigger>
						{#snippet child({ props })}
							<Button variant="outline" size="icon" aria-label="Workspace menu" {...props}><EllipsisIcon /></Button>
						{/snippet}
					</DropdownMenu.Trigger>
					<DropdownMenu.Content align="end" class="w-48">
						<DropdownMenu.Item onSelect={() => ((workspaceDialog = 'edit'), (workspaceDialogOpen = true))}>Edit workspace</DropdownMenu.Item>
						<DropdownMenu.Item onSelect={() => ((workspaceDialog = 'new'), (workspaceDialogOpen = true))}>New workspace</DropdownMenu.Item>
						<DropdownMenu.Separator />
						<DropdownMenu.Item class="text-destructive focus:text-destructive" onSelect={() => (removing = { kind: 'workspace', workspace })}>Delete workspace</DropdownMenu.Item>
					</DropdownMenu.Content>
				</DropdownMenu.Root>
			</div>
		</div>

		{#if error || desk.loadError}
			<p class="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive" role="alert">{error || desk.loadError}</p>
		{/if}

		<Tabs.Root value="boards" class="gap-4">
		<Tabs.List>
			<Tabs.Trigger value="boards">Boards</Tabs.Trigger>
			<Tabs.Trigger value="history">History</Tabs.Trigger>
		</Tabs.List>
		<Tabs.Content value="boards" class="grid gap-4">
		{#each workspace.boards as board, i (board.id)}
			<WorkspaceBoard
				{board}
				{desk}
				legacyProjectId={board.id === firstBoardId ? id : undefined}
				collapsed={folded.includes(board.id)}
				canMoveUp={i > 0}
				canMoveDown={i < workspace.boards.length - 1}
				fill={workspace.boards.length === 1}
				ontoggle={() => toggle(board.id)}
				onmove={(step) => shift(board, step)}
				onedit={() => edit(board)}
				onstatuses={() => openStatuses(board)}
				onduplicate={() => duplicate(board)}
				onremove={() => (removing = { kind: 'board', board })}
			/>
		{:else}
			<div class="rounded-xl border border-dashed px-4 py-12 text-center">
				<p class="text-sm font-medium">No boards in this workspace yet</p>
				<p class="mt-1 text-xs text-muted-foreground">A board is a Kanban with its own statuses.</p>
				<Button class="mt-4" onclick={() => ((boardDialog = 'new'), (boardDialogOpen = true))}><PlusIcon /> New board</Button>
			</div>
		{/each}
		</Tabs.Content>
		<Tabs.Content value="history">
			<HistoryList projectId={id} scope={{ workspaceId: workspace.id }} {workspaces} tasks={desk.tasks} ontask={(t) => desk.openTask(t)} now={desk.now} revision={desk.revision} />
		</Tabs.Content>
		</Tabs.Root>
	</div>

	<DeskDialogs {desk} {workspaces} />
	{#if statusesBoard}
		<StatusesDialog bind:open={statusesOpen} board={allBoards.find((b) => b.id === statusesBoard!.id) ?? statusesBoard} tasks={desk.tasks} onchange={() => desk.reload()} />
	{/if}
	<BoardDialog
		bind:open={boardDialogOpen}
		workspaceId={workspace.id}
		board={boardDialog === 'new' || boardDialog === null ? null : boardDialog}
		onsaved={() => desk.reload()}
	/>
	<WorkspaceDialog
		bind:open={workspaceDialogOpen}
		projectId={id}
		workspace={workspaceDialog === 'edit' ? workspace : null}
		onsaved={async (saved) => {
			await desk.reload()
			if (workspaceDialog === 'new') router.navigate(`/projects/${id}/workspaces/${saved.id}`)
		}}
	/>
	<RemoveDialog
		bind:target={removing}
		{workspaces}
		ondeleted={async () => {
			await desk.reload()
			if (!structure.get(id)?.some((w) => w.id === workspaceId)) router.navigate(`/projects/${id}`)
		}}
	/>
{:else if desk.loadError}
	<p class="m-auto text-sm text-destructive">{desk.loadError}</p>
{/if}
