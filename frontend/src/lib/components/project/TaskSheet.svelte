<script lang="ts">
	import { api, ApiError, type Board, type PropertyDef, type Task, type TaskStatus, type Workspace } from '$lib/api'
	import { Button } from '$lib/components/ui/button/index.js'
	import XIcon from '@lucide/svelte/icons/x'
	import { fly } from 'svelte/transition'
	import * as Tabs from '$lib/components/ui/tabs/index.js'
	import StatusBadge from '$lib/components/StatusBadge.svelte'
	import { dateTime, relative } from '$lib/format'
	import PlayIcon from '@lucide/svelte/icons/play'
	import SquareIcon from '@lucide/svelte/icons/square'
	import Trash2Icon from '@lucide/svelte/icons/trash-2'
	import AttemptHistory from './AttemptHistory.svelte'
	import SendDialog from './SendDialog.svelte'
	import TaskForm, { TASK_FORM_ID } from './TaskForm.svelte'
	import TaskRouting from './TaskRouting.svelte'
	import TaskWorkflowRuns from './TaskWorkflowRuns.svelte'

	let {
		open = $bindable(false),
		projectId,
		task,
		board,
		tasks,
		workspaces,
		defaultStatus,
		defs,
		timezone,
		now,
		onchange,
		ondelete,
		onopen,
	}: {
		open: boolean
		projectId: number
		task: Task | null
		/** the board a new task is created on */
		board: Board
		/** the project's tasks and workspaces, for the links between tasks and the boards to send one to */
		tasks: Task[]
		workspaces: Workspace[]
		defaultStatus: TaskStatus
		defs: PropertyDef[]
		timezone: string
		now: number
		onchange: () => void
		/** asks the page to delete the task (it confirms first and refreshes the board) */
		ondelete: (task: Task) => void
		/** opens another task in this panel (a link between tasks) */
		onopen: (task: Task) => void
	} = $props()

	let sendMode = $state<'move' | 'spawn'>('move')
	let sendOpen = $state(false)

	let tab = $state('details')
	let error = $state('')
	let busy = $state(false)
	let formSaving = $state(false) // reported by the form: its buttons are in the top bar
	let formCanSave = $state(false)

	// a fresh form every time the sheet opens on a different task
	const formKey = $derived(task ? `task-${task.id}-${task.board_id}` : 'new')

	$effect(() => {
		if (open) {
			tab = 'details'
			error = ''
		}
	})

	/** Escape closes the panel, unless it is meant for a menu or a dialog that is open on top of it */
	function closeOnEscape(e: KeyboardEvent) {
		if (!open || e.key !== 'Escape' || e.defaultPrevented) return
		if (document.querySelector('[role="listbox"], [role="menu"], [role="dialog"], [role="alertdialog"]')) return
		open = false
	}

	async function act(fn: () => Promise<unknown>) {
		error = ''
		busy = true
		try {
			await fn()
			onchange()
		} catch (e) {
			error = e instanceof ApiError || e instanceof Error ? e.message : 'Something went wrong'
		} finally {
			busy = false
		}
	}
</script>

<!-- Not a modal: the board behind stays sharp and usable (clicking another card switches the panel to it). -->
<svelte:window onkeydown={closeOnEscape} />

{#if open}
	<aside
		aria-label={task ? 'Task details' : 'New task'}
		class="fixed inset-y-0 right-0 z-40 flex w-full flex-col overflow-y-auto border-l bg-popover text-sm text-popover-foreground shadow-float sm:max-w-xl"
		transition:fly={{ x: 48, duration: 160 }}
	>
		<!-- Save and Cancel stay at the top, in view however far the form is scrolled. History has nothing to save. -->
		<div class="sticky top-0 z-10 flex items-center justify-end gap-2 border-b bg-popover/95 px-4 py-2 backdrop-blur">
			{#if !task || tab === 'details'}
				<Button type="button" variant="ghost" size="sm" onclick={() => (open = false)}>Cancel</Button>
				<Button type="submit" form={TASK_FORM_ID} size="sm" disabled={!formCanSave}>{formSaving ? 'Saving...' : task ? 'Save changes' : 'Create task'}</Button>
			{/if}
			<Button variant="ghost" size="icon-sm" aria-label="Close" onclick={() => (open = false)}><XIcon /></Button>
		</div>
		<header class="flex flex-col gap-0.5 p-4 pb-3">
			<div class="flex items-center gap-2">
				<h2 class="truncate text-base font-medium text-foreground">{task ? task.title : 'New task'}</h2>
				{#if task}<StatusBadge status={task.status} {board} />{/if}
			</div>
			<p class="text-sm text-muted-foreground">
				{#if !task}
					Tasks are the unit of work. Schedule them, and cells run them around the clock.
				{:else if task.status === 'ready' && task.next_run_at}
					Runs {relative(task.next_run_at, now)} ({dateTime(task.next_run_at)})
				{:else if task.last_run_at}
					Last ran {relative(task.last_run_at, now)}
				{:else}
					Created {dateTime(task.created_at)}
				{/if}
			</p>
		</header>

		{#if task}
			<div class="flex items-center gap-2 px-4 pb-5">
				{#if task.status === 'running'}
					<Button size="sm" variant="secondary" disabled={busy} onclick={() => act(() => api.cancelTask(task!.id))}>
						<SquareIcon /> Cancel run
					</Button>
				{:else}
					<Button size="sm" disabled={busy} onclick={() => act(() => api.runTask(task!.id))}>
						<PlayIcon /> Run now
					</Button>
				{/if}
				<Button
					size="icon-sm"
					variant="ghost"
					class="ms-auto text-muted-foreground hover:text-destructive"
					aria-label="Delete task"
					title={task.status === 'running' ? 'Cancel the run before deleting' : 'Delete task'}
					disabled={busy || task.status === 'running'}
					onclick={() => ondelete(task!)}
				>
					<Trash2Icon />
				</Button>
			</div>
			<TaskRouting
				{task}
				{tasks}
				{workspaces}
				{busy}
				onsend={() => ((sendMode = 'move'), (sendOpen = true))}
				onfollowup={() => ((sendMode = 'spawn'), (sendOpen = true))}
				{onopen}
			/>
			{#if error}
				<p class="mx-4 mb-3 rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive" role="alert">{error}</p>
			{/if}

			<Tabs.Root bind:value={tab} class="gap-4">
				<Tabs.List class="mx-4">
					<Tabs.Trigger value="details">Details</Tabs.Trigger>
					<Tabs.Trigger value="history">History</Tabs.Trigger>
				</Tabs.List>
				<Tabs.Content value="details">
					{#key formKey}
						<TaskForm {projectId} {task} {board} {defaultStatus} {defs} {timezone} bind:saving={formSaving} bind:canSave={formCanSave} onsaved={() => (onchange(), (open = false))} />
					{/key}
				</Tabs.Content>
				<Tabs.Content value="history">
					<TaskWorkflowRuns taskId={task.id} projectId={task.project_id} taskStatus={task.status} />
					<AttemptHistory taskId={task.id} taskStatus={task.status} projectId={task.project_id} />
				</Tabs.Content>
			</Tabs.Root>
		{:else}
			{#key formKey}
				<TaskForm {projectId} task={null} {board} {defaultStatus} {defs} {timezone} bind:saving={formSaving} bind:canSave={formCanSave} onsaved={() => (onchange(), (open = false))} />
			{/key}
		{/if}
	</aside>
{/if}

{#if task}
	<SendDialog bind:open={sendOpen} mode={sendMode} {task} {workspaces} ondone={onchange} />
{/if}
