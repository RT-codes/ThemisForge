<script lang="ts">
	import { api, ApiError, type Connection, type ConnectionProvider, type ProjectConnection } from '$lib/api'
	import { METHOD_LABEL } from '$lib/connections'
	import { router } from '$lib/router.svelte'
	import { cn } from '$lib/utils'
	import { Button } from '$lib/components/ui/button/index.js'
	import * as Dialog from '$lib/components/ui/dialog/index.js'
	import { Input } from '$lib/components/ui/input/index.js'
	import { Label } from '$lib/components/ui/label/index.js'
	import LoaderCircleIcon from '@lucide/svelte/icons/loader-circle'

	// Which of your connections a project uses for one service, and the project's own settings for it (for GitHub,
	// the repository). Agents of the project then opt in to it on their own page.
	let {
		open = $bindable(false),
		projectId,
		provider,
		current,
		onsaved,
	}: {
		open: boolean
		projectId: number
		provider: ConnectionProvider | null
		current: ProjectConnection | null
		onsaved: () => void
	} = $props()

	let mine = $state<Connection[]>([])
	let chosen = $state<number | null>(null)
	let config = $state<Record<string, string>>({})
	let error = $state('')
	let busy = $state(false)
	let loaded = $state(false)

	$effect(() => {
		if (!open || !provider) return
		const id = provider.id
		loaded = false
		error = ''
		chosen = current?.connection_id ?? null
		config = { ...(current?.config ?? {}) }
		api.connections().then(
			(list) => {
				mine = list.connections.filter((c) => c.provider === id && !c.needs_reconnect)
				chosen = chosen ?? mine[0]?.id ?? null
				loaded = true
			},
			(e) => {
				error = e instanceof Error ? e.message : 'Could not load your connections'
				loaded = true
			},
		)
	})

	async function run(action: () => Promise<unknown>) {
		error = ''
		busy = true
		try {
			await action()
			onsaved()
			open = false
		} catch (e) {
			error = e instanceof ApiError || e instanceof Error ? e.message : 'Something went wrong'
		} finally {
			busy = false
		}
	}

	const save = (e: SubmitEvent) => {
		e.preventDefault()
		if (provider && chosen !== null) void run(() => api.useConnection(projectId, provider.id, chosen!, config))
	}
</script>

<Dialog.Root bind:open>
	<Dialog.Content class="sm:max-w-lg">
		{#if provider}
			<Dialog.Header>
				<Dialog.Title>{provider.name} for this project</Dialog.Title>
				<Dialog.Description>Pick the connection this project uses. Agents of the project can then be given it on their page.</Dialog.Description>
			</Dialog.Header>

			{#if !loaded}
				<p class="text-sm text-muted-foreground">Loading...</p>
			{:else if mine.length === 0}
				<div class="grid gap-3 rounded-lg border border-dashed p-4 text-sm">
					<p>You have no {provider.name} connection yet.</p>
					<Button class="justify-self-start" onclick={() => router.navigate('/settings')}>Connect {provider.name} in Settings</Button>
				</div>
			{:else}
				<form onsubmit={save} class="grid gap-4">
					<div class="grid gap-2" role="radiogroup" aria-label="Connection">
						{#each mine as conn (conn.id)}
							<button
								type="button"
								role="radio"
								aria-checked={chosen === conn.id}
								onclick={() => (chosen = conn.id)}
								class={cn('flex items-center gap-2 rounded-lg border px-3 py-2.5 text-start text-sm', chosen === conn.id ? 'border-primary bg-primary/5' : 'hover:bg-accent/30')}
							>
								<span class="font-medium">@{conn.account}</span>
								<span class="text-xs text-muted-foreground">{METHOD_LABEL[conn.method]}</span>
							</button>
						{/each}
					</div>
					{#each provider.config_fields as field (field.key)}
						<div class="grid gap-2">
							<Label for="connection-{field.key}">{field.label}</Label>
							<Input id="connection-{field.key}" bind:value={config[field.key]} placeholder={field.placeholder} />
							{#if field.help}<p class="text-xs text-muted-foreground">{field.help}</p>{/if}
						</div>
					{/each}
					{#if error}<p class="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive" role="alert">{error}</p>{/if}
					<Dialog.Footer>
						{#if current}
							<Button type="button" variant="ghost" class="me-auto" disabled={busy} onclick={() => run(() => api.stopUsingConnection(projectId, provider.id))}>Stop using</Button>
						{/if}
						<Button type="button" variant="ghost" onclick={() => (open = false)}>Cancel</Button>
						<Button type="submit" disabled={busy || chosen === null}>
							{#if busy}<LoaderCircleIcon class="animate-spin" />{/if}Save
						</Button>
					</Dialog.Footer>
				</form>
			{/if}
			{#if loaded && mine.length === 0 && error}<p class="text-sm text-destructive" role="alert">{error}</p>{/if}
		{/if}
	</Dialog.Content>
</Dialog.Root>
