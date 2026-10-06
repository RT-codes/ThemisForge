<script lang="ts">
	import { api, ApiError, type Project, type SystemStatus, type Task, type TaskStatus } from '$lib/api'
	import ProjectDialog from '$lib/components/project/ProjectDialog.svelte'
	import PropertiesDialog from '$lib/components/project/PropertiesDialog.svelte'
	import { BoardViewStore } from '$lib/boardView.svelte'
	import BoardToolbar from '$lib/components/project/BoardToolbar.svelte'
	import Board from '$lib/components/project/Board.svelte'
	import ScheduleTimeline from '$lib/components/project/ScheduleTimeline.svelte'
	import TaskList from '$lib/components/project/TaskList.svelte'
	import TaskSheet from '$lib/components/project/TaskSheet.svelte'
	import * as AlertDialog from '$lib/components/ui/alert-dialog/index.js'
	import { Button } from '$lib/components/ui/button/index.js'
	import * as DropdownMenu from '$lib/components/ui/dropdown-menu/index.js'
	import * as Tabs from '$lib/components/ui/tabs/index.js'
	import { relative } from '$lib/format'
	import { projects } from '$lib/projects.svelte'
	import { router } from '$lib/router.svelte'
	import EllipsisIcon from '@lucide/svelte/icons/ellipsis'
	import PlusIcon from '@lucide/svelte/icons/plus'
	import { onMount, untrack } from 'svelte'
	import { fade } from 'svelte/transition'

	let { id }: { id: number } = $props()

	let project = $state<Project | null>(null)
	let tasks = $state<Task[]>([])
	let system = $state<SystemStatus | null>(null)
	let notFound = $state(false)
	let loadError = $state('')
	let tab = $state('board')
	const view = new BoardViewStore(untrack(() => id)) // the board is rebuilt for every project, so the id does not change here
	let now = $state(Date.now())
	let revision = $state(0)

	let sheetOpen = $state(false)
	let sheetTaskId = $state<number | null>(null)
	let sheetStatus = $state<TaskStatus>('inbox')
	let propsOpen = $state(false)
	let editOpen = $state(false)
	let deleteOpen = $state(false)
	let deleteError = $state('')

	const sheetTask = $derived(tasks.find((t) => t.id === sheetTaskId) ?? null)
	const defs = $derived(project?.properties ?? [])
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

	async function load() {
		try {
			;[project, tasks] = await Promise.all([api.project(id), api.tasks(id)])
			system = await api.systemStatus()
			loadError = ''
			revision++
		} catch (e) {
			if (e instanceof ApiError && e.status === 404) notFound = true
			else loadError = e instanceof Error ? e.message : 'Could not load the project'
		}
	}

	async function reload() {
		await Promise.all([load(), projects.refresh()])
	}

	onMount(() => {
		load()
		const poll = setInterval(() => {
			if (document.hidden) return
			api.tasks(id).then((t) => (tasks = t)).catch(() => {})
			api.systemStatus().then((s) => (system = s)).catch(() => {})
		}, 3000)
		const clock = setInterval(() => (now = Date.now()), 20_000)
		return () => (clearInterval(poll), clearInterval(clock))
	})

	function openTask(task: Task) {
		sheetTaskId = task.id
		sheetOpen = true
	}

	function addTask(status: TaskStatus = 'inbox') {
		sheetTaskId = null
		sheetStatus = status
		sheetOpen = true
	}

	async function move(task: Task, status: TaskStatus, position: number) {
		const before = tasks
		tasks = tasks.map((t) => (t.id === task.id ? { ...t, status, position } : t)) // optimistic
		try {
			await api.updateTask(task.id, { status, position })
			await load()
		} catch (e) {
			tasks = before
			loadError = e instanceof Error ? e.message : 'Could not move the task'
		}
	}

	async function deleteProject() {
		deleteError = ''
		try {
			await api.deleteProject(id)
			await projects.refresh()
			deleteOpen = false
			router.navigate('/')
		} catch (e) {
			deleteError = e instanceof Error ? e.message : 'Could not delete the project'
		}
	}
</script>

{#if notFound}
	<div class="m-auto text-center">
		<p class="text-lg font-medium">Project not found</p>
		<p class="mt-1 text-sm text-muted-foreground">It may have been deleted.</p>
		<Button class="mt-4" onclick={() => router.navigate('/')}>Back home</Button>
	</div>
{:else if project}
	<div class="flex min-h-0 flex-1 flex-col gap-4 px-6 py-6" in:fade={{ duration: 350 }}>
		<div class="flex flex-wrap items-start gap-x-6 gap-y-3">
			<div class="min-w-0 flex-1">
				<h2 class="truncate text-2xl font-semibold tracking-tight">Tasks</h2>
			</div>
			<div class="flex items-center gap-2">
				<Button onclick={() => addTask()}><PlusIcon /> New task</Button>
				<DropdownMenu.Root>
					<DropdownMenu.Trigger>
						{#snippet child({ props })}
							<Button variant="outline" size="icon" aria-label="Project menu" {...props}><EllipsisIcon /></Button>
						{/snippet}
					</DropdownMenu.Trigger>
					<DropdownMenu.Content align="end" class="w-48">
						<DropdownMenu.Item onSelect={() => (propsOpen = true)}>Task properties</DropdownMenu.Item>
						<DropdownMenu.Item onSelect={() => (editOpen = true)}>Rename project</DropdownMenu.Item>
						<DropdownMenu.Separator />
						<DropdownMenu.Item class="text-destructive focus:text-destructive" onSelect={() => ((deleteError = ''), (deleteOpen = true))}>
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
				{nextRun ? `Next run ${relative(nextRun, now)}` : 'Nothing scheduled'}
			</span>
			{#if system}
				<span
					class="ms-auto inline-flex items-center gap-1.5 text-muted-foreground"
					title="Containers running now out of how many may run at once. The scheduler checks for due tasks every few seconds, around the clock."
				>
					<span class="size-1.5 rounded-full {system.scheduler.running ? 'bg-emerald-400' : 'bg-destructive'}"></span>
					{system.scheduler.running ? 'Scheduler on' : 'Scheduler off'} · {system.scheduler.active_cells}/{system.scheduler.max_cells} containers
				</span>
			{/if}
		</div>

		{#if loadError}
			<p class="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive" role="alert">{loadError}</p>
		{/if}

		<Tabs.Root bind:value={tab} class="min-h-0 flex-1 gap-4">
			<div class="flex flex-wrap items-center gap-3">
				<Tabs.List>
					<Tabs.Trigger value="board">Board</Tabs.Trigger>
					<Tabs.Trigger value="list">List</Tabs.Trigger>
					<Tabs.Trigger value="schedule">Schedule</Tabs.Trigger>
				</Tabs.List>
				<!-- search, order and filters for the whole board; each status adds its own under its title -->
				{#if tab === 'board'}
					<div class="ms-auto"><BoardToolbar {view} {defs} /></div>
				{/if}
			</div>
			<Tabs.Content value="board" class="min-h-0 flex-1">
				<Board {tasks} {defs} {now} {view} onopen={openTask} onadd={addTask} onmove={move} />
			</Tabs.Content>
			<Tabs.Content value="list">
				<TaskList {tasks} {defs} {now} onopen={openTask} />
			</Tabs.Content>
			<Tabs.Content value="schedule">
				<ScheduleTimeline projectId={id} {now} timezone={system?.timezone ?? 'UTC'} {revision} />
			</Tabs.Content>
		</Tabs.Root>
	</div>

	<TaskSheet
		bind:open={sheetOpen}
		projectId={id}
		task={sheetTask}
		defaultStatus={sheetStatus}
		{defs}
		timezone={system?.timezone ?? 'UTC'}
		{now}
		onchange={reload}
	/>
	<PropertiesDialog bind:open={propsOpen} projectId={id} {defs} onsaved={reload} />
	<ProjectDialog bind:open={editOpen} {project} onsaved={reload} />

	<AlertDialog.Root bind:open={deleteOpen}>
		<AlertDialog.Content>
			<AlertDialog.Header>
				<AlertDialog.Title>Delete "{project.name}"?</AlertDialog.Title>
				<AlertDialog.Description>
					All of its tasks and their history are removed permanently. Files in the project workspace on disk are kept.
				</AlertDialog.Description>
			</AlertDialog.Header>
			{#if deleteError}<p class="text-sm text-destructive" role="alert">{deleteError}</p>{/if}
			<AlertDialog.Footer>
				<AlertDialog.Cancel>Keep it</AlertDialog.Cancel>
				<AlertDialog.Action onclick={(e) => (e.preventDefault(), deleteProject())}>Delete project</AlertDialog.Action>
			</AlertDialog.Footer>
		</AlertDialog.Content>
	</AlertDialog.Root>
{:else if loadError}
	<p class="m-auto text-sm text-destructive">{loadError}</p>
{/if}
