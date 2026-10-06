<script lang="ts">
	import { api, ApiError, type Agent, type Harness, type PropertyDef, type WorkflowSummary, type PropertyValue, type ScheduleKind, type Task, type TaskPatch, type TaskStatus } from '$lib/api'
	import { Button } from '$lib/components/ui/button/index.js'
	import { Input } from '$lib/components/ui/input/index.js'
	import { Label } from '$lib/components/ui/label/index.js'
	import * as Select from '$lib/components/ui/select/index.js'
	import { Switch } from '$lib/components/ui/switch/index.js'
	import { Textarea } from '$lib/components/ui/textarea/index.js'
	import { STATUSES, fromLocalInput, statusLabel, toLocalInput } from '$lib/format'
	import { MINUTE_INTERVALS, REPEAT_KINDS, WEEKDAYS, defaultRecurrence, describeRecurrence, describeSchedule, fromCron, toCron, type RepeatKind, type Recurrence } from '$lib/recurrence'
	import { cn } from '$lib/utils'
	import { onMount, untrack } from 'svelte'
	import { slide } from 'svelte/transition'

	let {
		projectId,
		task,
		defaultStatus,
		defs,
		timezone,
		onsaved,
		oncancel,
	}: {
		projectId: number
		task: Task | null
		defaultStatus: TaskStatus
		defs: PropertyDef[]
		timezone: string
		onsaved: (task: Task) => void
		oncancel: () => void
	} = $props()

	// Initial values only: live updates of the task never overwrite what is being typed.
	const initial = untrack(() => ({
		title: task?.title ?? '',
		description: task?.description ?? '',
		status: (task?.status ?? defaultStatus) as TaskStatus,
		kind: (task?.schedule_kind ?? 'none') as ScheduleKind,
		cron: task?.cron ?? '',
		runAt: toLocalInput(task?.run_at ?? null),
		review: task?.review_on_success ?? false,
		runWith: task?.agent_id ? `agent:${task.agent_id}` : (task?.harness ?? ''),
		workflowId: task?.workflow_id ? String(task.workflow_id) : '',
		properties: { ...(task?.properties ?? {}) } as Record<string, PropertyValue>,
	}))

	let title = $state(initial.title)
	let description = $state(initial.description)
	let status = $state<TaskStatus>(initial.status)
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
	let review = $state(initial.review)
	// "Run with" is one choice: a kind of run, or one of the project's agents
	let runWith = $state<string>(initial.runWith)
	const harness = $derived<Harness>(runWith.startsWith('agent:') ? 'codex' : (runWith as Harness))
	const agentId = $derived(runWith.startsWith('agent:') ? Number(runWith.slice(6)) : null)
	let agents = $state<Agent[]>([])
	const chosenAgent = $derived(agents.find((a) => a.id === agentId))
	let workflowId = $state(initial.workflowId)
	let workflows = $state<WorkflowSummary[]>([])
	const harnessLabels: Record<Harness, string> = { '': 'Placeholder program', codex: 'Codex agent', workflow: 'Workflow' }
	const runLabel = $derived(agentId !== null ? (chosenAgent?.name ?? 'An agent that was deleted') : harnessLabels[harness])
	const chosenWorkflow = $derived(workflows.find((w) => String(w.id) === workflowId))

	onMount(async () => {
		try {
			;[workflows, agents] = await Promise.all([api.workflows(projectId), api.agents(projectId)])
		} catch {
			// the list only fills the workflow picker; saving still reports a real problem
		}
	})
	let properties = $state<Record<string, PropertyValue>>(initial.properties)

	let saving = $state(false)
	let error = $state('')

	const running = $derived(task?.status === 'running')
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

	async function save(e: SubmitEvent) {
		e.preventDefault()
		error = ''
		if (harness === 'workflow' && !workflowId) {
			error = 'Choose the workflow this task should play'
			return
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
					await api.createTask(projectId, {
						title,
						description,
						status,
						properties,
						review_on_success: review,
						harness,
						workflow_id: harness === 'workflow' ? Number(workflowId) : null,
						agent_id: agentId,
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
					workflow_id: harness === 'workflow' ? Number(workflowId) : null,
					agent_id: agentId,
				}
				if (status !== task.status) patch.status = status
				if (scheduleChanged) Object.assign(patch, schedule)
				onsaved(await api.updateTask(task.id, patch))
			}
		} catch (err) {
			error = err instanceof ApiError || err instanceof Error ? err.message : 'Could not save the task'
		} finally {
			saving = false
		}
	}
</script>

<form onsubmit={save} class="grid gap-5 px-4">
	<div class="grid gap-2">
		<Label for="task-title">Title</Label>
		<Input id="task-title" bind:value={title} required maxlength={200} placeholder="What needs to be done?" autofocus />
	</div>

	<div class="grid gap-2">
		<Label for="task-desc">Description</Label>
		<Textarea id="task-desc" bind:value={description} rows={4} placeholder="Context, goal, acceptance criteria..." />
	</div>

	<div class="grid gap-2">
		<Label>Status</Label>
		<Select.Root type="single" bind:value={status} disabled={running}>
			<Select.Trigger class="w-full">{statusLabel(status)}</Select.Trigger>
			<Select.Content>
				{#each STATUSES.filter((s) => s.id !== 'running') as s (s.id)}
					<Select.Item value={s.id} label={s.label}>{s.label}</Select.Item>
				{/each}
			</Select.Content>
		</Select.Root>
		<p class="text-xs text-muted-foreground">
			{running ? 'A cell is working on this task. Cancel it to change the status.' : STATUSES.find((s) => s.id === status)?.hint}
		</p>
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
				<Input id="task-run-at" type="datetime-local" bind:value={runAt} required />
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
							<Input id="task-time" type="time" required value={timeOf(repeat)} oninput={(e) => repeat && 'time' in repeat && (repeat = { ...repeat, time: e.currentTarget.value })} />
						</div>
					{/if}
					<p class="text-xs text-muted-foreground">
						{describeRecurrence(repeat)}, in the <span class="text-foreground">{timezone}</span> time zone (set in Settings). It runs every time while
						the task is Ready; move the task to Inbox to pause it.
					</p>
				{/if}
			</div>
		{/if}

		<div class="grid gap-2 pt-1">
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
					<Select.Root type="single" bind:value={workflowId}>
						<Select.Trigger id="task-workflow" class="w-full" aria-label="Workflow to play">
							{chosenWorkflow?.name ?? (workflowId ? 'Workflow' : 'Choose a workflow')}
						</Select.Trigger>
						<Select.Content>
							{#each workflows as w (w.id)}<Select.Item value={String(w.id)} label={w.name}>{w.name}</Select.Item>{/each}
						</Select.Content>
					</Select.Root>
					{#if workflows.length === 0}
						<p class="text-xs text-muted-foreground">
							This project has no workflows yet. <a class="text-primary hover:underline" href="/projects/{projectId}#workflows">Create one</a> on the overview.
						</p>
					{/if}
				</div>
			{/if}
			<p class="text-xs text-muted-foreground">
				{#if harness === 'workflow'}
					Plays the workflow instead of running a container: its nodes run in order and can start other tasks. The attempt history links to the run.
				{:else if agentId !== null}
					{chosenAgent?.name ?? 'The agent'} does the task with its own instructions, model, cell and folders (set on the Agents page).
				{:else if harness === 'codex'}
					An agent works on the task in its own container, using the project owner's Codex connection (Settings). Its working folder is private to each run.
				{:else}
					Prints the task and finishes. Useful to try out scheduling.
				{/if}
			</p>
		</div>

		<div class="flex items-center justify-between gap-3 pt-1">
			<div>
				<Label for="task-review">Ask for review when it succeeds</Label>
				<p class="text-xs text-muted-foreground">One-off tasks go to Review instead of Done.</p>
			</div>
			<Switch id="task-review" bind:checked={review} />
		</div>
	</fieldset>

	{#if defs.length}
		<fieldset class="grid gap-3 rounded-lg border p-3">
			<legend class="px-1 text-sm font-medium">Properties</legend>
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

	{#if error}
		<p class="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive" role="alert">{error}</p>
	{/if}

	<div class="sticky bottom-0 -mx-4 flex justify-end gap-2 border-t bg-background/95 px-4 py-3 backdrop-blur">
		<Button type="button" variant="ghost" onclick={oncancel}>Cancel</Button>
		<Button type="submit" disabled={saving || running || !title.trim()}>{task ? 'Save changes' : 'Create task'}</Button>
	</div>
</form>
