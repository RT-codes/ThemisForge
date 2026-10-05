<script lang="ts">
	import { api, ApiError, type PropertyDef, type Task, type TaskStatus } from '$lib/api'
	import * as AlertDialog from '$lib/components/ui/alert-dialog/index.js'
	import { Button } from '$lib/components/ui/button/index.js'
	import * as Sheet from '$lib/components/ui/sheet/index.js'
	import * as Tabs from '$lib/components/ui/tabs/index.js'
	import StatusBadge from '$lib/components/StatusBadge.svelte'
	import { dateTime, relative } from '$lib/format'
	import PlayIcon from '@lucide/svelte/icons/play'
	import SquareIcon from '@lucide/svelte/icons/square'
	import Trash2Icon from '@lucide/svelte/icons/trash-2'
	import AttemptHistory from './AttemptHistory.svelte'
	import TaskForm from './TaskForm.svelte'

	let {
		open = $bindable(false),
		projectId,
		task,
		defaultStatus,
		defs,
		timezone,
		now,
		onchange,
	}: {
		open: boolean
		projectId: number
		task: Task | null
		defaultStatus: TaskStatus
		defs: PropertyDef[]
		timezone: string
		now: number
		onchange: () => void
	} = $props()

	let tab = $state('details')
	let error = $state('')
	let confirmDelete = $state(false)
	let busy = $state(false)

	// a fresh form every time the sheet opens on a different task
	const formKey = $derived(task ? `task-${task.id}` : 'new')

	$effect(() => {
		if (open) {
			tab = 'details'
			error = ''
		}
	})

	async function act(fn: () => Promise<unknown>, close = false) {
		error = ''
		busy = true
		try {
			await fn()
			onchange()
			if (close) open = false
		} catch (e) {
			error = e instanceof ApiError || e instanceof Error ? e.message : 'Something went wrong'
		} finally {
			busy = false
		}
	}
</script>

<Sheet.Root bind:open>
	<Sheet.Content side="right" class="w-full gap-0 overflow-y-auto sm:max-w-xl">
		<Sheet.Header class="pb-3">
			<div class="flex items-center gap-2 pe-8">
				<Sheet.Title class="truncate">{task ? task.title : 'New task'}</Sheet.Title>
				{#if task}<StatusBadge status={task.status} />{/if}
			</div>
			<Sheet.Description>
				{#if !task}
					Tasks are the unit of work. Schedule them, and cells run them around the clock.
				{:else if task.status === 'ready' && task.next_run_at}
					Runs {relative(task.next_run_at, now)} ({dateTime(task.next_run_at)})
				{:else if task.last_run_at}
					Last ran {relative(task.last_run_at, now)}
				{:else}
					Created {dateTime(task.created_at)}
				{/if}
			</Sheet.Description>
		</Sheet.Header>

		{#if task}
			<div class="flex flex-wrap gap-2 px-4 pb-4">
				{#if task.status === 'running'}
					<Button size="sm" variant="secondary" disabled={busy} onclick={() => act(() => api.cancelTask(task!.id))}>
						<SquareIcon /> Cancel run
					</Button>
				{:else}
					<Button size="sm" disabled={busy} onclick={() => act(() => api.runTask(task!.id))}>
						<PlayIcon /> Run now
					</Button>
				{/if}
				<Button size="sm" variant="ghost" class="ms-auto text-destructive hover:text-destructive" disabled={busy || task.status === 'running'} onclick={() => (confirmDelete = true)}>
					<Trash2Icon /> Delete
				</Button>
			</div>
			{#if error}
				<p class="mx-4 mb-3 rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive" role="alert">{error}</p>
			{/if}

			<Tabs.Root bind:value={tab} class="gap-3">
				<Tabs.List class="mx-4">
					<Tabs.Trigger value="details">Details</Tabs.Trigger>
					<Tabs.Trigger value="history">History</Tabs.Trigger>
				</Tabs.List>
				<Tabs.Content value="details">
					{#key formKey}
						<TaskForm {projectId} {task} {defaultStatus} {defs} {timezone} oncancel={() => (open = false)} onsaved={() => (onchange(), (open = false))} />
					{/key}
				</Tabs.Content>
				<Tabs.Content value="history">
					<AttemptHistory taskId={task.id} taskStatus={task.status} />
				</Tabs.Content>
			</Tabs.Root>
		{:else}
			{#key formKey}
				<TaskForm {projectId} task={null} {defaultStatus} {defs} {timezone} oncancel={() => (open = false)} onsaved={() => (onchange(), (open = false))} />
			{/key}
		{/if}
	</Sheet.Content>
</Sheet.Root>

<AlertDialog.Root bind:open={confirmDelete}>
	<AlertDialog.Content>
		<AlertDialog.Header>
			<AlertDialog.Title>Delete this task?</AlertDialog.Title>
			<AlertDialog.Description>
				"{task?.title}" and its attempt history will be removed permanently.
			</AlertDialog.Description>
		</AlertDialog.Header>
		<AlertDialog.Footer>
			<AlertDialog.Cancel>Keep it</AlertDialog.Cancel>
			<AlertDialog.Action onclick={() => task && act(() => api.deleteTask(task.id), true)}>Delete</AlertDialog.Action>
		</AlertDialog.Footer>
	</AlertDialog.Content>
</AlertDialog.Root>
