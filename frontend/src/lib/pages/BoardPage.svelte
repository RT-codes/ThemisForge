<script lang="ts">
	import { api, type Board as BoardInfo, type Workspace } from '$lib/api'
	import { columnsOf, defaultBoard, findBoard, isSimple, workspaceOf } from '$lib/boards'
	import { watchersByStatus } from '$lib/workflow'
	import { BoardViewStore } from '$lib/boardView.svelte'
	import Board from '$lib/components/project/Board.svelte'
	import BoardDialog from '$lib/components/project/BoardDialog.svelte'
	import BoardToolbar from '$lib/components/project/BoardToolbar.svelte'
	import DeskDialogs from '$lib/components/project/DeskDialogs.svelte'
	import ProjectDialog from '$lib/components/project/ProjectDialog.svelte'
	import HistoryList from '$lib/components/project/HistoryList.svelte'
	import PropertiesDialog from '$lib/components/project/PropertiesDialog.svelte'
	import RemoveDialog from '$lib/components/project/RemoveDialog.svelte'
	import ScheduleTimeline from '$lib/components/project/ScheduleTimeline.svelte'
	import StatusesDialog from '$lib/components/project/StatusesDialog.svelte'
	import TaskList from '$lib/components/project/TaskList.svelte'
	import WorkspaceDialog from '$lib/components/project/WorkspaceDialog.svelte'
	import * as AlertDialog from '$lib/components/ui/alert-dialog/index.js'
	import { Button } from '$lib/components/ui/button/index.js'
	import * as DropdownMenu from '$lib/components/ui/dropdown-menu/index.js'
	import * as Tabs from '$lib/components/ui/tabs/index.js'
	import { relative } from '$lib/format'
	import { ProjectDesk } from '$lib/projectDesk.svelte'
	import { projects } from '$lib/projects.svelte'
	import { router } from '$lib/router.svelte'
	import { structure } from '$lib/structure.svelte'
	import EllipsisIcon from '@lucide/svelte/icons/ellipsis'
	import PlusIcon from '@lucide/svelte/icons/plus'
	import { onMount, untrack } from 'svelte'
	import { fade } from 'svelte/transition'

	// One board on its own: its Board, List, Schedule and History. `boardId` null is the address /tasks, the project's
	// first board.
	let { id, boardId = null }: { id: number; boardId?: number | null } = $props()

	const desk = new ProjectDesk(untrack(() => id)) // the page is rebuilt for every project, so the id does not change here
	onMount(() => desk.start())

	let tab = $state('board')
	let propsOpen = $state(false)
	let statusesOpen = $state(false)
	let editProjectOpen = $state(false)
	let deleteProjectOpen = $state(false)
	let deleteProjectError = $state('')
	let boardDialog = $state<'new' | 'edit'>('new')
	let boardDialogOpen = $state(false)
	let workspaceDialog = $state(false)
	let removing = $state<{ kind: 'board'; board: BoardInfo } | null>(null)

	const workspaces = $derived<Workspace[]>(structure.get(id) ?? [])
	const board = $derived(boardId === null ? defaultBoard(workspaces) : findBoard(workspaces, boardId))
	const workspace = $derived(board ? workspaceOf(workspaces, board.id) : null)
	const simple = $derived(isSimple(workspaces))
	const columns = $derived(board ? columnsOf(board) : [])
	// what this board shows and remembers in this browser; rebuilt only when another board is opened
	const boardKey = $derived(board?.id ?? null)
	const view = $derived.by(() => (boardKey === null ? null : new BoardViewStore(boardKey, boardKey === defaultBoard(workspaces)?.id ? id : undefined)))

	const tasks = $derived(desk.tasks.filter((t) => t.board_id === board?.id))
	const defs = $derived(desk.project?.properties ?? [])
	const counts = $derived({
		running: tasks.filter((t) => t.status === 'running').length,
		ready: tasks.filter((t) => t.status === 'ready').length,
		review: tasks.filter((t) => t.status === 'review').length,
		failed: tasks.filter((t) => t.status === 'failed').length,
	})
	const nextRun = $derived(
		tasks
			.filter((t) => t.status === 'ready' && t.next_run_at)
			.map((t) => t.next_run_at!)
			.sort()[0] ?? null
	)

	/** the board after its statuses changed: show its new columns, and fetch the tasks (deleting a status moves some) */
	async function boardChanged() {
		await desk.reload()
	}

	async function duplicate() {
		if (!board) return
		const copy = await api.duplicateBoard(board.id)
		await desk.reload()
		router.navigate(`/projects/${id}/boards/${copy.id}`)
	}

	async function deleteProject() {
		deleteProjectError = ''
		try {
			await api.deleteProject(id)
			await projects.refresh()
			deleteProjectOpen = false
			router.navigate('/')
		} catch (e) {
			deleteProjectError = e instanceof Error ? e.message : 'Could not delete the project'
		}
	}
</script>

{#if desk.notFound}
	<div class="m-auto text-center">
		<p class="text-lg font-medium">Project not found</p>
		<p class="mt-1 text-sm text-muted-foreground">It may have been deleted.</p>
		<Button class="mt-4" onclick={() => router.navigate('/')}>Back home</Button>
	</div>
{:else if desk.project && structure.get(id) && !board}
	<div class="m-auto text-center">
		<p class="text-lg font-medium">Board not found</p>
		<p class="mt-1 text-sm text-muted-foreground">It may have been deleted.</p>
		<Button class="mt-4" onclick={() => router.navigate(`/projects/${id}`)}>Back to the project</Button>
	</div>
{:else if desk.project && board && view}
	<div class="flex min-h-0 flex-1 flex-col gap-4 px-6 py-6" in:fade={{ duration: 350 }}>
		<div class="flex flex-wrap items-start gap-x-6 gap-y-3">
			<div class="min-w-0 flex-1">
				{#if !simple && workspace}
					<a href="/projects/{id}/workspaces/{workspace.id}" class="text-xs text-muted-foreground transition-colors hover:text-foreground">{workspace.name}</a>
				{/if}
				<h2 class="truncate text-2xl font-semibold tracking-tight">{simple ? 'Tasks' : board.name}</h2>
				{#if !simple && board.purpose}<p class="mt-0.5 truncate text-sm text-muted-foreground">{board.purpose}</p>{/if}
			</div>
			<div class="flex items-center gap-2">
				<Button onclick={() => desk.addTask(board.id)}><PlusIcon /> New task</Button>
				<DropdownMenu.Root>
					<DropdownMenu.Trigger>
						{#snippet child({ props })}
							<Button variant="outline" size="icon" aria-label="Project menu" {...props}><EllipsisIcon /></Button>
						{/snippet}
					</DropdownMenu.Trigger>
					<DropdownMenu.Content align="end" class="w-52">
						<DropdownMenu.Item onSelect={() => ((boardDialog = 'new'), (boardDialogOpen = true))}>New board</DropdownMenu.Item>
						<DropdownMenu.Item onSelect={() => (workspaceDialog = true)}>New workspace</DropdownMenu.Item>
						<DropdownMenu.Separator />
						<DropdownMenu.Item onSelect={() => ((boardDialog = 'edit'), (boardDialogOpen = true))}>Edit this board</DropdownMenu.Item>
						<DropdownMenu.Item onSelect={duplicate}>Duplicate this board</DropdownMenu.Item>
						<DropdownMenu.Item class="text-destructive focus:text-destructive" onSelect={() => (removing = { kind: 'board', board })}>Delete this board</DropdownMenu.Item>
						<DropdownMenu.Separator />
						<DropdownMenu.Item onSelect={() => (propsOpen = true)}>Task properties</DropdownMenu.Item>
						<DropdownMenu.Item onSelect={() => (editProjectOpen = true)}>Rename project</DropdownMenu.Item>
						<DropdownMenu.Item class="text-destructive focus:text-destructive" onSelect={() => ((deleteProjectError = ''), (deleteProjectOpen = true))}>
							Delete project
						</DropdownMenu.Item>
					</DropdownMenu.Content>
				</DropdownMenu.Root>
			</div>
		</div>

		<div class="flex flex-wrap items-center gap-2 text-xs">
			<span class="inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1">
				<span class="size-1.5 rounded-full {counts.running ? 'animate-pulse bg-primary' : 'bg-muted-foreground/50'}"></span>
				{counts.running} running
			</span>
			<span class="rounded-full border px-2.5 py-1">{counts.ready} ready</span>
			{#if counts.review}<span class="rounded-full border px-2.5 py-1 text-violet-300">{counts.review} to review</span>{/if}
			{#if counts.failed}<span class="rounded-full border px-2.5 py-1 text-destructive">{counts.failed} failed</span>{/if}
			<span class="rounded-full border px-2.5 py-1 text-muted-foreground">
				{nextRun ? `Next run ${relative(nextRun, desk.now)}` : 'Nothing scheduled'}
			</span>
			{#if desk.system}
				<span
					class="ms-auto inline-flex items-center gap-1.5 text-muted-foreground"
					title="Containers running now out of how many may run at once. The scheduler checks for due tasks every few seconds, around the clock."
				>
					<span class="size-1.5 rounded-full {desk.system.scheduler.running ? 'bg-emerald-400' : 'bg-destructive'}"></span>
					{desk.system.scheduler.running ? 'Scheduler on' : 'Scheduler off'} · {desk.system.scheduler.active_cells}/{desk.system.scheduler.max_cells} containers
				</span>
			{/if}
		</div>

		{#if desk.loadError}
			<p class="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive" role="alert">{desk.loadError}</p>
		{/if}

		<Tabs.Root bind:value={tab} class="min-h-0 flex-1 gap-4">
			<div class="flex flex-wrap items-center gap-3">
				<Tabs.List>
					<Tabs.Trigger value="board">Board</Tabs.Trigger>
					<Tabs.Trigger value="list">List</Tabs.Trigger>
					<Tabs.Trigger value="schedule">Schedule</Tabs.Trigger>
					<Tabs.Trigger value="history">History</Tabs.Trigger>
				</Tabs.List>
				<!-- search, order and filters for the whole board; each status adds its own under its title -->
				{#if tab === 'board'}
					<div class="ms-auto"><BoardToolbar {view} {defs} {columns} onmanage={() => (statusesOpen = true)} /></div>
				{/if}
			</div>
			<Tabs.Content value="board" class="min-h-0 flex-1">
				<Board {tasks} boardId={board.id} {columns} {defs} now={desk.now} {view} projectId={id} watchers={watchersByStatus(desk.workflows)} selectedId={desk.sheetOpen ? desk.sheetTaskId : null} onopen={(t) => desk.openTask(t)} ondelete={(t) => desk.askDelete(t)} onadd={(status) => desk.addTask(board.id, status)} onmove={(t, status, position, to) => desk.moveTask(t, status, position, to)} />
			</Tabs.Content>
			<Tabs.Content value="list">
				<TaskList {tasks} {board} {defs} now={desk.now} selectedId={desk.sheetOpen ? desk.sheetTaskId : null} onopen={(t) => desk.openTask(t)} />
			</Tabs.Content>
			<Tabs.Content value="schedule">
				<ScheduleTimeline projectId={id} now={desk.now} timezone={desk.system?.timezone ?? 'UTC'} revision={desk.revision} />
			</Tabs.Content>
			<Tabs.Content value="history">
				<HistoryList projectId={id} scope={{ boardId: board.id }} {workspaces} tasks={desk.tasks} ontask={(t) => desk.openTask(t)} now={desk.now} revision={desk.revision} />
			</Tabs.Content>
		</Tabs.Root>
	</div>

	<DeskDialogs {desk} {workspaces} />
	<StatusesDialog bind:open={statusesOpen} {board} {tasks} onchange={boardChanged} />
	<PropertiesDialog bind:open={propsOpen} projectId={id} {defs} onsaved={() => desk.reload()} />
	<ProjectDialog bind:open={editProjectOpen} project={desk.project} onsaved={() => desk.reload()} />
	<BoardDialog
		bind:open={boardDialogOpen}
		workspaceId={board.workspace_id}
		board={boardDialog === 'edit' ? board : null}
		onsaved={async (saved) => {
			await desk.reload()
			if (boardDialog === 'new') router.navigate(`/projects/${id}/boards/${saved.id}`)
		}}
	/>
	<WorkspaceDialog
		bind:open={workspaceDialog}
		projectId={id}
		onsaved={async (saved) => {
			await desk.reload()
			router.navigate(`/projects/${id}/workspaces/${saved.id}`)
		}}
	/>
	<RemoveDialog bind:target={removing} {workspaces} ondeleted={async () => (await desk.reload(), router.navigate(`/projects/${id}`))} />

	<AlertDialog.Root bind:open={deleteProjectOpen}>
		<AlertDialog.Content>
			<AlertDialog.Header>
				<AlertDialog.Title>Delete "{desk.project.name}"?</AlertDialog.Title>
				<AlertDialog.Description>
					All of its tasks and their history are removed permanently. The project's files on disk are kept.
				</AlertDialog.Description>
			</AlertDialog.Header>
			{#if deleteProjectError}<p class="text-sm text-destructive" role="alert">{deleteProjectError}</p>{/if}
			<AlertDialog.Footer>
				<AlertDialog.Cancel>Keep it</AlertDialog.Cancel>
				<AlertDialog.Action onclick={(e) => (e.preventDefault(), deleteProject())}>Delete project</AlertDialog.Action>
			</AlertDialog.Footer>
		</AlertDialog.Content>
	</AlertDialog.Root>
{:else if desk.loadError}
	<p class="m-auto text-sm text-destructive">{desk.loadError}</p>
{/if}
