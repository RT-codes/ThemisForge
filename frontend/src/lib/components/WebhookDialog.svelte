<script lang="ts">
	import { api, ApiError, type Agent, type DeliveryResult, type Harness, type TaskStatus, type Webhook, type WebhookCreated, type WebhookDelivery, type WorkflowSummary, type Workspace } from '$lib/api'
	import { columnsOf, destinationLabel } from '$lib/boards'
	import { Button } from '$lib/components/ui/button/index.js'
	import * as Dialog from '$lib/components/ui/dialog/index.js'
	import { Input } from '$lib/components/ui/input/index.js'
	import { Label } from '$lib/components/ui/label/index.js'
	import * as Select from '$lib/components/ui/select/index.js'
	import { Switch } from '$lib/components/ui/switch/index.js'
	import * as Tabs from '$lib/components/ui/tabs/index.js'
	import { Textarea } from '$lib/components/ui/textarea/index.js'
	import { dateTime, relative } from '$lib/format'
	import { GITHUB_EXAMPLE, OUTCOMES, SAMPLE_MESSAGE, addressOf, toRows, toRules, type RuleRow } from '$lib/webhooks'
	import ArrowDownIcon from '@lucide/svelte/icons/arrow-down'
	import ArrowUpIcon from '@lucide/svelte/icons/arrow-up'
	import CheckIcon from '@lucide/svelte/icons/check'
	import CopyIcon from '@lucide/svelte/icons/copy'
	import PlusIcon from '@lucide/svelte/icons/plus'
	import RefreshCwIcon from '@lucide/svelte/icons/refresh-cw'
	import XIcon from '@lucide/svelte/icons/x'
	import { untrack } from 'svelte'

	// Makes a webhook or changes one. The sender of a message decides nothing but what the message says; everything about
	// the task that is made is chosen here: where it lands, what runs it, how the message becomes its title and text, and
	// which messages count at all. An existing webhook also shows what arrived and lets you send it a message yourself.
	let {
		open = $bindable(false),
		projectId,
		webhook,
		workspaces,
		onchanged,
	}: {
		open: boolean
		projectId: number
		/** null makes a new one */
		webhook: Webhook | null
		workspaces: Workspace[]
		onchanged: () => void
	} = $props()

	const MAX_STAGES = 20 // the same limit as the server's

	let name = $state('')
	let enabled = $state(true)
	let boardId = $state('')
	let status = $state<string>('backlog')
	let runWith = $state('')
	let workflowIds = $state<string[]>([''])
	let review = $state(false)
	let titleTemplate = $state('')
	let descriptionTemplate = $state('')
	let rules = $state<RuleRow[]>([])
	let agents = $state<Agent[]>([])
	let workflows = $state<WorkflowSummary[]>([])

	let tab = $state('setup')
	let error = $state('')
	let busy = $state(false)
	/** the whole address, known only right after it was made */
	let revealed = $state<WebhookCreated | null>(null)
	let copied = $state(false)
	let deliveries = $state<WebhookDelivery[]>([])
	let sample = $state(SAMPLE_MESSAGE)
	let sampleEvent = $state('test')
	let tried = $state<DeliveryResult | null>(null)
	let confirmDelete = $state(false)

	const boards = $derived(workspaces.flatMap((w) => w.boards))
	const board = $derived(boards.find((b) => String(b.id) === boardId) ?? null)
	// the scheduler is the only thing that starts a task, so Running is never where one lands
	const columns = $derived(board ? columnsOf(board).filter((c) => c.id !== 'running') : [])
	const harness = $derived<Harness>(runWith.startsWith('agent:') ? 'codex' : (runWith as Harness))
	const agentId = $derived(runWith.startsWith('agent:') ? Number(runWith.slice(6)) : null)
	const runLabel = $derived(
		agentId !== null ? (agents.find((a) => a.id === agentId)?.name ?? 'An agent that was deleted') : ({ '': 'Placeholder program', codex: 'Codex agent', workflow: 'Workflow' } as Record<Harness, string>)[harness],
	)
	const workflowName = (id: string) => workflows.find((w) => String(w.id) === id)?.name ?? (id ? 'Workflow' : 'Choose a workflow')

	function init() {
		const w = webhook
		name = w?.name ?? ''
		enabled = w?.enabled ?? true
		boardId = String(w?.board_id ?? boards[0]?.id ?? '')
		status = w?.status ?? 'backlog'
		runWith = w?.agent_id ? `agent:${w.agent_id}` : (w?.harness ?? '')
		workflowIds = w?.workflow_ids.length ? w.workflow_ids.map(String) : ['']
		review = w?.review_on_success ?? false
		titleTemplate = w?.title_template ?? ''
		descriptionTemplate = w?.description_template ?? ''
		rules = toRows(w?.rules ?? [])
		tab = 'setup'
		error = ''
		revealed = null
		tried = null
		deliveries = []
		sample = SAMPLE_MESSAGE
		api.agents(projectId).then((a) => (agents = a), () => {})
		api.workflows(projectId).then((w) => (workflows = w), () => {})
		if (w) loadDeliveries()
	}
	$effect(() => {
		if (open) untrack(init)
	})

	// a status belongs to its board: after another board is chosen, one it lacks falls back to the Backlog
	$effect(() => {
		if (board && !columns.some((c) => c.id === status)) status = 'backlog'
	})

	async function loadDeliveries() {
		if (!webhook) return
		try {
			deliveries = await api.webhookDeliveries(webhook.id)
		} catch {
			// the log is a help; the form works without it
		}
	}

	function moveWorkflow(i: number, by: -1 | 1) {
		const j = i + by
		if (j < 0 || j >= workflowIds.length) return
		;[workflowIds[i], workflowIds[j]] = [workflowIds[j], workflowIds[i]]
	}

	function useExample() {
		titleTemplate = GITHUB_EXAMPLE.title
		descriptionTemplate = GITHUB_EXAMPLE.description
		rules = toRows(GITHUB_EXAMPLE.rules)
	}

	async function submit(e: SubmitEvent) {
		e.preventDefault()
		if (!board) return
		busy = true
		error = ''
		const body = {
			name: name.trim(),
			enabled,
			board_id: board.id,
			status: status as TaskStatus,
			title_template: titleTemplate,
			description_template: descriptionTemplate,
			rules: toRules(rules),
			harness,
			agent_id: agentId,
			workflow_ids: harness === 'workflow' && agentId === null ? workflowIds.filter(Boolean).map(Number) : [],
			review_on_success: review,
		}
		try {
			if (webhook) {
				await api.updateWebhook(webhook.id, body)
				open = false
			} else {
				revealed = await api.createWebhook(projectId, body)
			}
			onchanged()
		} catch (err) {
			error = err instanceof ApiError || err instanceof Error ? err.message : 'That did not work'
		} finally {
			busy = false
		}
	}

	async function newSecret() {
		if (!webhook) return
		busy = true
		error = ''
		try {
			revealed = await api.newWebhookSecret(webhook.id)
			onchanged()
		} catch (err) {
			error = err instanceof ApiError || err instanceof Error ? err.message : 'Could not make a new address'
		} finally {
			busy = false
		}
	}

	async function copy(text: string) {
		try {
			await navigator.clipboard.writeText(text)
			copied = true
			setTimeout(() => (copied = false), 1800)
		} catch {
			// the address is on screen to select by hand
		}
	}

	async function remove() {
		if (!webhook) return
		busy = true
		try {
			await api.deleteWebhook(webhook.id)
			open = false
			onchanged()
		} catch (err) {
			error = err instanceof ApiError || err instanceof Error ? err.message : 'Could not delete the webhook'
		} finally {
			busy = false
			confirmDelete = false
		}
	}

	async function trySample() {
		if (!webhook) return
		busy = true
		error = ''
		tried = null
		try {
			tried = await api.testWebhook(webhook.id, { payload: sample, event: sampleEvent })
			onchanged()
			await loadDeliveries()
		} catch (err) {
			error = err instanceof ApiError || err instanceof Error ? err.message : 'That did not work'
		} finally {
			busy = false
		}
	}

	const tone = { good: 'bg-emerald-500/15 text-emerald-400', quiet: 'bg-muted text-muted-foreground', bad: 'bg-destructive/15 text-destructive' }
</script>

<Dialog.Root bind:open>
	<Dialog.Content class="max-h-[90vh] overflow-y-auto sm:max-w-2xl">
		{#if revealed}
			<Dialog.Header>
				<Dialog.Title>{webhook ? 'A new address' : 'Webhook made'}</Dialog.Title>
				<Dialog.Description>
					Give this address to whatever should send messages here (GitHub, a shop, a script). It is shown this once: only the end of it is kept. Anyone who has it can make tasks in this project, so treat it like a password.
				</Dialog.Description>
			</Dialog.Header>
			{@const address = addressOf(revealed.path, window.location.origin)}
			<div class="grid gap-2">
				<Label for="webhook-address">Address (POST)</Label>
				<div class="flex gap-2">
					<Input id="webhook-address" readonly value={address} class="font-mono text-xs" onfocus={(e) => e.currentTarget.select()} />
					<Button type="button" variant="outline" onclick={() => copy(address)}>
						{#if copied}<CheckIcon /> Copied{:else}<CopyIcon /> Copy{/if}
					</Button>
				</div>
				<p class="text-xs text-muted-foreground">
					Themis must be reachable from where the messages come from. On your own computer that needs a public address or a tunnel; the address above starts with the one this page was opened from.
				</p>
			</div>
			<Dialog.Footer>
				<Button
					type="button"
					onclick={() => {
						revealed = null
						open = false
					}}>Done</Button
				>
			</Dialog.Footer>
		{:else}
			<Dialog.Header>
				<Dialog.Title>{webhook ? webhook.name : 'New webhook'}</Dialog.Title>
				<Dialog.Description>
					An address other programs send messages to. Each message makes a task here, set up the way you choose below.
				</Dialog.Description>
			</Dialog.Header>

			<Tabs.Root bind:value={tab} class="gap-4" onValueChange={(v) => v === 'messages' && loadDeliveries()}>
				{#if webhook}
					<Tabs.List class="w-full">
						<Tabs.Trigger value="setup">Setup</Tabs.Trigger>
						<Tabs.Trigger value="messages">Messages{deliveries.length ? ` (${deliveries.length})` : ''}</Tabs.Trigger>
					</Tabs.List>
				{/if}

				<Tabs.Content value="setup">
					<form onsubmit={submit} class="grid gap-5">
						{#if webhook?.problem}
							<p class="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive" role="alert">Messages are refused right now: {webhook.problem}</p>
						{/if}

						<div class="grid gap-2">
							<Label for="webhook-name">Name</Label>
							<Input id="webhook-name" bind:value={name} required maxlength={60} placeholder="GitHub issues" />
						</div>

						<fieldset class="grid gap-3 rounded-lg border p-3">
							<legend class="px-1 text-sm font-medium">Where its tasks land</legend>
							<div class="grid gap-4 sm:grid-cols-2">
								<div class="grid gap-2">
									<Label>Board</Label>
									<Select.Root type="single" bind:value={boardId}>
										<Select.Trigger class="w-full">{board ? destinationLabel(workspaces, board) : 'Choose a board'}</Select.Trigger>
										<Select.Content>
											{#each boards as b (b.id)}
												<Select.Item value={String(b.id)} label={destinationLabel(workspaces, b)}>{destinationLabel(workspaces, b)}</Select.Item>
											{/each}
										</Select.Content>
									</Select.Root>
								</div>
								<div class="grid gap-2">
									<Label>Status</Label>
									<Select.Root type="single" bind:value={status}>
										<Select.Trigger class="w-full">{columns.find((c) => c.id === status)?.label ?? ''}</Select.Trigger>
										<Select.Content>
											{#each columns as c (c.id)}<Select.Item value={c.id} label={c.label}>{c.label}</Select.Item>{/each}
										</Select.Content>
									</Select.Root>
								</div>
							</div>
							<p class="text-xs text-muted-foreground">
								{#if status === 'ready'}
									Ready: the task starts as soon as there is room. Only choose this for messages you trust.
								{:else}
									The Backlog is the safe choice: the task waits until you move it on. Choose Ready to run every message at once, or a status of your own that a workflow watches.
								{/if}
							</p>
						</fieldset>

						<div class="grid gap-2">
							<Label for="webhook-run">Run with</Label>
							<Select.Root type="single" bind:value={runWith}>
								<Select.Trigger id="webhook-run" class="w-full">{runLabel}</Select.Trigger>
								<Select.Content>
									<Select.Item value="" label="Placeholder program">Placeholder program</Select.Item>
									<Select.Item value="codex" label="Codex agent">Codex agent</Select.Item>
									<Select.Item value="workflow" label="Workflow">Workflow</Select.Item>
									{#each agents as a (a.id)}<Select.Item value={`agent:${a.id}`} label={a.name}>{a.name}</Select.Item>{/each}
								</Select.Content>
							</Select.Root>
							{#if harness === 'workflow' && agentId === null}
								<div class="grid gap-2">
									{#each workflowIds as _, i (i)}
										<div class="flex items-center gap-1.5">
											<Select.Root type="single" bind:value={workflowIds[i]}>
												<Select.Trigger class="min-w-0 flex-1" aria-label="Workflow to play, stage {i + 1}">{workflowName(workflowIds[i])}</Select.Trigger>
												<Select.Content>
													{#each workflows as w (w.id)}<Select.Item value={String(w.id)} label={w.name}>{w.name}</Select.Item>{/each}
												</Select.Content>
											</Select.Root>
											{#if workflowIds.length > 1}
												<Button type="button" variant="ghost" size="icon-sm" aria-label="Move stage {i + 1} up" disabled={i === 0} onclick={() => moveWorkflow(i, -1)}><ArrowUpIcon /></Button>
												<Button type="button" variant="ghost" size="icon-sm" aria-label="Move stage {i + 1} down" disabled={i === workflowIds.length - 1} onclick={() => moveWorkflow(i, 1)}><ArrowDownIcon /></Button>
												<Button type="button" variant="ghost" size="icon-sm" aria-label="Remove stage {i + 1}" onclick={() => workflowIds.splice(i, 1)}><XIcon /></Button>
											{/if}
										</div>
									{/each}
									{#if workflows.length === 0}
										<p class="text-xs text-muted-foreground">This project has no workflows yet. Create one in the project's Settings.</p>
									{:else if workflowIds.length < MAX_STAGES}
										<Button type="button" variant="ghost" size="sm" class="justify-self-start" onclick={() => workflowIds.push('')}><PlusIcon /> Add a stage</Button>
									{/if}
								</div>
							{/if}
							<div class="flex items-center justify-between gap-3 pt-1">
								<Label for="webhook-review" class="font-normal">Hold finished tasks in Review</Label>
								<Switch id="webhook-review" bind:checked={review} />
							</div>
						</div>

						<fieldset class="grid gap-3 rounded-lg border p-3">
							<legend class="px-1 text-sm font-medium">What a message becomes</legend>
							<p class="text-xs text-muted-foreground">
								Put <code class="rounded bg-muted px-1">{'{{name}}'}</code> where a value of the message belongs, like <code class="rounded bg-muted px-1">{'{{issue.title}}'}</code> or <code class="rounded bg-muted px-1">{'{{items.0.name}}'}</code>. Left empty, the message's own <em>title</em> and <em>description</em> are used, else the whole message. <code class="rounded bg-muted px-1">{'{{_event}}'}</code> is what the sender called the event, <code class="rounded bg-muted px-1">{'{{_raw}}'}</code> the whole message.
							</p>
							<div class="grid gap-2">
								<Label for="webhook-title">Title</Label>
								<Input id="webhook-title" bind:value={titleTemplate} maxlength={200} placeholder={'{{title}}'} class="font-mono text-sm" />
							</div>
							<div class="grid gap-2">
								<Label for="webhook-description">Description</Label>
								<Textarea id="webhook-description" bind:value={descriptionTemplate} rows={4} maxlength={20000} placeholder={'{{description}}'} class="font-mono text-sm" />
							</div>
							<Button type="button" variant="ghost" size="sm" class="justify-self-start" onclick={useExample}>Fill in the GitHub issue example</Button>
						</fieldset>

						<fieldset class="grid gap-3 rounded-lg border p-3">
							<legend class="px-1 text-sm font-medium">Only when</legend>
							<p class="text-xs text-muted-foreground">
								A message makes a task only when every rule holds. Name a value and what it may be (several allowed, separated by commas); leave the values out to only ask that it is there. No rules: every message counts.
							</p>
							{#each rules as row, i (i)}
								<div class="flex items-center gap-1.5">
									<Input bind:value={row.path} aria-label="Rule {i + 1}: value" placeholder="action" class="min-w-0 flex-1 font-mono text-sm" maxlength={100} />
									<span class="text-xs text-muted-foreground">is</span>
									<Input bind:value={row.values} aria-label="Rule {i + 1}: allowed values" placeholder="opened, reopened" class="min-w-0 flex-1 text-sm" />
									<Button type="button" variant="ghost" size="icon-sm" aria-label="Remove rule {i + 1}" onclick={() => rules.splice(i, 1)}><XIcon /></Button>
								</div>
							{/each}
							{#if rules.length < 10}
								<Button type="button" variant="ghost" size="sm" class="justify-self-start" onclick={() => rules.push({ path: '', values: '' })}><PlusIcon /> Add a rule</Button>
							{/if}
						</fieldset>

						{#if webhook}
							<div class="flex flex-wrap items-center justify-between gap-3 rounded-lg border p-3">
								<div class="min-w-0">
									<p class="text-sm font-medium">Switched {enabled ? 'on' : 'off'}</p>
									<p class="text-xs text-muted-foreground">While it is off, messages are refused and nothing is made.</p>
								</div>
								<Switch bind:checked={enabled} aria-label="Webhook on" />
							</div>
							<div class="flex flex-wrap items-center justify-between gap-3 rounded-lg border p-3">
								<div class="min-w-0">
									<p class="text-sm font-medium">Address ending in <span class="font-mono">…{webhook.token_hint}</span></p>
									<p class="text-xs text-muted-foreground">Lost it, or shared it too widely? A new address ends the old one at once.</p>
								</div>
								<Button type="button" variant="outline" size="sm" disabled={busy} onclick={newSecret}><RefreshCwIcon /> New address</Button>
							</div>
						{/if}

						{#if error}<p class="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive" role="alert">{error}</p>{/if}
						<Dialog.Footer class="sm:justify-between">
							{#if webhook}
								<Button type="button" variant="ghost" class="text-destructive hover:text-destructive" onclick={() => (confirmDelete = true)}>Delete</Button>
							{:else}
								<span></span>
							{/if}
							<div class="flex gap-2">
								<Button type="button" variant="ghost" onclick={() => (open = false)}>Cancel</Button>
								<Button type="submit" disabled={busy || !board || !name.trim()}>{webhook ? 'Save' : 'Make the webhook'}</Button>
							</div>
						</Dialog.Footer>
					</form>
				</Tabs.Content>

				<Tabs.Content value="messages" class="grid gap-5">
					<div class="grid gap-2 rounded-lg border p-3">
						<Label for="webhook-sample">Try it with a message of your own</Label>
						<Textarea id="webhook-sample" bind:value={sample} rows={5} class="font-mono text-xs" />
						<div class="flex flex-wrap items-center gap-2">
							<Label for="webhook-event" class="text-xs font-normal text-muted-foreground">Event</Label>
							<Input id="webhook-event" bind:value={sampleEvent} class="h-8 w-32 text-xs" maxlength={60} />
							<Button type="button" size="sm" class="ms-auto" disabled={busy} onclick={trySample}>Send</Button>
						</div>
						<p class="text-xs text-muted-foreground">It goes the whole way, so it makes a real task. Paste a message from the log below to see what yours would do.</p>
						{#if tried}
							<p class="rounded-md px-3 py-2 text-sm {tone[OUTCOMES[tried.outcome].tone]}">
								{OUTCOMES[tried.outcome].label}{tried.detail ? `: ${tried.detail}` : ''}
							</p>
						{/if}
						{#if error}<p class="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive" role="alert">{error}</p>{/if}
					</div>

					<div class="grid gap-2">
						<div class="flex items-center justify-between">
							<h4 class="text-sm font-medium">What arrived</h4>
							<Button type="button" variant="ghost" size="sm" onclick={loadDeliveries}><RefreshCwIcon /> Refresh</Button>
						</div>
						{#if deliveries.length === 0}
							<p class="rounded-lg border border-dashed py-6 text-center text-sm text-muted-foreground">Nothing has arrived yet.</p>
						{:else}
							<ul class="divide-y rounded-lg border">
								{#each deliveries as d (d.id)}
									<li>
										<details class="group">
											<summary class="flex cursor-pointer list-none flex-wrap items-center gap-2 px-3 py-2 text-sm hover:bg-accent/40">
												<span class="rounded-full px-2 py-0.5 text-xs font-medium {tone[OUTCOMES[d.outcome].tone]}">{OUTCOMES[d.outcome].label}</span>
												{#if d.event}<span class="font-mono text-xs text-muted-foreground">{d.event}</span>{/if}
												<span class="min-w-0 flex-1 truncate text-xs text-muted-foreground">{d.detail}</span>
												<time class="text-xs text-muted-foreground" datetime={d.received_at} title={dateTime(d.received_at)}>{relative(d.received_at)}</time>
											</summary>
											<pre class="slim-scrollbar max-h-60 overflow-auto border-t bg-background/40 p-3 text-xs break-all whitespace-pre-wrap">{d.payload || '(empty)'}</pre>
											<div class="flex justify-end gap-2 px-3 pb-2">
												<Button type="button" variant="ghost" size="sm" onclick={() => ((sample = d.payload), (sampleEvent = d.event || 'test'))}>Use as the test message</Button>
											</div>
										</details>
									</li>
								{/each}
							</ul>
						{/if}
					</div>
				</Tabs.Content>
			</Tabs.Root>
		{/if}
	</Dialog.Content>
</Dialog.Root>

{#if webhook}
	<Dialog.Root bind:open={confirmDelete}>
		<Dialog.Content class="sm:max-w-md">
			<Dialog.Header>
				<Dialog.Title>Delete this webhook?</Dialog.Title>
				<Dialog.Description>Its address stops working at once. The tasks it made stay.</Dialog.Description>
			</Dialog.Header>
			<Dialog.Footer>
				<Button variant="ghost" onclick={() => (confirmDelete = false)}>Keep it</Button>
				<Button variant="destructive" disabled={busy} onclick={remove}>Delete</Button>
			</Dialog.Footer>
		</Dialog.Content>
	</Dialog.Root>
{/if}
