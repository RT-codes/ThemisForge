<script lang="ts">
	import { api, ApiError, type ConnectionLogin, type ConnectionProvider } from '$lib/api'
	import { METHOD_HINT, METHOD_LABEL } from '$lib/connections'
	import { dateTime } from '$lib/format'
	import { cn } from '$lib/utils'
	import { Button } from '$lib/components/ui/button/index.js'
	import * as Dialog from '$lib/components/ui/dialog/index.js'
	import { Input } from '$lib/components/ui/input/index.js'
	import { Label } from '$lib/components/ui/label/index.js'
	import ExternalLinkIcon from '@lucide/svelte/icons/external-link'
	import LoaderCircleIcon from '@lucide/svelte/icons/loader-circle'

	// Connect one service: paste a token, or sign in with a code. Both end in the same kind of connection.
	let {
		open = $bindable(false),
		provider,
		onconnected,
	}: { open: boolean; provider: ConnectionProvider | null; onconnected: () => void } = $props()

	let method = $state<'token' | 'oauth'>('token')
	let token = $state('')
	let login = $state<ConnectionLogin | null>(null)
	let error = $state('')
	let busy = $state(false)

	const waiting = $derived(login?.status === 'waiting' || login?.status === 'starting')
	const methods = $derived(provider?.methods ?? [])

	$effect(() => {
		if (open) {
			method = 'token'
			token = ''
			login = null
			error = ''
		}
	})

	// while a sign in is waiting for the person, ask how it is going
	$effect(() => {
		if (!open || !provider || !waiting) return
		const id = provider.id
		const timer = setInterval(async () => {
			if (document.hidden) return
			try {
				login = await api.connectionLogin(id)
			} catch {
				return // a hiccup: ask again on the next beat
			}
			if (login?.status === 'connected') {
				onconnected()
				open = false
			}
		}, 2000)
		return () => clearInterval(timer)
	})

	function message(e: unknown, fallback: string) {
		return e instanceof ApiError || e instanceof Error ? e.message : fallback
	}

	async function connectWithToken(e: SubmitEvent) {
		e.preventDefault()
		if (!provider) return
		error = ''
		busy = true
		try {
			await api.connectWithToken(provider.id, token)
			token = ''
			onconnected()
			open = false
		} catch (err) {
			error = message(err, 'Could not connect')
		} finally {
			busy = false
		}
	}

	async function startSignIn() {
		if (!provider) return
		error = ''
		busy = true
		try {
			login = await api.startConnectionLogin(provider.id)
		} catch (err) {
			error = message(err, 'Could not start the sign in')
		} finally {
			busy = false
		}
	}

	async function cancelSignIn() {
		if (!provider) return
		await api.cancelConnectionLogin(provider.id).catch(() => {})
		login = null
	}

	// leaving the dialog also ends a sign in that is still waiting
	$effect(() => {
		if (!open && waiting) void cancelSignIn()
	})
</script>

<Dialog.Root bind:open>
	<Dialog.Content class="sm:max-w-lg">
		{#if provider}
			<Dialog.Header>
				<Dialog.Title>Connect {provider.name}</Dialog.Title>
				<Dialog.Description>{provider.description}</Dialog.Description>
			</Dialog.Header>

			{#if methods.length > 1}
				<div class="grid gap-2" role="radiogroup" aria-label="How to connect">
					{#each methods as m (m.id)}
						<button
							type="button"
							role="radio"
							aria-checked={method === m.id}
							disabled={!m.available || waiting}
							onclick={() => (method = m.id)}
							class={cn(
								'rounded-lg border px-3 py-2.5 text-start transition-colors disabled:opacity-60',
								method === m.id ? 'border-primary bg-primary/5' : 'hover:bg-accent/30',
							)}
						>
							<span class="block text-sm font-medium">{METHOD_LABEL[m.id]}</span>
							<span class="block text-xs text-muted-foreground">{m.available ? METHOD_HINT[m.id] : m.reason}</span>
						</button>
					{/each}
				</div>
			{/if}

			{#if method === 'token'}
				<form onsubmit={connectWithToken} class="grid gap-3">
					<div class="grid gap-2">
						<Label for="connection-token">Token</Label>
						<Input id="connection-token" type="password" autocomplete="off" bind:value={token} required placeholder="Paste the token here" />
						{#if provider.token_help}<p class="text-xs text-muted-foreground">{provider.token_help}</p>{/if}
					</div>
					{#if error}<p class="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive" role="alert">{error}</p>{/if}
					<Dialog.Footer>
						<Button type="button" variant="ghost" onclick={() => (open = false)}>Cancel</Button>
						<Button type="submit" disabled={busy || !token.trim()}>
							{#if busy}<LoaderCircleIcon class="animate-spin" />{/if}Connect
						</Button>
					</Dialog.Footer>
				</form>
			{:else}
				<div class="grid gap-3">
					{#if waiting && login}
						<div class="grid gap-3 rounded-lg border p-4">
							<p class="text-sm">
								<span class="font-medium">1.</span> Open
								<a class="inline-flex items-center gap-1 text-primary underline-offset-4 hover:underline" href={login.verification_url} target="_blank" rel="noreferrer noopener">
									{login.verification_url}<ExternalLinkIcon class="size-3.5" />
								</a>
								and sign in to {provider.name}.
							</p>
							<p class="text-sm"><span class="font-medium">2.</span> Enter this code:</p>
							<p class="select-all justify-self-start rounded-md bg-muted px-4 py-2 font-mono text-2xl tracking-widest" aria-label="Code">{login.code}</p>
							<p class="flex items-center gap-2 text-xs text-muted-foreground">
								<LoaderCircleIcon class="size-3.5 animate-spin" />
								Waiting for you to finish{login.expires_at ? ` (the code expires at ${dateTime(login.expires_at)})` : ''}. Only continue if you started this yourself.
							</p>
						</div>
					{:else if login?.status === 'failed'}
						<p class="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive" role="alert">{login.error}</p>
					{/if}
					{#if error}<p class="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive" role="alert">{error}</p>{/if}
					<Dialog.Footer>
						<Button type="button" variant="ghost" onclick={() => (open = false)}>{waiting ? 'Stop' : 'Cancel'}</Button>
						{#if !waiting}
							<Button type="button" disabled={busy} onclick={startSignIn}>
								{#if busy}<LoaderCircleIcon class="animate-spin" />{/if}Get a code
							</Button>
						{/if}
					</Dialog.Footer>
				</div>
			{/if}
		{/if}
	</Dialog.Content>
</Dialog.Root>
