<script lang="ts">
	import { cn } from '$lib/utils'
	import { api, ApiError, type CodexStatus } from '$lib/api'
	import { Button } from '$lib/components/ui/button/index.js'
	import * as Card from '$lib/components/ui/card/index.js'
	import { dateTime } from '$lib/format'
	import CircleCheckIcon from '@lucide/svelte/icons/circle-check'
	import ExternalLinkIcon from '@lucide/svelte/icons/external-link'
	import LoaderCircleIcon from '@lucide/svelte/icons/loader-circle'
	import { onMount } from 'svelte'

	// bare: just the connection itself, for use inside a section that already has a title
	let { class: className = '', bare = false }: { class?: string; bare?: boolean } = $props()

	let codex = $state<CodexStatus | null>(null)
	let error = $state('')
	let busy = $state(false)

	const login = $derived(codex?.login ?? null)
	const waiting = $derived(login?.status === 'waiting' || login?.status === 'starting')

	async function refresh() {
		try {
			codex = await api.codex()
		} catch (e) {
			error = e instanceof Error ? e.message : 'Could not load'
		}
	}

	onMount(() => {
		refresh()
		const timer = setInterval(() => waiting && !document.hidden && refresh(), 2000)
		return () => clearInterval(timer)
	})

	async function run(action: () => Promise<unknown>) {
		error = ''
		busy = true
		try {
			await action()
		} catch (e) {
			error = e instanceof ApiError || e instanceof Error ? e.message : 'Something went wrong'
		} finally {
			busy = false
			await refresh()
		}
	}
</script>

{#snippet body()}
		{#if !codex}
			{#if error}<p class="text-sm text-destructive" role="alert">{error}</p>{/if}
		{:else}
			{#if !codex.secret_key_secure}
				<p class="rounded-lg border border-yellow-500/30 bg-yellow-500/5 p-3 text-sm" role="alert">
					<span class="font-medium text-yellow-300">Set a real secret key first.</span>
					Your login is encrypted with <code>THEMIS_SECRET_KEY</code>, which is still the development default. Ask the administrator to set one (see Settings), then come back.
				</p>
			{:else if !codex.cli_installed}
				<p class="rounded-lg border border-yellow-500/30 bg-yellow-500/5 p-3 text-sm" role="alert">
					<span class="font-medium text-yellow-300">The Codex CLI was not found on the server.</span>
					Install it, or set <code>THEMIS_CODEX_BIN</code> to its location, then restart ThemisForge.
				</p>
			{/if}

			{#if waiting && login}
				<div class="grid gap-3 rounded-lg border p-4">
					<p class="text-sm">
						<span class="font-medium">1.</span> Open
						<a class="inline-flex items-center gap-1 text-primary underline-offset-4 hover:underline" href={login.verification_url} target="_blank" rel="noreferrer noopener">
							{login.verification_url}<ExternalLinkIcon class="size-3.5" />
						</a>
						and sign in with ChatGPT.
					</p>
					<p class="text-sm"><span class="font-medium">2.</span> Enter this one-time code:</p>
					<p class="select-all justify-self-start rounded-md bg-muted px-4 py-2 font-mono text-2xl tracking-widest" aria-label="One-time code">{login.code}</p>
					<p class="flex items-center gap-2 text-xs text-muted-foreground">
						<LoaderCircleIcon class="size-3.5 animate-spin" />
						Waiting for you to finish{login.expires_at ? ` (the code expires at ${dateTime(login.expires_at)})` : ''}. Only continue if you started this yourself.
					</p>
					<Button type="button" variant="ghost" class="justify-self-start" disabled={busy} onclick={() => run(api.codexCancelLogin)}>Cancel</Button>
				</div>
			{:else if codex.connected}
				<div class="flex items-center gap-3 rounded-lg border px-3 py-2.5">
					<CircleCheckIcon class="size-4 shrink-0 text-emerald-400" />
					<div class="min-w-0">
						<p class="truncate text-sm font-medium">Connected{codex.account ? ` as ${codex.account}` : ''}</p>
						<p class="text-xs text-muted-foreground">
							Since {dateTime(codex.connected_at ?? '')}{codex.refreshed_at ? ` · last refreshed ${dateTime(codex.refreshed_at)}` : ''}
						</p>
					</div>
					<Button type="button" variant="outline" class="ms-auto" disabled={busy} onclick={() => run(api.codexDisconnect)}>Disconnect</Button>
				</div>
				<p class="text-xs text-muted-foreground">
					Disconnecting removes the login from ThemisForge. To also revoke it at OpenAI, sign out of Codex in your ChatGPT security settings.
				</p>
			{:else}
				{#if codex.needs_reconnect}
					<p class="rounded-lg border border-yellow-500/30 bg-yellow-500/5 p-3 text-sm" role="alert">
						<span class="font-medium text-yellow-300">Reconnect needed.</span> The stored login can no longer be read (the secret key changed). Connect again.
					</p>
				{/if}
				{#if login?.status === 'failed'}
					<p class="text-sm text-destructive" role="alert">{login.error}</p>
				{/if}
				<Button type="button" class="justify-self-start" disabled={busy || !codex.secret_key_secure || !codex.cli_installed} onclick={() => run(api.codexStartLogin)}>
					{codex.needs_reconnect ? 'Reconnect Codex' : 'Connect Codex'}
				</Button>
			{/if}
			{#if error}<p class="text-sm text-destructive" role="alert">{error}</p>{/if}
		{/if}
{/snippet}

{#if bare}
	<div class={cn('grid gap-4', className)}>{@render body()}</div>
{:else}
<Card.Root class={cn(className)}>
	<Card.Header>
		<Card.Title>Codex</Card.Title>
		<Card.Description>
			Sign in with your ChatGPT account so tasks use your plan's Codex usage. You do this once: the login is kept, refreshed automatically and survives restarts and rebuilds.
		</Card.Description>
	</Card.Header>
	<Card.Content class="grid gap-4">{@render body()}</Card.Content>
</Card.Root>
{/if}
