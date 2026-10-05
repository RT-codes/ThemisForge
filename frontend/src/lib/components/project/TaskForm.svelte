<script lang="ts">
	import { api, ApiError, type PropertyDef, type PropertyValue, type ScheduleKind, type Task, type TaskPatch, type TaskStatus } from '$lib/api'
	import { Button } from '$lib/components/ui/button/index.js'
	import { Input } from '$lib/components/ui/input/index.js'
	import { Label } from '$lib/components/ui/label/index.js'
	import * as Select from '$lib/components/ui/select/index.js'
	import { Switch } from '$lib/components/ui/switch/index.js'
	import { Textarea } from '$lib/components/ui/textarea/index.js'
	import { CRON_PRESETS, STATUSES, fromLocalInput, statusLabel, toLocalInput } from '$lib/format'
	import { cn } from '$lib/utils'
	import { untrack } from 'svelte'

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
		cron: task?.cron ?? '0 9 * * *',
		runAt: toLocalInput(task?.run_at ?? null),
		review: task?.review_on_success ?? false,
		properties: { ...(task?.properties ?? {}) } as Record<string, PropertyValue>,
	}))

	let title = $state(initial.title)
	let description = $state(initial.description)
	let status = $state<TaskStatus>(initial.status)
	let kind = $state<ScheduleKind>(initial.kind)
	let cron = $state(initial.cron)
	let runAt = $state(initial.runAt)
	let review = $state(initial.review)
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
	const presetValue = $derived(CRON_PRESETS.find((p) => p.cron === cron)?.cron ?? 'custom')

	function setProperty(key: string, value: PropertyValue | undefined) {
		if (value === undefined || value === '') delete properties[key]
		else properties[key] = value
	}

	async function save(e: SubmitEvent) {
		e.preventDefault()
		error = ''
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
						...schedule,
					})
				)
			} else {
				const patch: TaskPatch = { title, description, properties, review_on_success: review }
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
			<div class="grid gap-2">
				<Label>Repeat</Label>
				<Select.Root type="single" value={presetValue} onValueChange={(v) => v !== 'custom' && (cron = v)}>
					<Select.Trigger class="w-full">
						{CRON_PRESETS.find((p) => p.cron === cron)?.label ?? 'Custom cron'}
					</Select.Trigger>
					<Select.Content>
						{#each CRON_PRESETS as p (p.cron)}
							<Select.Item value={p.cron} label={p.label}>{p.label}</Select.Item>
						{/each}
						<Select.Item value="custom" label="Custom cron">Custom cron</Select.Item>
					</Select.Content>
				</Select.Root>
				<Input bind:value={cron} class="font-mono" aria-label="Cron expression" placeholder="0 9 * * 1-5" required />
				<p class="text-xs text-muted-foreground">
					minute hour day month weekday, evaluated in <span class="text-foreground">{timezone}</span>. The task runs on every
					occurrence while it is Ready; move it to Inbox to pause it.
				</p>
			</div>
		{/if}

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
							<Select.Trigger class="w-full">{properties[d.key] ?? 'None'}</Select.Trigger>
							<Select.Content>
								<Select.Item value="" label="None">None</Select.Item>
								{#each d.options as o (o)}
									<Select.Item value={o} label={o}>{o}</Select.Item>
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
