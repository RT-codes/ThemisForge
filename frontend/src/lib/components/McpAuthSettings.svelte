<script lang="ts">
	import { ApiError } from '$lib/api/core'
	import type { McpAuthPolicy } from '$lib/api/settings'
	import { toolsApi, type McpLogin } from '$lib/api/tools'
	import { Button } from '$lib/components/ui/button/index.js'
	import { Input } from '$lib/components/ui/input/index.js'
	import { Label } from '$lib/components/ui/label/index.js'
	import { relative } from '$lib/format'
	import GlobeIcon from '@lucide/svelte/icons/globe'
	import LogOutIcon from '@lucide/svelte/icons/log-out'
	import { onMount } from 'svelte'

	// The current user's sign ins to tool servers that ask for one (a tool is signed in to from its project's Tools
	// section; this is where they are all seen and forgotten), and for administrators the numbers signing in follows.
	// The numbers are saved with the Settings page's own save bar, so this edits them in place.
	let { policy = $bindable() }: { policy?: McpAuthPolicy } = $props()

	let logins = $state<McpLogin[]>([])
	let loaded = $state(false)
	let error = $state('')

	async function load() {
		try {
			logins = await toolsApi.mcpLogins()
			error = ''
		} catch (e) {
			error = e instanceof Error ? e.message : 'Could not load the sign ins'
		} finally {
			loaded = true
		}
	}
	onMount(load)

	async function signOut(login: McpLogin) {
		try {
			await toolsApi.mcpSignOut(login.id)
			await load()
		} catch (e) {
			error = e instanceof ApiError || e instanceof Error ? e.message : 'Could not sign out'
		}
	}

	const host = (resource: string) => {
		try {
			return new URL(resource).host
		} catch {
			return resource
		}
	}

	// the numbers are stored in seconds, and shown in the unit people think in
	const minutes = (seconds: number) => Math.round(seconds / 6) / 10
	const whole = (e: Event) => Math.max(0, Math.round(Number((e.target as HTMLInputElement).value) || 0))
</script>

{#if error}<p class="mb-3 text-sm text-destructive" role="alert">{error}</p>{/if}

{#if !loaded}
	<p class="text-sm text-muted-foreground">Loading...</p>
{:else if logins.length === 0}
	<p class="rounded-lg border border-dashed px-3 py-6 text-center text-sm text-muted-foreground">
		No sign ins yet. Add a tool that asks for one, then press <em>Sign in</em> on it in the project's Settings, under Tools.
	</p>
{:else}
	<ul class="divide-y rounded-lg border">
		{#each logins as login (login.id)}
			<li class="flex items-center gap-3 px-3 py-2.5">
				<GlobeIcon class="size-4 shrink-0 text-muted-foreground" />
				<div class="min-w-0">
					<p class="truncate text-sm font-medium">{login.account || host(login.resource)}</p>
					<p class="truncate text-xs text-muted-foreground">
						<span class="font-mono">{host(login.resource)}</span> ·
						{#if login.status === 'active'}
							{login.expires_at ? `token renews ${relative(login.expires_at)}` : 'does not expire'}
						{:else}
							<span class="text-tone-yellow">needs a new sign in{login.error ? `: ${login.error}` : ''}</span>
						{/if}
					</p>
				</div>
				<Button type="button" variant="ghost" size="sm" class="ms-auto shrink-0" aria-label={`Sign out of ${login.account || host(login.resource)}`} onclick={() => signOut(login)}>
					<LogOutIcon /> Sign out
				</Button>
			</li>
		{/each}
	</ul>
	<p class="mt-2 text-xs text-muted-foreground">Signing out only forgets the sign in here. To also withdraw the access, do that in the service's own settings.</p>
{/if}

{#if policy}
	<details class="group mt-4 rounded-lg border">
		<summary class="cursor-pointer list-none px-3 py-2.5 text-sm text-muted-foreground hover:text-foreground">Sign in rules (administrator)</summary>
		<div class="grid gap-4 border-t p-3 sm:grid-cols-2">
			<div class="grid gap-1.5">
				<Label for="mcp-margin">Renew early by (minutes)</Label>
				<Input id="mcp-margin" type="number" min="0" max="1440" value={minutes(policy.refresh_margin_seconds)} oninput={(e) => (policy!.refresh_margin_seconds = whole(e) * 60)} />
				<p class="text-xs text-muted-foreground">A token must outlast a run's time limit by this much when the run starts, or it is renewed first.</p>
			</div>
			<div class="grid gap-1.5">
				<Label for="mcp-lifetime">Assumed token life (minutes)</Label>
				<Input id="mcp-lifetime" type="number" min="1" value={minutes(policy.default_token_seconds)} oninput={(e) => (policy!.default_token_seconds = Math.max(1, whole(e)) * 60)} />
				<p class="text-xs text-muted-foreground">Only used when a service does not say how long its tokens last, which most do.</p>
			</div>
			<div class="grid gap-1.5">
				<Label for="mcp-keepalive">Keep unused sign ins alive (days)</Label>
				<Input id="mcp-keepalive" type="number" min="0" max="365" value={policy.keepalive_days} oninput={(e) => (policy!.keepalive_days = whole(e))} />
				<p class="text-xs text-muted-foreground">Services end a sign in that sits unused (Notion after 30 days). 0 switches this off.</p>
			</div>
			<div class="grid gap-1.5">
				<Label for="mcp-wait">A sign in waits for (minutes)</Label>
				<Input id="mcp-wait" type="number" min="1" max="60" value={policy.sign_in_minutes} oninput={(e) => (policy!.sign_in_minutes = Math.max(1, whole(e)))} />
			</div>
			<div class="grid gap-1.5">
				<Label for="mcp-timeout">Wait for a service (seconds)</Label>
				<Input id="mcp-timeout" type="number" min="3" max="120" value={policy.request_timeout_seconds} oninput={(e) => (policy!.request_timeout_seconds = Math.max(3, whole(e)))} />
			</div>
			<div class="grid gap-1.5">
				<Label for="mcp-name">Name on the service's consent page</Label>
				<Input id="mcp-name" bind:value={policy.client_name} maxlength={60} />
			</div>
			<div class="grid gap-1.5 sm:col-span-2">
				<Label for="mcp-public">Themis' public address</Label>
				<Input id="mcp-public" bind:value={policy.public_url} class="font-mono" placeholder="https://themis.example.com" />
				<p class="text-xs text-muted-foreground">
					Where the service sends a person back to after they sign in. Leave it empty to use the address the page was opened on; set it when
					Themis is behind a reverse proxy.
				</p>
			</div>
			<p class="text-xs text-muted-foreground sm:col-span-2">
				What one service does differently (a scope it needs, a client id registered by hand) is in <code>backend/app/mcp_auth/servers.yaml</code>,
				which is read on every sign in.
			</p>
		</div>
	</details>
{/if}
