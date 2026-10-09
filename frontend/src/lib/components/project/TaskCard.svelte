<script lang="ts">
	import type { PropertyDef, Task } from '$lib/api'
	import { chipStyle } from '$lib/colors'
	import { dateTime, relative } from '$lib/format'
	import { describeSchedule } from '$lib/recurrence'
	import { cn } from '$lib/utils'
	import BotIcon from '@lucide/svelte/icons/bot'
	import CircleAlertIcon from '@lucide/svelte/icons/circle-alert'
	import ClockIcon from '@lucide/svelte/icons/clock'
	import LoaderCircleIcon from '@lucide/svelte/icons/loader-circle'
	import RepeatIcon from '@lucide/svelte/icons/repeat'
	import Trash2Icon from '@lucide/svelte/icons/trash-2'
	import WorkflowIcon from '@lucide/svelte/icons/workflow'

	let {
		task,
		defs,
		now,
		dragging = false,
		selected = false,
		onopen,
		ondelete,
		...rest
	}: {
		task: Task
		defs: PropertyDef[]
		now: number
		dragging?: boolean
		/** its details are open in the side panel */
		selected?: boolean
		onopen: () => void
		ondelete: () => void
		[key: string]: unknown
	} = $props()

	const chips = $derived(
		defs
			.filter((d) => task.properties[d.key] !== undefined)
			.map((d) => {
				const v = task.properties[d.key]
				return {
					key: d.key,
					text: d.type === 'checkbox' ? d.name : d.type === 'select' ? String(v) : `${d.name}: ${v}`,
					style: d.type === 'select' ? chipStyle(d.colors?.[String(v)]) : undefined,
				}
			})
	)
	const running = $derived(task.status === 'running')
</script>

<div
	role="button"
	tabindex="0"
	draggable={!running}
	onclick={onopen}
	onkeydown={(e) => (e.key === 'Enter' || e.key === ' ') && (e.preventDefault(), onopen())}
	class={cn(
		'group w-full cursor-pointer rounded-lg border bg-card p-3 text-start transition-colors select-none hover:border-primary/40 focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none',
		running && 'border-primary/40',
		dragging && 'opacity-40',
		selected && 'border-primary hover:border-primary'
	)}
	{...rest}
>
	<div class="flex items-start gap-2">
		<p class="min-w-0 flex-1 text-sm leading-snug font-medium break-words">{task.title}</p>
		{#if running}
			<LoaderCircleIcon class="mt-0.5 size-4 shrink-0 animate-spin text-primary" />
		{:else}
			{#if task.last_attempt_status === 'failed' && task.status !== 'failed'}
				<span title="The last attempt failed"><CircleAlertIcon class="mt-0.5 size-4 shrink-0 text-destructive" /></span>
			{/if}
			<!-- a running task cannot be deleted (cancel it first); on touch screens the details panel has the same button -->
			<button
				type="button"
				draggable="false"
				class="-m-1 shrink-0 rounded-md p-1 text-muted-foreground opacity-0 transition hover:bg-destructive/10 hover:text-destructive focus-visible:opacity-100 group-hover:opacity-100"
				aria-label="Delete task"
				title="Delete task"
				onclick={(e) => (e.stopPropagation(), ondelete())}
				onkeydown={(e) => e.stopPropagation()}
			>
				<Trash2Icon class="size-3.5" />
			</button>
		{/if}
	</div>

	{#if task.workflow_run}
		<p class="mt-2 inline-flex max-w-full items-center gap-1 rounded-md bg-primary/15 px-1.5 py-0.5 text-xs text-primary" title="A workflow started by this task is running">
			<LoaderCircleIcon class="size-3 shrink-0 animate-spin" />
			<span class="min-w-0 truncate">{task.workflow_run.workflow_name}{task.workflow_run.step ? ` · ${task.workflow_run.step}` : ''}</span>
		</p>
	{/if}

	{#if task.description}
		<p class="mt-1 line-clamp-2 text-xs text-muted-foreground">{task.description}</p>
	{/if}

	{#if chips.length || task.harness}
		<div class="mt-2 flex flex-wrap gap-1">
			{#if task.harness === 'workflow'}
				<span class="inline-flex items-center gap-1 rounded-md bg-primary/15 px-1.5 py-0.5 text-xs text-primary"><WorkflowIcon class="size-3" />Workflow</span>
			{:else if task.harness === 'codex'}
				<span class="inline-flex items-center gap-1 rounded-md bg-primary/15 px-1.5 py-0.5 text-xs text-primary"><BotIcon class="size-3" />Codex</span>
			{/if}
			{#each chips as chip (chip.key)}
				<span class="rounded-md border border-transparent bg-secondary px-1.5 py-0.5 text-xs text-secondary-foreground" style={chip.style}>{chip.text}</span>
			{/each}
		</div>
	{/if}

	{#if task.schedule_kind !== 'none'}
		<div class="mt-2 flex flex-wrap items-center gap-x-1.5 gap-y-0.5 text-xs text-muted-foreground">
			{#if task.schedule_kind === 'cron'}
				<RepeatIcon class="size-3 shrink-0" />
				<span class="min-w-0">{describeSchedule(task.cron)}</span>
			{:else}
				<ClockIcon class="size-3 shrink-0" />
				<span class="min-w-0">{task.run_at ? dateTime(task.run_at) : 'One-off'}</span>
			{/if}
			{#if task.next_run_at && task.status === 'ready'}
				<span class="ms-auto shrink-0 text-foreground/70">{relative(task.next_run_at, now)}</span>
			{:else if task.schedule_kind === 'cron' && task.status === 'backlog'}
				<span class="ms-auto shrink-0">paused</span>
			{/if}
		</div>
	{/if}
</div>
