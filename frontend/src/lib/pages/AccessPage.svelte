<script lang="ts">
	import { api, type AccessRequest, type Invite, type InviteCreated } from '$lib/api'
	import { auth } from '$lib/auth.svelte'
	import { Button } from '$lib/components/ui/button/index.js'
	import * as Card from '$lib/components/ui/card/index.js'
	import * as Dialog from '$lib/components/ui/dialog/index.js'
	import { Input } from '$lib/components/ui/input/index.js'
	import { Textarea } from '$lib/components/ui/textarea/index.js'
	import { dateTime, relative } from '$lib/format'
	import { inbox } from '$lib/inbox.svelte'
	import CheckIcon from '@lucide/svelte/icons/check'
	import CopyIcon from '@lucide/svelte/icons/copy'
	import { onMount } from 'svelte'

	let requests = $state<AccessRequest[]>([])
	let invites = $state<Invite[]>([])
	let loaded = $state(false)
	let error = $state('')
	let busyId = $state<number | null>(null)

	let inviteEmail = $state('')
	let inviteError = $state('')

	let created = $state<InviteCreated | null>(null)
	let linkOpen = $state(false)
	let copied = $state(false)
	let linkInput = $state<HTMLTextAreaElement | null>(null)

	const now = Date.now()
	const pending = $derived(requests.filter((r) => r.status === 'pending'))
	const handled = $derived(requests.filter((r) => r.status !== 'pending').slice(0, 10))
	const link = $derived(created ? `${window.location.origin}/invite/${created.token}` : '')

	async function load() {
		try {
			;[requests, invites] = await Promise.all([api.accessRequests(), api.invites()])
			inbox.refresh()
			error = ''
		} catch (e) {
			error = e instanceof Error ? e.message : 'Could not load'
		} finally {
			loaded = true
		}
	}
	onMount(() => {
		if (auth.user?.is_admin) load()
	})

	function showLink(invite: InviteCreated) {
		created = invite
		copied = false
		linkOpen = true
	}

	async function act(r: AccessRequest, fn: () => Promise<InviteCreated | AccessRequest>) {
		busyId = r.id
		error = ''
		try {
			const result = await fn()
			if ('token' in result) showLink(result)
			await load()
		} catch (e) {
			error = e instanceof Error ? e.message : 'Something went wrong'
			await load()
		} finally {
			busyId = null
		}
	}

	async function invite(e: SubmitEvent) {
		e.preventDefault()
		inviteError = ''
		try {
			showLink(await api.createInvite(inviteEmail))
			inviteEmail = ''
			await load()
		} catch (err) {
			inviteError = err instanceof Error ? err.message : 'Could not create the invite'
		}
	}

	async function revoke(i: Invite) {
		await api.revokeInvite(i.id)
		await load()
	}

	async function copy() {
		linkInput?.select()
		try {
			await navigator.clipboard.writeText(link)
			copied = true
		} catch {
			copied = false // not a secure context: the link is selected, Ctrl+C works
		}
	}
</script>

<div class="w-full max-w-3xl px-6 py-8">
	<h2 class="text-2xl font-semibold tracking-tight">Access</h2>
	<p class="text-sm text-muted-foreground">
		ThemisForge is invite only. People ask for access from the sign in screen, and you decide.
	</p>

	{#if !auth.user?.is_admin}
		<p class="mt-8 rounded-lg border border-dashed p-6 text-sm text-muted-foreground">Only administrators can manage access.</p>
	{:else}
		{#if error}<p class="mt-6 text-sm text-destructive" role="alert">{error}</p>{/if}

		<Card.Root class="mt-8">
			<Card.Header>
				<Card.Title>Requests {#if pending.length}<span class="ms-1 rounded-full bg-primary/15 px-2 text-xs text-primary">{pending.length}</span>{/if}</Card.Title>
				<Card.Description>Approving creates a personal link for you to send. It works once and expires after 7 days.</Card.Description>
			</Card.Header>
			<Card.Content class="grid gap-3">
				{#if !loaded}
					<div class="h-16"></div>
				{:else if pending.length === 0}
					<p class="rounded-lg border border-dashed py-8 text-center text-sm text-muted-foreground">No requests waiting.</p>
				{/if}
				{#each pending as r (r.id)}
					<div class="rounded-lg border p-3">
						<div class="flex flex-wrap items-baseline gap-x-2">
							<p class="font-medium">{r.name}</p>
							<p class="text-sm text-muted-foreground">{r.email}</p>
							<p class="ms-auto text-xs text-muted-foreground" title={dateTime(r.created_at)}>{relative(r.created_at, now)}</p>
						</div>
						<p class="mt-2 text-sm whitespace-pre-wrap">{r.reason}</p>
						<div class="mt-3 flex gap-2">
							<Button size="sm" disabled={busyId === r.id} onclick={() => act(r, () => api.approveRequest(r.id))}>Approve</Button>
							<Button size="sm" variant="ghost" disabled={busyId === r.id} onclick={() => act(r, () => api.denyRequest(r.id))}>Deny</Button>
						</div>
					</div>
				{/each}
			</Card.Content>
		</Card.Root>

		<Card.Root class="mt-6">
			<Card.Header>
				<Card.Title>Invite someone</Card.Title>
				<Card.Description>Skip the request: create a link for an email address yourself.</Card.Description>
			</Card.Header>
			<Card.Content class="grid gap-4">
				<form onsubmit={invite} class="flex gap-2">
					<Input type="email" bind:value={inviteEmail} placeholder="name@example.com" required aria-label="Email to invite" />
					<Button type="submit" variant="secondary">Create invite</Button>
				</form>
				{#if inviteError}<p class="text-sm text-destructive" role="alert">{inviteError}</p>{/if}

				{#if invites.length}
					<div>
						<h4 class="mb-2 text-xs font-medium tracking-wide text-muted-foreground uppercase">Open invites</h4>
						<ul class="divide-y rounded-lg border">
							{#each invites as i (i.id)}
								<li class="flex items-center gap-3 px-3 py-2.5 text-sm">
									<span class="min-w-0 truncate">{i.email}</span>
									<span class="ms-auto shrink-0 text-xs text-muted-foreground">expires {relative(i.expires_at, now)}</span>
									<Button size="sm" variant="ghost" onclick={() => revoke(i)}>Revoke</Button>
								</li>
							{/each}
						</ul>
						<p class="mt-2 text-xs text-muted-foreground">
							A link is only shown when it is created. If you lost it, create a new invite for the same address: it replaces the old one.
						</p>
					</div>
				{/if}
			</Card.Content>
		</Card.Root>

		{#if handled.length}
			<div class="mt-6">
				<h4 class="mb-2 text-xs font-medium tracking-wide text-muted-foreground uppercase">Earlier requests</h4>
				<ul class="divide-y rounded-lg border text-sm">
					{#each handled as r (r.id)}
						<li class="flex items-center gap-3 px-3 py-2">
							<span class="truncate">{r.name} <span class="text-muted-foreground">{r.email}</span></span>
							<span class="ms-auto shrink-0 text-xs {r.status === 'approved' ? 'text-emerald-400' : 'text-muted-foreground'}">{r.status}</span>
						</li>
					{/each}
				</ul>
			</div>
		{/if}
	{/if}
</div>

<Dialog.Root bind:open={linkOpen}>
	<Dialog.Content class="sm:max-w-lg">
		<Dialog.Header>
			<Dialog.Title>Invite link for {created?.email}</Dialog.Title>
			<Dialog.Description>
				Send this link to them yourself. It works once, expires {created ? relative(created.expires_at, now) : ''}, and will not be shown again.
			</Dialog.Description>
		</Dialog.Header>
		<Textarea bind:ref={linkInput} readonly rows={3} value={link} class="resize-none font-mono text-xs break-all" onfocus={(e) => e.currentTarget.select()} aria-label="Invite link" />
		<Dialog.Footer>
			<Button variant="ghost" onclick={() => (linkOpen = false)}>Done</Button>
			<Button type="button" onclick={copy}>
				{#if copied}<CheckIcon /> Copied{:else}<CopyIcon /> Copy link{/if}
			</Button>
		</Dialog.Footer>
	</Dialog.Content>
</Dialog.Root>
