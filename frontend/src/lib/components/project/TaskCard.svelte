<script lang="ts">
	import type { PropertyDef, Task } from '$lib/api'
	import { chipStyle } from '$lib/colors'
	import { attemptLabel, dateTime, relative } from '$lib/format'
	import { describeSchedule } from '$lib/recurrence'
	import { cn } from '$lib/utils'
	import BotIcon from '@lucide/svelte/icons/bot'
	import CircleCheckIcon from '@lucide/svelte/icons/circle-check'
	import CircleAlertIcon from '@lucide/svelte/icons/circle-alert'
	import ClockIcon from '@lucide/svelte/icons/clock'
	import GitBranchIcon from '@lucide/svelte/icons/git-branch'
	import LoaderCircleIcon from '@lucide/svelte/icons/loader-circle'
	import PencilIcon from '@lucide/svelte/icons/pencil'
	import RepeatIcon from '@lucide/svelte/icons/repeat'
	import Trash2Icon from '@lucide/svelte/icons/trash-2'
	import WorkflowIcon from '@lucide/svelte/icons/workflow'
	import TaskStageStrip from './TaskStageStrip.svelte'

	let {
		task,
		defs,
		now,
		dragging = false,
		selected = false,
		expanded = false,
		picked = false,
		onselect,
		onedit,
		onpick,
		ondelete,
		...rest
	}: {
		task: Task
		defs: PropertyDef[]
		now: number
		dragging?: boolean
		/** its details are open in the side panel */
		selected?: boolean
		/** selected on its own (a plain click): the card unfolds to show more of the task */
		expanded?: boolean
		/** part of the board's multiple selection (ctrl or cmd and click): these do not unfold */
		picked?: boolean
		/** a plain click: select it (or let go of it) */
		onselect: () => void
		/** the pencil: open its details in the side panel */
		onedit: () => void
		/** ctrl, cmd or shift and click: the event says which (add or take out one, or a range) */
		onpick: (e: MouseEvent | KeyboardEvent) => void
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
	// Unfolding and folding are animated: the card's height runs from what it was to what it is now, and the extra
	// information is uncovered as it grows (or covered as it shrinks). Only a change of `expanded` animates; the card
	// growing for any other reason (a stage moving on, a live update) just happens.
	let card: HTMLElement | undefined
	let heightBefore = 0
	let mounted = false
	$effect.pre(() => {
		void expanded // runs before the card is updated, when it still has its old height
		heightBefore = card?.offsetHeight ?? 0
	})
	$effect(() => {
		void expanded // runs after the card has been updated, which is when its new height is known
		if (!card) return
		if (!mounted) return void (mounted = true) // the first run is the card appearing, not unfolding
		const to = card.offsetHeight
		if (heightBefore === 0 || heightBefore === to || window.matchMedia('(prefers-reduced-motion: reduce)').matches) return
		card.style.overflow = 'hidden' // what is not yet uncovered must not show below the card
		const run = card.animate([{ height: `${heightBefore}px` }, { height: `${to}px` }], { duration: 200, easing: 'cubic-bezier(0.2, 0, 0, 1)' })
		run.finished.then(() => (card!.style.overflow = ''), () => (card!.style.overflow = ''))
	})
	const picking = (e: MouseEvent | KeyboardEvent) => e.ctrlKey || e.metaKey || e.shiftKey
	const runWithLabel = $derived(
		task.agent_id !== null ? 'An agent' : { '': 'Placeholder program', codex: 'Codex agent', workflow: 'Workflow' }[task.harness] ?? task.harness
	)
	const running = $derived(task.status === 'running')
	// a task that plays workflows says so with its stages below, so the badge is only for the ones without any
	const showHarness = $derived(task.harness === 'codex' || (task.harness === 'workflow' && task.stages.length === 0))
</script>

<div
	bind:this={card}
	role="button"
	tabindex="0"
	draggable={!running}
	onclick={(e) => (picking(e) ? onpick(e) : onselect())}
	onkeydown={(e) => (e.key === 'Enter' || e.key === ' ') && (e.preventDefault(), picking(e) ? onpick(e) : onselect())}
	class={cn(
		'group w-full cursor-pointer rounded-lg border bg-card p-3 text-start transition-colors select-none hover:border-primary/40 focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none',
		running && 'border-primary/40',
		dragging && 'opacity-40',
		selected && 'border-primary hover:border-primary',
		expanded && !selected && 'border-primary/70 shadow-sm hover:border-primary/70',
		// the ring is the selection, the border the card open in the panel: a card can be both
		picked && 'bg-primary/10 ring-2 ring-primary/70'
	)}
	{...rest}
>
	<div class="flex items-start gap-2">
		{#if picked}<CircleCheckIcon class="mt-0.5 size-4 shrink-0 text-primary" aria-label="Selected" />{/if}
		<p class="min-w-0 flex-1 text-sm leading-snug font-medium break-words">{task.title}</p>
		{#if task.origin_task_id !== null}
			<span title="A follow-up of another task (see its details)"><GitBranchIcon class="mt-0.5 size-3.5 shrink-0 text-muted-foreground" /></span>
		{/if}
		{#if running}
			<LoaderCircleIcon class="mt-0.5 size-4 shrink-0 animate-spin text-primary" />
		{:else if task.last_attempt_status === 'failed' && task.status !== 'failed'}
			<span title="The last attempt failed"><CircleAlertIcon class="mt-0.5 size-4 shrink-0 text-destructive" /></span>
		{/if}
		<!-- Opening the details is this button's job, so it is always reachable: on hover, when the card is selected, and
		     on touch screens, which have no hover. -->
		<button
			type="button"
			draggable="false"
			class={cn(
				'-m-1 shrink-0 rounded-md p-1 text-muted-foreground opacity-0 transition hover:bg-accent hover:text-foreground focus-visible:opacity-100 group-hover:opacity-100 [@media(hover:none)]:opacity-100',
				(expanded || selected) && 'opacity-100'
			)}
			aria-label="Edit task"
			title="Edit task"
			onclick={(e) => (e.stopPropagation(), onedit())}
			onkeydown={(e) => e.stopPropagation()}
		>
			<PencilIcon class="size-3.5" />
		</button>
		{#if !running}
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
		<!-- folded: two lines, so a board of cards stays easy to scan; selected: all of it -->
		<p class={cn('mt-1 text-xs text-muted-foreground', expanded ? 'whitespace-pre-wrap break-words' : 'line-clamp-2')}>{task.description}</p>
	{/if}

	{#if chips.length || showHarness}
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

	{#if expanded}
		<!-- what the board leaves out of a folded card: how it runs, when it last did and will, how it ended -->
		<dl class="mt-2 grid grid-cols-[auto_minmax(0,1fr)] gap-x-3 gap-y-0.5 border-t pt-2 text-xs">
			<dt class="text-muted-foreground">Run with</dt>
			<dd class="truncate">{runWithLabel}</dd>
			{#if task.last_run_at}
				<dt class="text-muted-foreground">Last ran</dt>
				<dd class="truncate" title={dateTime(task.last_run_at)}>{relative(task.last_run_at, now)}</dd>
			{/if}
			{#if task.last_attempt_status}
				<dt class="text-muted-foreground">Last attempt</dt>
				<dd class={cn('truncate', task.last_attempt_status === 'failed' && 'text-destructive')}>{attemptLabel[task.last_attempt_status]}</dd>
			{/if}
			<dt class="text-muted-foreground">Created</dt>
			<dd class="truncate">{dateTime(task.created_at)}</dd>
		</dl>
	{/if}

	{#if task.stages.length}
		<TaskStageStrip stages={task.stages} {expanded} />
	{/if}
</div>

