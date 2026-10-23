<script lang="ts">
	import { ApiError } from '$lib/api/core'
	import { notificationsApi, type NotificationOptions, type NotificationTarget } from '$lib/api/notifications'
	import { Button } from '$lib/components/ui/button/index.js'
	import { Checkbox } from '$lib/components/ui/checkbox/index.js'
	import * as Dialog from '$lib/components/ui/dialog/index.js'
	import { Input } from '$lib/components/ui/input/index.js'
	import { Label } from '$lib/components/ui/label/index.js'
	import * as Select from '$lib/components/ui/select/index.js'
	import { Switch } from '$lib/components/ui/switch/index.js'
	import { relative } from '$lib/format'
	import BellIcon from '@lucide/svelte/icons/bell'
	import ChevronRightIcon from '@lucide/svelte/icons/chevron-right'
	import PlusIcon from '@lucide/svelte/icons/plus'
	import { onMount } from 'svelte'
	import { slide } from 'svelte/transition'

	// Where this project tells you that something happened (a task failed, something waits for you), so you do not have
	// to keep the app open. The services and the fields each needs come from the server (`options`), so the form below
	// is the same for all of them.
	let { projectId }: { projectId: number } = $props()

	let targets = $state<NotificationTarget[]>([])
	let options = $state<NotificationOptions>({ kinds: [], events: [] })
	let loaded = $state(false)
	let error = $state('')

	let open = $state(false)
	let editing = $state<NotificationTarget | null>(null)
	let name = $state('')
	let kindKey = $state('')
	let config = $state<Record<string, string>>({})
	let events = $state<string[]>([])
	let busy = $state(false)
	let formError = $state('')
	let tried = $state<{ ok: boolean; detail: string } | null>(null)
	let confirmDelete = $state(false)

	const kind = $derived(options.kinds.find((k) => k.key === kindKey))
	const labelOf = (key: string) => options.kinds.find((k) => k.key === key)?.label ?? key
	const fail = (e: unknown, fallback: string) => (e instanceof ApiError || e instanceof Error ? e.message : fallback)

	async function load() {
		try {
			;[targets, options] = await Promise.all([notificationsApi.notifications(projectId), notificationsApi.notificationOptions()])
			error = ''
		} catch (e) {
			error = fail(e, 'Could not load the notifications')
		} finally {
			loaded = true
		}
	}

	onMount(load)

	function openDialog(target: NotificationTarget | null) {
		editing = target
		name = target?.name ?? ''
		kindKey = target?.kind ?? options.kinds[0]?.key ?? ''
		config = {}
		// a new target starts with the two events that need you; "done" is chatty and opt in
		events = target ? [...target.events] : ['failed', 'attention']
		formError = ''
		tried = null
		open = true
	}

	async function save() {
		busy = true
		formError = ''
		try {
			if (editing) {
				// the stored secret cannot be shown, so it is replaced only when something was typed
				const typed = Object.values(config).some((v) => v.trim())
				await notificationsApi.updateNotification(editing.id, { name, events, ...(typed ? { config } : {}) })
			} else {
				await notificationsApi.createNotification(projectId, { name, kind: kindKey, config, events })
			}
			open = false
			await load()
		} catch (e) {
			formError = fail(e, 'That did not work')
		} finally {
			busy = false
		}
	}

	async function trySend() {
		if (!editing) return
		busy = true
		tried = null
		try {
			tried = await notificationsApi.testNotification(editing.id)
			await load()
		} catch (e) {
			formError = fail(e, 'That did not work')
		} finally {
			busy = false
		}
	}

	async function remove() {
		if (!editing) return
		busy = true
		try {
			await notificationsApi.deleteNotification(editing.id)
			open = false
			await load()
		} catch (e) {
			formError = fail(e, 'Could not delete it')
		} finally {
			busy = false
			confirmDelete = false
		}
	}

	async function toggle(target: NotificationTarget, enabled: boolean) {
		try {
			await notificationsApi.updateNotification(target.id, { enabled })
			await load()
		} catch (e) {
			error = fail(e, 'Could not change it')
		}
	}

	function toggleEvent(key: string, on: boolean) {
		events = on ? [...events, key] : events.filter((e) => e !== key)
	}

	function status(t: NotificationTarget): string {
		if (t.last_error) return `Last message failed: ${t.last_error}`
		return t.last_sent_at ? `last message ${relative(t.last_sent_at)}` : 'nothing sent yet'
	}
</script>

<section id="notifications" class="mt-6 scroll-mt-6 rounded-xl border bg-card">
	<div class="flex items-center gap-3 p-5 pb-3">
		<div class="min-w-0 flex-1">
			<h3 class="text-base font-semibold tracking-tight">Notifications</h3>
			<p class="text-sm text-muted-foreground">Get a message in a chat when a task fails or something waits for you.</p>
		</div>
		<Button size="sm" disabled={options.kinds.length === 0} onclick={() => openDialog(null)}><PlusIcon /> New</Button>
	</div>

	{#if error}<p class="px-5 pb-3 text-sm text-destructive" role="alert">{error}</p>{/if}

	{#if !loaded}
		<p class="px-5 pb-5 text-sm text-muted-foreground">Loading...</p>
	{:else if targets.length === 0}
		<div class="mx-5 mb-5 rounded-lg border border-dashed py-8 text-center">
			<p class="text-sm font-medium">Nothing connected yet</p>
			<p class="mt-1 text-xs text-muted-foreground">Connect a chat and Themis will tell you when work fails or needs you.</p>
		</div>
	{:else}
		<ul class="divide-y border-t">
			{#each targets as t (t.id)}
				<li class="flex items-center gap-3 px-5 py-3 transition-colors hover:bg-accent/40" transition:slide={{ duration: 200 }}>
					<button type="button" class="group flex min-w-0 flex-1 items-center gap-3 text-start" onclick={() => openDialog(t)}>
						<span class="flex size-8 shrink-0 items-center justify-center rounded-md bg-primary/15 text-primary"><BellIcon class="size-4" /></span>
						<span class="min-w-0 flex-1">
							<span class="block truncate text-sm font-medium">{t.name} <span class="font-normal text-muted-foreground">· {labelOf(t.kind)}</span></span>
							<span class={t.last_error ? 'block truncate text-xs text-destructive' : 'block truncate text-xs text-muted-foreground'}>{status(t)}</span>
						</span>
						<ChevronRightIcon class="size-4 shrink-0 text-muted-foreground/50 transition-transform group-hover:translate-x-0.5 group-hover:text-foreground" />
					</button>
					<Switch checked={t.enabled} onCheckedChange={(v) => toggle(t, v)} aria-label="{t.name} on" />
				</li>
			{/each}
		</ul>
	{/if}
</section>

<Dialog.Root bind:open>
	<Dialog.Content class="max-h-[90vh] overflow-y-auto sm:max-w-lg">
		<Dialog.Header>
			<Dialog.Title>{editing ? editing.name : 'New notification'}</Dialog.Title>
			<Dialog.Description>{kind?.description ?? 'Choose where Themis should send its messages.'}</Dialog.Description>
		</Dialog.Header>

		<form
			class="grid gap-4"
			onsubmit={(e) => {
				e.preventDefault()
				save()
			}}
		>
			<div class="grid gap-2">
				<Label for="notification-name">Name</Label>
				<Input id="notification-name" bind:value={name} maxlength={60} placeholder="My phone" required />
			</div>

			{#if !editing && options.kinds.length > 1}
				<div class="grid gap-2">
					<Label>Service</Label>
					<Select.Root type="single" bind:value={kindKey}>
						<Select.Trigger class="w-full">{kind?.label ?? ''}</Select.Trigger>
						<Select.Content>
							{#each options.kinds as k (k.key)}<Select.Item value={k.key} label={k.label}>{k.label}</Select.Item>{/each}
						</Select.Content>
					</Select.Root>
				</div>
			{/if}

			{#each kind?.fields ?? [] as f (f.name)}
				<div class="grid gap-2">
					<Label for="notification-{f.name}">{f.label}</Label>
					<!-- a password field: the value is a secret, and the stored one is never sent back to be shown -->
					<Input
						id="notification-{f.name}"
						type="password"
						autocomplete="off"
						bind:value={config[f.name]}
						placeholder={editing ? `Ends in ${editing.hint}. Type to replace it.` : f.placeholder}
						required={!editing}
					/>
					{#if f.help}<p class="text-xs text-muted-foreground">{f.help}</p>{/if}
				</div>
			{/each}

			<fieldset class="grid gap-2">
				<legend class="mb-1 text-sm font-medium">Tell me when</legend>
				{#each options.events as ev (ev.key)}
					<label class="flex items-center gap-2 text-sm">
						<Checkbox checked={events.includes(ev.key)} onCheckedChange={(on) => toggleEvent(ev.key, !!on)} />
						{ev.label}
					</label>
				{/each}
			</fieldset>

			{#if tried}
				<p class="rounded-md px-3 py-2 text-sm {tried.ok ? 'bg-tone-green/15 text-tone-green' : 'bg-destructive/15 text-destructive'}">
					{tried.ok ? 'Sent. Look in the chat.' : tried.detail}
				</p>
			{/if}
			{#if formError}<p class="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive" role="alert">{formError}</p>{/if}

			<Dialog.Footer class="gap-2 sm:justify-between">
				<div class="flex gap-2">
					{#if editing}
						<Button type="button" variant="ghost" class="text-destructive hover:text-destructive" onclick={() => (confirmDelete = true)}>Delete</Button>
						<Button type="button" variant="outline" disabled={busy} onclick={trySend}>Send a test</Button>
					{/if}
				</div>
				<Button type="submit" disabled={busy || !name.trim() || events.length === 0}>{editing ? 'Save' : 'Connect'}</Button>
			</Dialog.Footer>
		</form>
	</Dialog.Content>
</Dialog.Root>

<Dialog.Root bind:open={confirmDelete}>
	<Dialog.Content class="sm:max-w-md">
		<Dialog.Header>
			<Dialog.Title>Delete this notification?</Dialog.Title>
			<Dialog.Description>Themis stops sending messages there. The chat itself is untouched.</Dialog.Description>
		</Dialog.Header>
		<Dialog.Footer>
			<Button variant="ghost" onclick={() => (confirmDelete = false)}>Keep it</Button>
			<Button variant="destructive" disabled={busy} onclick={remove}>Delete</Button>
		</Dialog.Footer>
	</Dialog.Content>
</Dialog.Root>
