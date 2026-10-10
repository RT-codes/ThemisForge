<script lang="ts">
	import { api, ApiError, type Connection, type ConnectionProvider, type ConnectionsList } from '$lib/api'
	import { catalog, filterCatalog, groupByCategory, METHOD_LABEL, type CatalogEntry } from '$lib/connections'
	import { dateTime } from '$lib/format'
	import { Badge } from '$lib/components/ui/badge/index.js'
	import { Button } from '$lib/components/ui/button/index.js'
	import { Input } from '$lib/components/ui/input/index.js'
	import CodexConnection from '$lib/components/CodexConnection.svelte'
	import ConnectDialog from '$lib/components/ConnectDialog.svelte'
	import DynamicIcon from '$lib/components/DynamicIcon.svelte'
	import CircleCheckIcon from '@lucide/svelte/icons/circle-check'
	import CircleXIcon from '@lucide/svelte/icons/circle-x'
	import PlugIcon from '@lucide/svelte/icons/plug'
	import SearchIcon from '@lucide/svelte/icons/search'
	import { onMount, type Snippet } from 'svelte'

	// An administrator's setup of one provider's sign in, drawn inside that provider's row. The settings page gives it so
	// it is saved with the rest of Settings.
	let { setup }: { setup?: Snippet<[string]> } = $props()

	// Everything a person can connect, in one searchable list. Services are connected here once; a project then picks
	// one of its owner's connections, and its agents opt in (see the project's Connections).
	let list = $state<ConnectionsList | null>(null)
	let query = $state('')
	let error = $state('')
	let busyId = $state<number | null>(null)
	let connecting = $state<ConnectionProvider | null>(null)
	let dialogOpen = $state(false)
	let codexOpen = $state(false)

	const entries = $derived(catalog(list?.providers ?? []))
	const groups = $derived(groupByCategory(filterCatalog(entries, query)))
	const accounts = (provider: string) => (list?.connections ?? []).filter((c) => c.provider === provider)

	async function load() {
		try {
			list = await api.connections()
			error = ''
		} catch (e) {
			error = e instanceof Error ? e.message : 'Could not load connections'
		}
	}

	onMount(load)

	function connect(entry: CatalogEntry) {
		connecting = list?.providers.find((p) => p.id === entry.id) ?? null
		dialogOpen = connecting !== null
	}

	async function act(conn: Connection, action: () => Promise<unknown>) {
		busyId = conn.id
		error = ''
		try {
			await action()
		} catch (e) {
			error = e instanceof ApiError || e instanceof Error ? e.message : 'Something went wrong'
		} finally {
			busyId = null
			await load()
		}
	}
</script>

<div class="grid min-w-0 grid-cols-1 gap-4">
	{#if list && !list.secret_key_secure}
		<p class="rounded-lg border border-yellow-500/30 bg-yellow-500/5 p-3 text-sm" role="alert">
			<span class="font-medium text-yellow-300">Set a real secret key first.</span>
			Connections are encrypted with <code>THEMIS_SECRET_KEY</code>, which is still the development default. Ask the administrator to set one, then come back.
		</p>
	{/if}

	<div class="relative">
		<SearchIcon class="pointer-events-none absolute start-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
		<Input bind:value={query} class="ps-9" placeholder="Search connections" aria-label="Search connections" />
	</div>

	{#each groups as group (group.id)}
		<div class="grid min-w-0 grid-cols-1 gap-2">
			<h4 class="px-1 text-xs font-medium tracking-wide text-muted-foreground uppercase">{group.label}</h4>
			{#each group.entries as entry (entry.id)}
				<div class="min-w-0 rounded-lg border">
					<div class="flex items-center gap-3 px-3 py-2.5">
						<span class="flex size-8 shrink-0 items-center justify-center rounded-md bg-primary/15 text-primary">
							<DynamicIcon name={entry.icon} fallback={PlugIcon} class="size-4" />
						</span>
						<span class="min-w-0 flex-1">
							<span class="block truncate text-sm font-medium">{entry.name}</span>
							<span class="block truncate text-xs text-muted-foreground">{entry.description}</span>
						</span>
						{#if entry.id === 'codex'}
							<Button variant="outline" size="sm" onclick={() => (codexOpen = !codexOpen)} aria-expanded={codexOpen}>{codexOpen ? 'Hide' : 'Manage'}</Button>
						{:else}
							<Button variant="outline" size="sm" disabled={!list?.secret_key_secure} onclick={() => connect(entry)}>
								{accounts(entry.id).length ? 'Add another' : 'Connect'}
							</Button>
						{/if}
					</div>

					{#if entry.id === 'codex'}
						{#if codexOpen}<div class="border-t p-3"><CodexConnection bare /></div>{/if}
					{:else}
						{#each accounts(entry.id) as conn (conn.id)}
							<div class="flex items-center gap-3 border-t px-3 py-2.5">
								{#if conn.needs_reconnect}
									<CircleXIcon class="size-4 shrink-0 text-destructive" />
								{:else}
									<CircleCheckIcon class="size-4 shrink-0 text-emerald-400" />
								{/if}
								<span class="min-w-0 flex-1">
									<span class="flex items-center gap-2 truncate text-sm font-medium">
										@{conn.account}
										<Badge variant="secondary">{METHOD_LABEL[conn.method]}</Badge>
									</span>
									<span class="block truncate text-xs text-muted-foreground">
										{#if conn.needs_reconnect}
											Can no longer be read (the secret key changed). Disconnect and connect again.
										{:else}
											Since {dateTime(conn.connected_at)}{conn.checked_at ? ` · last checked ${dateTime(conn.checked_at)}` : ''}
										{/if}
									</span>
								</span>
								<Button variant="ghost" size="sm" disabled={busyId === conn.id} onclick={() => act(conn, () => api.testConnection(conn.id))}>Test</Button>
								<Button variant="ghost" size="sm" disabled={busyId === conn.id} onclick={() => act(conn, () => api.disconnect(conn.id))}>Disconnect</Button>
							</div>
						{/each}
						{#if setup}{@render setup(entry.id)}{/if}
					{/if}
				</div>
			{/each}
		</div>
	{:else}
		{#if list}<p class="text-sm text-muted-foreground">Nothing matches "{query}".</p>{/if}
	{/each}

	{#if error}<p class="text-sm text-destructive" role="alert">{error}</p>{/if}
</div>

<ConnectDialog bind:open={dialogOpen} provider={connecting} onconnected={load} />
