<script lang="ts">
	import { api, ApiError, type Board, type PropertyDef, type Task, type TaskStatus, type Workspace } from '$lib/api'
	import { Button } from '$lib/components/ui/button/index.js'
	import XIcon from '@lucide/svelte/icons/x'
	import { fly } from 'svelte/transition'
	import * as Tabs from '$lib/components/ui/tabs/index.js'
	import { dateTime, relative } from '$lib/format'
	import PlayIcon from '@lucide/svelte/icons/play'
	import OctagonXIcon from '@lucide/svelte/icons/octagon-x'
	import Trash2Icon from '@lucide/svelte/icons/trash-2'
	import CopyIcon from '@lucide/svelte/icons/copy'
	import AttemptHistory from './AttemptHistory.svelte'
	import HistoryList from './HistoryList.svelte'
	import SendDialog from './SendDialog.svelte'
	import TaskForm, { TASK_FORM_ID } from './TaskForm.svelte'
	import TaskBar from './TaskBar.svelte'
	import TaskStages from './TaskStages.svelte'
	import TaskWorkflowRuns from './TaskWorkflowRuns.svelte'

	let {
		open = $bindable(false),
		dirty = $bindable(false),
		save = $bindable(null),
		projectId,
		task,
		board,
		tasks,
		workspaces,
		defaultStatus,
		defs,
		timezone,
		now,
		revision,
		onchange,
		ondelete,
		onduplicate,
		onopen,
		onopenworkflow,
	}: {
		open: boolean
		/** the form has changes that are not saved */
		dirty?: boolean
		/** saves the form, for whoever must get it saved before the panel goes away; whether it worked */
		save?: (() => Promise<boolean>) | null
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
		/** changes when the project was reloaded, so the task's activity refreshes */
		revision: number
		onchange: () => void
		/** asks the page to delete the task (it confirms first and refreshes the board) */
		ondelete: (task: Task) => void
		/** makes a copy of the task in the Backlog and opens it; rejects when that did not work */
		onduplicate: (task: Task) => Promise<void>
		/** opens another task in this panel (a link between tasks) */
		onopen: (task: Task) => void
		/** leaves for the editor of a workflow the task plays, at one of its nodes when `nodeId` is given */
		onopenworkflow: (workflowId: number, nodeId?: string) => void
	} = $props()

	let sendMode = $state<'move' | 'spawn'>('move')
	let sendOpen = $state(false)

	let tab = $state('details')
	let error = $state('')
	let busy = $state(false)
	let formSaving = $state(false) // reported by the form: its buttons are in the top bar
	let formCanSave = $state(false)
	let form = $state<TaskForm>()
	// the title is edited in the card at the top of the panel, but is part of the form (saved, and counted as a change)
	let title = $state('')
	let titleInput = $state<HTMLTextAreaElement>()
	$effect(() => {
		if (open && !task) titleInput?.focus() // a new task starts with the cursor in its title
	})
	// the status a new task starts in: chosen in the taskbar (an existing task's is changed there at once)
	let newStatus = $state<TaskStatus>('backlog')
	$effect(() => {
		if (open && !task) newStatus = defaultStatus
	})

	$effect(() => {
		save = form ? () => form!.save() : null
	})
	$effect(() => {
		if (!open) dirty = false // the form is gone with the panel, and so are its changes
	})

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

	async function duplicate() {
		error = ''
		busy = true
		try {
			await onduplicate(task!)
		} catch (e) {
			error = e instanceof ApiError || e instanceof Error ? e.message : 'Something went wrong'
		} finally {
			busy = false
		}
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
		data-task-panel
		aria-label={task ? 'Task details' : 'New task'}
		class="fixed inset-y-0 right-0 z-40 flex w-full flex-col overflow-y-auto border-l bg-popover text-sm text-popover-foreground shadow-float sm:max-w-xl"
		transition:fly={{ x: 48, duration: 160 }}
	>
		<!-- The bar stays at the top, in view however far the panel is scrolled: running the task on the left, with when it
		     last ran, and saving or leaving on the right. History has nothing to save. -->
		<div class="sticky top-0 z-10 flex items-center gap-2 border-b bg-popover/95 px-4 py-2 backdrop-blur">
			{#if task}
				{#if task.status === 'running'}
					<Button size="sm" variant="secondary" disabled={busy} onclick={() => act(() => api.cancelTask(task!.id))}>
						<OctagonXIcon /> Stop task
					</Button>
				{:else}
					<Button size="sm" disabled={busy} onclick={() => act(() => api.runTask(task!.id))}>
						<PlayIcon /> Run now
					</Button>
				{/if}
				<span class="min-w-0 truncate text-xs text-muted-foreground" title={task.last_run_at ? dateTime(task.last_run_at) : undefined}>
					{task.last_run_at ? `Last ran ${relative(task.last_run_at, now)}` : 'Never run'}
				</span>
			{/if}
			<div class="ms-auto flex shrink-0 items-center gap-2">
				{#if !task || tab === 'details'}
					<Button type="button" variant="ghost" size="sm" onclick={() => (open = false)}>Cancel</Button>
					<Button type="submit" form={TASK_FORM_ID} size="sm" disabled={!formCanSave}>{formSaving ? 'Saving...' : task ? 'Save changes' : 'Create task'}</Button>
				{/if}
				<Button variant="ghost" size="icon-sm" aria-label="Close" onclick={() => (open = false)}><XIcon /></Button>
			</div>
		</div>

		<!-- The title, in a card of its own: select it, change it, and save it with the rest of the form. -->
		<div class="mx-4 mt-4 mb-3 rounded-lg border bg-card/40 p-3">
			<div class="flex items-start gap-2">
				<!-- a text area that grows with the title, so a long one is read in full; it is still one line of text -->
				<textarea
					bind:this={titleInput}
					bind:value={title}
					rows={1}
					aria-label="Task title"
					placeholder="What needs to be done?"
					maxlength={200}
					readonly={task?.status === 'running'}
					class="field-sizing-content -mx-1.5 min-h-8 min-w-0 flex-1 resize-none rounded-md border border-transparent bg-transparent px-1.5 py-0.5 text-lg leading-snug font-semibold text-foreground outline-none transition-colors placeholder:font-normal placeholder:text-muted-foreground/60 hover:border-input focus:border-ring focus:bg-background/60"
					oninput={(e) => (title = e.currentTarget.value.replace(/\s*\n+\s*/g, ' '))}
					onkeydown={(e) => e.key === 'Enter' && (e.preventDefault(), formCanSave && form?.save())}
				></textarea>
				{#if task && !task.internal}
					<Button
						size="icon-sm"
						variant="ghost"
						class="shrink-0 text-muted-foreground"
						aria-label="Duplicate task"
						title="Duplicate task (the copy goes to the Backlog)"
						disabled={busy}
						onclick={duplicate}
					>
						<CopyIcon />
					</Button>
				{/if}
				{#if task}
					<Button
						size="icon-sm"
						variant="ghost"
						class="shrink-0 text-muted-foreground hover:text-destructive"
						aria-label="Delete task"
						title={task.status === 'running' ? 'Cancel the run before deleting' : 'Delete task'}
						disabled={busy || task.status === 'running'}
						onclick={() => ondelete(task!)}
					>
						<Trash2Icon />
					</Button>
				{/if}
			</div>
			<p class="mt-1 text-xs text-muted-foreground">
				{#if !task}
					Tasks are the unit of work. Schedule them, and cells run them around the clock.
				{:else if task.status === 'ready' && task.next_run_at}
					Runs {relative(task.next_run_at, now)} ({dateTime(task.next_run_at)})
				{:else}
					Created {dateTime(task.created_at)}
				{/if}
			</p>
		</div>

		{#if task}
			<Tabs.Root bind:value={tab} class="gap-0">
				<TaskBar
					{task}
					{board}
					{tasks}
					{workspaces}
					status={task.status}
					{busy}
					showTabs
					onstatus={(s) => act(() => api.updateTask(task!.id, { status: s }))}
					onsend={() => ((sendMode = 'move'), (sendOpen = true))}
					onfollowup={() => ((sendMode = 'spawn'), (sendOpen = true))}
					{onopen}
				/>
				<!-- above the tabs, so where the task is stays in view whichever tab is open -->
				{#if task.stages.length}
					<TaskStages stages={task.stages} projectId={task.project_id} {onopenworkflow} />
				{/if}
				{#if error}
					<p class="mx-4 mb-3 rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive" role="alert">{error}</p>
				{/if}
				<Tabs.Content value="details" class="mt-1">
					{#key formKey}
						<TaskForm bind:this={form} {projectId} {task} {board} status={newStatus} {defs} {timezone} bind:saving={formSaving} bind:canSave={formCanSave} bind:dirty bind:title {onopenworkflow} onsaved={() => (onchange(), (open = false))} />
					{/key}
				</Tabs.Content>
				<Tabs.Content value="history" class="mt-1">
					<TaskWorkflowRuns taskId={task.id} projectId={task.project_id} taskStatus={task.status} />
					<AttemptHistory taskId={task.id} taskStatus={task.status} projectId={task.project_id} />
					<h3 class="mx-4 mt-6 mb-2 text-sm font-medium">Activity</h3>
					<div class="mx-4 mb-6">
						<HistoryList projectId={task.project_id} scope={{ taskId: task.id }} {now} {revision} compact />
					</div>
				</Tabs.Content>
			</Tabs.Root>
		{:else}
			<TaskBar task={null} {board} {tasks} {workspaces} status={newStatus} busy={false} showTabs={false} onstatus={(s) => (newStatus = s)} onsend={() => {}} onfollowup={() => {}} {onopen} />
			{#key formKey}
				<TaskForm bind:this={form} {projectId} task={null} {board} status={newStatus} {defs} {timezone} bind:saving={formSaving} bind:canSave={formCanSave} bind:dirty bind:title {onopenworkflow} onsaved={() => (onchange(), (open = false))} />
			{/key}
		{/if}
	</aside>
{/if}

{#if task}
	<SendDialog bind:open={sendOpen} mode={sendMode} {task} {workspaces} ondone={onchange} />
{/if}
