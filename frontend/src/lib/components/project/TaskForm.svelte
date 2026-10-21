<script lang="ts" module>
	/** the id of the form, so the Save button in the panel's top bar can submit it */
	export const TASK_FORM_ID = 'task-form'
</script>

<script lang="ts">
	import { agentsApi, type Agent } from '$lib/api/agents'
	import { ApiError } from '$lib/api/core'
	import type { Board } from '$lib/api/projects'
	import { tasksApi, type Harness, type PropertyDef, type PropertyValue, type ScheduleKind, type Task, type TaskPatch, type TaskStatus } from '$lib/api/tasks'
	import { workflowsApi, type WorkflowSummary } from '$lib/api/workflows'
	import { Button } from '$lib/components/ui/button/index.js'
	import { Input } from '$lib/components/ui/input/index.js'
	import { Label } from '$lib/components/ui/label/index.js'
	import * as Select from '$lib/components/ui/select/index.js'
	import * as Tabs from '$lib/components/ui/tabs/index.js'
	import { Switch } from '$lib/components/ui/switch/index.js'
	import { Textarea } from '$lib/components/ui/textarea/index.js'
	import GuardFields from '$lib/components/GuardFields.svelte'
	import { fromLocalInput, toLocalInput } from '$lib/format'
	import { MINUTE_INTERVALS, REPEAT_KINDS, WEEKDAYS, defaultRecurrence, describeRecurrence, describeSchedule, fromCron, toCron, type RepeatKind, type Recurrence } from '$lib/recurrence'
	import { cn } from '$lib/utils'
	import ArrowDownIcon from '@lucide/svelte/icons/arrow-down'
	import ArrowRightIcon from '@lucide/svelte/icons/arrow-right'
	import ArrowUpIcon from '@lucide/svelte/icons/arrow-up'
	import PlusIcon from '@lucide/svelte/icons/plus'
	import XIcon from '@lucide/svelte/icons/x'
	import { onMount, untrack } from 'svelte'
	import { slide } from 'svelte/transition'

	let {
		projectId,
		task,
		board,
		status,
		defs,
		timezone,
		saving = $bindable(false),
		canSave = $bindable(false),
		dirty = $bindable(false),
		title = $bindable(''),
		onsaved,
		onopenworkflow,
	}: {
		projectId: number
		task: Task | null
		/** the board a new task is created on */
		board: Board
		/** the status a new task starts in (the taskbar of the panel sets it; an existing task's status is not edited here) */
		status: TaskStatus
		defs: PropertyDef[]
		timezone: string
		/** the Save and Cancel buttons live in the panel's top bar (they submit this form by its id), so it reports their state */
		saving?: boolean
		canSave?: boolean
		/** something was changed and not saved yet: the panel asks before it closes on it */
		dirty?: boolean
		/** edited in the panel's title card, outside this form, and saved with the rest of it */
		title?: string
		onsaved: (task: Task) => void
		/** leaves for the editor of a workflow this task plays (the panel asks about unsaved changes first) */
		onopenworkflow: (workflowId: number) => void
	} = $props()

	const MAX_STAGES = 20 // the same limit as the server's

	// Initial values only: live updates of the task never overwrite what is being typed.
	const initial = untrack(() => ({
		description: task?.description ?? '',
		kind: (task?.schedule_kind ?? 'none') as ScheduleKind,
		cron: task?.cron ?? '',
		runAt: toLocalInput(task?.run_at ?? null),
		review: task?.review_on_success ?? false,
		runWith: task?.agent_id ? `agent:${task.agent_id}` : (task?.harness ?? ''),
		workflowIds: (task?.stages ?? []).map((s) => String(s.workflow_id)),
		properties: { ...(task?.properties ?? {}) } as Record<string, PropertyValue>,
		cooldown: task?.cooldown_seconds ?? null,
		hops: task?.max_hops ?? null,
	}))

	// the title lives in the card above the tabs, which shows what this form holds: it starts as the task's own
	title = untrack(() => task?.title ?? '')
	let description = $state(initial.description)
	let kind = $state<ScheduleKind>(initial.kind)
	// The repeat rule is edited as a sentence ("every weekday at 09:00"). A task whose stored schedule cannot be
	// expressed that way keeps it untouched until a new repeat is chosen (repeat stays null).
	let repeat = $state<Recurrence | null>(initial.cron ? fromCron(initial.cron) : defaultRecurrence('day'))
	const advanced = initial.cron !== '' && fromCron(initial.cron) === null
	const cron = $derived(repeat ? toCron(repeat) : initial.cron)
	const timeOf = (r: Recurrence | null) => (r && 'time' in r ? r.time : '09:00')

	function chooseRepeat(id: string) {
		if (id === 'advanced') return void (repeat = null)
		const next = defaultRecurrence(id as RepeatKind)
		repeat = 'time' in next ? { ...next, time: timeOf(repeat) } : next
	}
	function toggleDay(n: number) {
		if (repeat?.every !== 'week') return
		const has = repeat.days.includes(n)
		if (has && repeat.days.length === 1) return // a weekly task needs at least one day
		repeat = { ...repeat, days: has ? repeat.days.filter((d) => d !== n) : [...repeat.days, n] }
	}
	let runAt = $state(initial.runAt)
	let cooldown = $state<number | null>(initial.cooldown)
	let hops = $state<number | null>(initial.hops)
	let review = $state(initial.review)
	// "Run with" is one choice: a kind of run, or one of the project's agents
	let runWith = $state<string>(initial.runWith)
	const harness = $derived<Harness>(runWith.startsWith('agent:') ? 'codex' : (runWith as Harness))
	const agentId = $derived(runWith.startsWith('agent:') ? Number(runWith.slice(6)) : null)
	let agents = $state<Agent[]>([])
	const chosenAgent = $derived(agents.find((a) => a.id === agentId))
	// The workflows this task plays, in order; '' is a row that has none chosen yet.
	let workflowIds = $state<string[]>(initial.workflowIds.length ? initial.workflowIds : [''])
	let workflows = $state<WorkflowSummary[]>([])
	const harnessLabels: Record<Harness, string> = { '': 'Placeholder program', codex: 'Codex agent', workflow: 'Workflow' }
	const runLabel = $derived(agentId !== null ? (chosenAgent?.name ?? 'An agent that was deleted') : harnessLabels[harness])
	const pickedWorkflows = $derived(workflowIds.filter(Boolean).map(Number))
	const workflowName = (id: string) => workflows.find((w) => String(w.id) === id)?.name ?? (id ? 'Workflow' : 'Choose a workflow')
	function moveWorkflow(i: number, by: -1 | 1) {
		const j = i + by
		if (j < 0 || j >= workflowIds.length) return
		;[workflowIds[i], workflowIds[j]] = [workflowIds[j], workflowIds[i]]
	}

	onMount(async () => {
		try {
			;[workflows, agents] = await Promise.all([workflowsApi.workflows(projectId), agentsApi.agents(projectId)])
		} catch {
			// the list only fills the workflow picker; saving still reports a real problem
		}
	})
	let properties = $state<Record<string, PropertyValue>>(initial.properties)

	let error = $state('')
	// the two tabs of the form; a problem found on save in the other one switches to it
	let section = $state('general')

	const running = $derived(task?.status === 'running')
	$effect.pre(() => {
		canSave = !saving && !running && !!title.trim()
	})

	// What the form holds, to tell an edit from a form that was only looked at. Rows of the workflow picker without a
	// choice are not an edit.
	const snapshot = () =>
		JSON.stringify([title, description, kind, cron, runAt, review, runWith, workflowIds.filter(Boolean), properties, cooldown, hops])
	const pristine = untrack(snapshot)
	$effect.pre(() => {
		dirty = snapshot() !== pristine
	})
	const scheduleChanged = $derived(kind !== initial.kind || (kind === 'cron' && cron !== initial.cron) || (kind === 'once' && runAt !== initial.runAt))
	const kinds: { id: ScheduleKind; label: string }[] = [
		{ id: 'none', label: 'Manual' },
		{ id: 'once', label: 'Once' },
		{ id: 'cron', label: 'Recurring' },
	]

	function setProperty(key: string, value: PropertyValue | undefined) {
		if (value === undefined || value === '') delete properties[key]
		else properties[key] = value
	}

	/** Saves the task, as the Save button does. Whether it worked; if not, the form shows why. */
	export async function save(): Promise<boolean> {
		error = ''
		if (harness === 'workflow' && !pickedWorkflows.length) {
			error = 'Choose the workflow this task should play'
			return false
		}
		// not left to the browser: a field on the tab that is not showing cannot be focused to say what is wrong
		if (kind === 'once' && !runAt) {
			error = 'Choose when the task should run'
			section = 'rules'
			return false
		}
		if (kind === 'cron' && repeat && 'time' in repeat && !repeat.time) {
			error = 'Choose the time of day the task should run'
			section = 'rules'
			return false
		}
		saving = true
		try {
			const schedule = {
				schedule_kind: kind,
				cron: kind === 'cron' ? cron : null,
				run_at: kind === 'once' ? fromLocalInput(runAt) : null,
			}
			if (task === null) {
				onsaved(
					await tasksApi.createTask(projectId, {
						title,
						description,
						status,
						board_id: board.id,
						properties,
						review_on_success: review,
						harness,
						workflow_ids: harness === 'workflow' ? pickedWorkflows : [],
						agent_id: agentId,
						cooldown_seconds: cooldown,
						max_hops: hops,
						...schedule,
					})
				)
			} else {
				const patch: TaskPatch = {
					title,
					description,
					properties,
					review_on_success: review,
					harness,
					workflow_ids: harness === 'workflow' ? pickedWorkflows : [],
					agent_id: agentId,
					cooldown_seconds: cooldown,
					max_hops: hops,
				}
				if (scheduleChanged) Object.assign(patch, schedule)
				onsaved(await tasksApi.updateTask(task.id, patch))
			}
			return true
		} catch (err) {
			error = err instanceof ApiError || err instanceof Error ? err.message : 'Could not save the task'
			return false
		} finally {
			saving = false
		}
	}

	function submit(e: SubmitEvent) {
		e.preventDefault()
		void save()
	}
</script>

<form id={TASK_FORM_ID} onsubmit={submit} class="grid gap-5 px-4 pb-6">
	{#if error}
		<p class="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive" role="alert">{error}</p>
	{/if}

	<Tabs.Root bind:value={section} class="gap-5">
		<Tabs.List class="w-full">
			<Tabs.Trigger value="general">General</Tabs.Trigger>
			<Tabs.Trigger value="rules">Schedule & automation</Tabs.Trigger>
		</Tabs.List>
		<!-- what the task is: kept together on the first tab -->
		<Tabs.Content value="general" class="grid gap-5">
			<div class="grid gap-2">
				<Label for="task-desc">Description</Label>
				<Textarea id="task-desc" bind:value={description} rows={4} placeholder="Context, goal, acceptance criteria..." />
				{#if harness === 'workflow'}
					<p class="text-xs text-muted-foreground" transition:slide={{ duration: 160 }}>
						Given to every agent step of the workflows below as the task's brief. Write what this run should focus on; the workflows say how to work.
					</p>
				{/if}
			</div>

			<div class="grid gap-2">
				<Label for="task-harness">Run with</Label>
				<Select.Root type="single" bind:value={runWith}>
					<Select.Trigger id="task-harness" class="w-full">{runLabel}</Select.Trigger>
					<Select.Content>
						<Select.Item value="" label="Placeholder program">Placeholder program</Select.Item>
						<Select.Item value="codex" label="Codex agent">Codex agent</Select.Item>
						{#each agents as a (a.id)}
							<Select.Item value="agent:{a.id}" label={a.name}>{a.name}{a.role ? ` - ${a.role}` : ''}</Select.Item>
						{/each}
						<Select.Item value="workflow" label="Workflow">Workflow</Select.Item>
					</Select.Content>
				</Select.Root>
				{#if harness === 'workflow'}
					<div class="grid gap-1.5" transition:slide={{ duration: 160 }}>
						{#each workflowIds as _, i (i)}
							<div class="flex items-center gap-1">
								{#if workflowIds.length > 1}<span class="w-5 shrink-0 text-center text-xs text-muted-foreground">{i + 1}</span>{/if}
								<Select.Root type="single" bind:value={workflowIds[i]}>
									<Select.Trigger id={i === 0 ? 'task-workflow' : undefined} class="min-w-0 flex-1" aria-label="Workflow to play, stage {i + 1}">
										{workflowName(workflowIds[i])}
									</Select.Trigger>
									<Select.Content>
										{#each workflows as w (w.id)}<Select.Item value={String(w.id)} label={w.name}>{w.name}</Select.Item>{/each}
									</Select.Content>
								</Select.Root>
								{#if workflowIds[i]}
									<!-- a plain click goes through the panel (it asks about unsaved changes first); ctrl or cmd opens a tab -->
									<Button
										type="button"
										variant="ghost"
										size="icon-sm"
										class="text-muted-foreground"
										aria-label="Open {workflowName(workflowIds[i])} in the editor"
										title="Open in the workflow editor"
										href="/projects/{projectId}/workflows/{workflowIds[i]}"
										onclick={(e: MouseEvent) => {
											if (e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return
											e.preventDefault()
											onopenworkflow(Number(workflowIds[i]))
										}}><ArrowRightIcon /></Button
									>
								{/if}
								{#if workflowIds.length > 1}
									<Button type="button" variant="ghost" size="icon-sm" aria-label="Move up" disabled={i === 0} onclick={() => moveWorkflow(i, -1)}><ArrowUpIcon /></Button>
									<Button type="button" variant="ghost" size="icon-sm" aria-label="Move down" disabled={i === workflowIds.length - 1} onclick={() => moveWorkflow(i, 1)}><ArrowDownIcon /></Button>
									<Button type="button" variant="ghost" size="icon-sm" aria-label="Remove stage {i + 1}" onclick={() => workflowIds.splice(i, 1)}><XIcon /></Button>
								{/if}
							</div>
						{/each}
						{#if workflows.length === 0}
							<p class="text-xs text-muted-foreground">
								This project has no workflows yet. <a class="text-primary hover:underline" href="/projects/{projectId}/settings#workflows">Create one</a> in the project's Settings.
							</p>
						{:else if workflowIds.length < MAX_STAGES}
							<Button type="button" variant="ghost" size="sm" class="justify-self-start" onclick={() => workflowIds.push('')}><PlusIcon /> Add a stage</Button>
						{/if}
					</div>
				{/if}
				<p class="text-xs text-muted-foreground">
					{#if harness === 'workflow'}
						Plays the workflows one after the other instead of running a container: each is a stage, whose nodes run in order and can start other tasks. A stage that fails stops the ones after it.
					{:else if agentId !== null}
						{chosenAgent?.name ?? 'The agent'} does the task with its own instructions, model, cell and folders (set on the Agents page).
					{:else if harness === 'codex'}
						An agent works on the task in its own container, using the project owner's Codex connection (Settings). Its working folder is private to each run.
					{:else}
						Prints the task and finishes. Useful to try out scheduling.
					{/if}
				</p>
			</div>

			{#if defs.length}
				<fieldset class="grid gap-3 rounded-lg border p-3">
					<legend class="px-1 text-sm font-medium">Custom properties</legend>
					{#each defs as d (d.key)}
						{@const id = `prop-${d.key}`}
						<div class="grid gap-2">
							{#if d.type === 'checkbox'}
								<div class="flex items-center justify-between">
									<Label for={id}>{d.name}</Label>
									<Switch id={id} checked={properties[d.key] === true} onCheckedChange={(v) => setProperty(d.key, v ? true : undefined)} />
								</div>
							{:else if d.type === 'select'}
								<Label>{d.name}</Label>
								<Select.Root type="single" value={String(properties[d.key] ?? '')} onValueChange={(v) => setProperty(d.key, v || undefined)}>
									<Select.Trigger class="w-full">
										{#if properties[d.key] !== undefined && d.colors?.[String(properties[d.key])]}
											<span class="size-2.5 shrink-0 rounded-full ring-1 ring-foreground/20" style:background-color={d.colors[String(properties[d.key])]}></span>
										{/if}
										{properties[d.key] ?? 'None'}
									</Select.Trigger>
									<Select.Content>
										<Select.Item value="" label="None">None</Select.Item>
										{#each d.options as o (o)}
											<Select.Item value={o} label={o}>
												<span class="size-2.5 shrink-0 rounded-full ring-1 ring-foreground/20" style:background-color={d.colors?.[o] ?? 'transparent'}></span>
												{o}
											</Select.Item>
										{/each}
									</Select.Content>
								</Select.Root>
							{:else if d.type === 'number'}
								<Label for={id}>{d.name}</Label>
								<Input id={id} type="number" step="any" value={properties[d.key] ?? ''} oninput={(e) => setProperty(d.key, e.currentTarget.value === '' ? undefined : Number(e.currentTarget.value))} />
							{:else if d.type === 'date'}
								<Label for={id}>{d.name}</Label>
								<Input id={id} type="date" value={String(properties[d.key] ?? '')} oninput={(e) => setProperty(d.key, e.currentTarget.value || undefined)} />
							{:else}
								<Label for={id}>{d.name}</Label>
								<Input id={id} value={String(properties[d.key] ?? '')} oninput={(e) => setProperty(d.key, e.currentTarget.value || undefined)} />
							{/if}
						</div>
					{/each}
				</fieldset>
			{/if}
		</Tabs.Content>
		<!-- when and how it runs, and how much automation may touch it -->
		<Tabs.Content value="rules" class="grid gap-5">
			<div class="flex items-center justify-between gap-3 rounded-lg border p-3">
				<div>
					<Label for="task-review">Ask for review when it succeeds</Label>
					<p class="text-xs text-muted-foreground">One-off tasks go to Review instead of Done.</p>
				</div>
				<Switch id="task-review" bind:checked={review} />
			</div>

			<fieldset class="grid gap-3 rounded-lg border p-3">
				<legend class="px-1 text-sm font-medium">Schedule</legend>
				<div class="grid grid-cols-3 gap-1 rounded-lg bg-muted p-1" role="radiogroup" aria-label="Schedule type">
					{#each kinds as k (k.id)}
						<button
							type="button"
							role="radio"
							aria-checked={kind === k.id}
							class={cn(
								'rounded-md px-2 py-1 text-sm font-medium transition-colors',
								kind === k.id ? 'bg-background text-foreground shadow-sm' : 'text-muted-foreground hover:text-foreground'
							)}
							onclick={() => (kind = k.id)}>{k.label}</button
						>
					{/each}
				</div>

				{#if kind === 'none'}
					<p class="text-xs text-muted-foreground">Runs as soon as a cell is free once the task is Ready, or when you press Run now.</p>
				{:else if kind === 'once'}
					<div class="grid gap-2">
						<Label for="task-run-at">Run at</Label>
						<Input id="task-run-at" type="datetime-local" bind:value={runAt} />
						<p class="text-xs text-muted-foreground">Starts once it is Ready and this time has passed (your local time).</p>
					</div>
				{:else}
					<div class="grid gap-3">
						<div class="grid gap-2">
							<Label for="task-repeat">Repeat</Label>
							<Select.Root type="single" value={repeat?.every ?? 'advanced'} onValueChange={chooseRepeat}>
								<Select.Trigger id="task-repeat" class="w-full">
									{repeat ? REPEAT_KINDS.find((k) => k.id === repeat?.every)?.label : 'Keep the current schedule'}
								</Select.Trigger>
								<Select.Content>
									{#if advanced}<Select.Item value="advanced" label="Keep the current schedule">Keep the current schedule</Select.Item>{/if}
									{#each REPEAT_KINDS as k (k.id)}
										<Select.Item value={k.id} label={k.label}>{k.label}</Select.Item>
									{/each}
								</Select.Content>
							</Select.Root>
						</div>

						{#if repeat === null}
							<p class="rounded-md bg-muted px-3 py-2 text-xs text-muted-foreground">
								This task has a schedule that was set up another way ({describeSchedule(initial.cron)}). It keeps running as before. Choose a repeat above to replace it.
							</p>
						{:else}
							{#if repeat.every === 'minutes'}
								<div class="grid gap-2">
									<Label for="task-interval">Every</Label>
									<Select.Root type="single" value={String(repeat.interval)} onValueChange={(v) => (repeat = { every: 'minutes', interval: Number(v) })}>
										<Select.Trigger id="task-interval" class="w-full">{repeat.interval} minutes</Select.Trigger>
										<Select.Content>
											{#each MINUTE_INTERVALS as n (n)}<Select.Item value={String(n)} label={`${n} minutes`}>{n} minutes</Select.Item>{/each}
										</Select.Content>
									</Select.Root>
								</div>
							{:else if repeat.every === 'hour'}
								<div class="grid gap-2">
									<Label for="task-minute">Minutes past the hour</Label>
									<Input id="task-minute" type="number" min="0" max="59" value={repeat.minute} oninput={(e) => (repeat = { every: 'hour', minute: Math.min(59, Math.max(0, Number(e.currentTarget.value) || 0)) })} />
								</div>
							{:else}
								{#if repeat.every === 'week'}
									<div class="grid gap-2">
										<Label>On</Label>
										<div class="flex flex-wrap gap-1" role="group" aria-label="Days of the week">
											{#each WEEKDAYS as d (d.n)}
												<button
													type="button"
													aria-pressed={repeat.days.includes(d.n)}
													onclick={() => toggleDay(d.n)}
													class={cn(
														'rounded-md border px-2 py-1 text-sm transition-colors',
														repeat.days.includes(d.n) ? 'border-primary bg-primary/15 text-primary' : 'text-muted-foreground hover:text-foreground'
													)}>{d.short}</button
												>
											{/each}
										</div>
									</div>
								{:else if repeat.every === 'month'}
									<div class="grid gap-2">
										<Label for="task-day">On day of the month</Label>
										<Input id="task-day" type="number" min="1" max="28" value={repeat.day} oninput={(e) => repeat?.every === 'month' && (repeat = { ...repeat, day: Math.min(28, Math.max(1, Number(e.currentTarget.value) || 1)) })} />
										<p class="text-xs text-muted-foreground">Up to the 28th, so every month has that day.</p>
									</div>
								{/if}
								<div class="grid gap-2">
									<Label for="task-time">At</Label>
									<Input id="task-time" type="time" value={timeOf(repeat)} oninput={(e) => repeat && 'time' in repeat && (repeat = { ...repeat, time: e.currentTarget.value })} />
								</div>
							{/if}
							<p class="text-xs text-muted-foreground">
								{describeRecurrence(repeat)}, in the <span class="text-foreground">{timezone}</span> time zone (set in Settings). It runs every time while
								the task is Ready; move the task to Backlog to pause it.
							</p>
						{/if}
					</div>
				{/if}
			</fieldset>

			<details class="rounded-lg border p-3" open={initial.cooldown !== null || initial.hops !== null}>
				<summary class="cursor-pointer px-1 text-sm font-medium">Automation guard</summary>
				<p class="mt-2 mb-3 text-xs text-muted-foreground">
					Keeps workflows from moving this task around for ever. Leave a box empty to follow the project's values.
					{#if task && task.hops > 0}Workflows have handled this task {task.hops} {task.hops === 1 ? 'time' : 'times'} in a row.{/if}
				</p>
				<GuardFields bind:cooldown bind:hops prefix="task" fallback="the project" />
			</details>
		</Tabs.Content>
	</Tabs.Root>
</form>
