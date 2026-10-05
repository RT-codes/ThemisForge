<script lang="ts">
	import { api, ApiError, type AppSettings, type DockerStatus, type Secret, type SystemStatus } from '$lib/api'
	import { auth } from '$lib/auth.svelte'
	import { Button } from '$lib/components/ui/button/index.js'
	import CodexConnection from '$lib/components/CodexConnection.svelte'
	import * as Card from '$lib/components/ui/card/index.js'
	import { Input } from '$lib/components/ui/input/index.js'
	import { Label } from '$lib/components/ui/label/index.js'
	import * as Select from '$lib/components/ui/select/index.js'
	import { dateTime } from '$lib/format'
	import { cn } from '$lib/utils'
	import CircleCheckIcon from '@lucide/svelte/icons/circle-check'
	import CircleXIcon from '@lucide/svelte/icons/circle-x'
	import KeyRoundIcon from '@lucide/svelte/icons/key-round'
	import RefreshCwIcon from '@lucide/svelte/icons/refresh-cw'
	import Trash2Icon from '@lucide/svelte/icons/trash-2'
	import { onMount } from 'svelte'

	let saved = $state<AppSettings | null>(null)
	let form = $state<AppSettings | null>(null)
	let docker = $state<DockerStatus | null>(null)
	let system = $state<SystemStatus | null>(null)
	let checking = $state(false)
	let secrets = $state<Secret[]>([])
	let loadError = $state('')
	let saveError = $state('')
	let saving = $state(false)
	let justSaved = $state(false)

	let secretName = $state('')
	let secretKind = $state('anthropic')
	let secretValue = $state('')
	let secretError = $state('')

	const kinds = ['anthropic', 'openai', 'google', 'github', 'custom']
	const zones = (() => {
		try {
			return Intl.supportedValuesOf('timeZone')
		} catch {
			return []
		}
	})()
	const browserZone = Intl.DateTimeFormat().resolvedOptions().timeZone
	const dirty = $derived(JSON.stringify(form) !== JSON.stringify(saved))

	async function checkDocker(host?: string) {
		checking = true
		try {
			docker = await api.docker(host)
		} catch (e) {
			docker = {
				ok: false,
				installed: true,
				host: host || 'local socket',
				version: null,
				os: null,
				cpus: null,
				memory_mb: null,
				error: e instanceof Error ? e.message : 'Check failed',
				hint: null,
			}
		} finally {
			checking = false
		}
	}

	async function load() {
		try {
			saved = await api.settings()
			form = { ...saved }
			secrets = await api.secrets()
			system = await api.systemStatus()
			await checkDocker()
		} catch (e) {
			loadError = e instanceof ApiError && e.status === 403 ? 'Only administrators can change settings.' : (e as Error).message
		}
	}
	onMount(() => {
		if (auth.user?.is_admin) load()
	})

	async function save(e: SubmitEvent) {
		e.preventDefault()
		if (!form) return
		saveError = ''
		saving = true
		try {
			saved = await api.saveSettings(form)
			form = { ...saved }
			justSaved = true
			setTimeout(() => (justSaved = false), 2500)
			checkDocker()
		} catch (err) {
			saveError = err instanceof Error ? err.message : 'Could not save'
		} finally {
			saving = false
		}
	}

	async function addSecret(e: SubmitEvent) {
		e.preventDefault()
		secretError = ''
		try {
			await api.createSecret(secretName, secretKind, secretValue)
			secretName = secretValue = ''
			secrets = await api.secrets()
		} catch (err) {
			secretError = err instanceof Error ? err.message : 'Could not add the secret'
		}
	}

	async function removeSecret(s: Secret) {
		await api.deleteSecret(s.id)
		secrets = await api.secrets()
	}

	const gb = (mb: number | null) => (mb === null ? '' : `${(mb / 1024).toFixed(1)} GB`)
</script>

<div class="mx-auto w-full max-w-3xl px-6 py-8">
	<h2 class="text-2xl font-semibold tracking-tight">Settings</h2>
	<p class="text-sm text-muted-foreground">Your connections and, for administrators, how this ThemisForge installation runs cells and reaches the outside world.</p>

	{#if !auth.user?.is_admin}
		<CodexConnection class="mt-8" />
	{:else if loadError}
		<p class="mt-8 text-sm text-destructive" role="alert">{loadError}</p>
	{:else if form}
		{#if system?.insecure_secret_key}
			<p class="mt-8 rounded-lg border border-yellow-500/30 bg-yellow-500/5 p-3 text-sm" role="alert">
				<span class="font-medium text-yellow-300">Insecure secret key.</span>
				THEMIS_SECRET_KEY is still the development default, so sessions can be forged and stored keys are weakly protected. Set a real value in
				<code>backend/.env</code> (the installer does this for you) and restart. Keys saved before the change must be added again.
			</p>
		{/if}
		<form onsubmit={save} class="mt-8 grid gap-6">
			<Card.Root>
				<Card.Header>
					<Card.Title>Docker</Card.Title>
					<Card.Description>Cells are Docker containers. ThemisForge needs to reach a Docker engine.</Card.Description>
				</Card.Header>
				<Card.Content class="grid gap-4">
					{#if docker}
						<div
							class={cn(
								'flex items-start gap-3 rounded-lg border p-3',
								docker.ok ? 'border-emerald-500/30 bg-emerald-500/5' : 'border-destructive/40 bg-destructive/5'
							)}
							role="status"
						>
							{#if docker.ok}
								<CircleCheckIcon class="mt-0.5 size-5 shrink-0 text-emerald-400" />
							{:else}
								<CircleXIcon class="mt-0.5 size-5 shrink-0 text-destructive" />
							{/if}
							<div class="min-w-0 text-sm">
								{#if docker.ok}
									<p class="font-medium">Connected to Docker {docker.version}</p>
									<p class="text-muted-foreground">
										{docker.host} · {docker.os} · {docker.cpus} CPUs · {gb(docker.memory_mb)} RAM
									</p>
								{:else}
									<p class="font-medium">{docker.installed ? 'Docker is not reachable' : 'Docker is not installed'}</p>
									<p class="break-words text-muted-foreground">{docker.error}</p>
									{#if docker.hint}<p class="mt-1">{docker.hint}</p>{/if}
								{/if}
							</div>
							<Button type="button" variant="ghost" size="icon" class="ms-auto shrink-0" aria-label="Check again" disabled={checking} onclick={() => checkDocker(form!.docker_host)}>
								<RefreshCwIcon class={checking ? 'animate-spin' : ''} />
							</Button>
						</div>
					{/if}
					<div class="grid gap-2">
						<Label for="docker-host">Docker host</Label>
						<div class="flex gap-2">
							<Input id="docker-host" bind:value={form.docker_host} placeholder="Local Docker socket (default)" class="font-mono" />
							<Button type="button" variant="outline" disabled={checking} onclick={() => checkDocker(form!.docker_host)}>Test</Button>
						</div>
						<p class="text-xs text-muted-foreground">
							Leave empty for the Docker on this machine. To use another machine: <code>ssh://user@host</code> or <code>tcp://host:2376</code>.
						</p>
					</div>
				</Card.Content>
			</Card.Root>

			<Card.Root>
				<Card.Header>
					<Card.Title>Cells</Card.Title>
					<Card.Description>Defaults for every container a task runs in.</Card.Description>
				</Card.Header>
				<Card.Content class="grid gap-4 sm:grid-cols-2">
					<div class="grid gap-2 sm:col-span-2">
						<Label for="cell-image">Image</Label>
						<Input id="cell-image" bind:value={form.cell_image} class="font-mono" required />
					</div>
					<div class="grid gap-2">
						<Label for="cell-cpus">CPUs per cell</Label>
						<Input id="cell-cpus" type="number" min="0.1" max="64" step="0.1" bind:value={form.cell_cpus} required />
					</div>
					<div class="grid gap-2">
						<Label for="cell-mem">Memory per cell (MB)</Label>
						<Input id="cell-mem" type="number" min="64" step="64" bind:value={form.cell_memory_mb} required />
					</div>
					<div class="grid gap-2">
						<Label for="cell-timeout">Time limit (seconds)</Label>
						<Input id="cell-timeout" type="number" min="10" step="10" bind:value={form.cell_timeout_seconds} required />
					</div>
					<div class="grid gap-2">
						<Label for="cell-max">Cells at the same time</Label>
						<Input id="cell-max" type="number" min="1" max="64" bind:value={form.max_concurrent_cells} required />
					</div>
				</Card.Content>
			</Card.Root>

			<Card.Root>
				<Card.Header>
					<Card.Title>Schedules</Card.Title>
					<Card.Description>Recurring tasks are evaluated in this time zone.</Card.Description>
				</Card.Header>
				<Card.Content class="grid gap-2">
					<Label for="timezone">Time zone</Label>
					<div class="flex gap-2">
						<Input id="timezone" list="zones" bind:value={form.timezone} required />
						{#if browserZone !== form.timezone}
							<Button type="button" variant="outline" onclick={() => (form!.timezone = browserZone)}>Use {browserZone}</Button>
						{/if}
					</div>
					<datalist id="zones">
						{#each zones as z (z)}<option value={z}></option>{/each}
					</datalist>
				</Card.Content>
			</Card.Root>

			<div class="flex items-center justify-end gap-3">
				{#if saveError}<p class="text-sm text-destructive" role="alert">{saveError}</p>{/if}
				{#if justSaved}<p class="text-sm text-emerald-400">Saved</p>{/if}
				<Button type="submit" disabled={!dirty || saving}>Save settings</Button>
			</div>
		</form>

		<CodexConnection class="mt-6" />

		<Card.Root class="mt-6">
			<Card.Header>
				<Card.Title>Keys and connections</Card.Title>
				<Card.Description>
					Credentials for model providers and tools. They are encrypted at rest and never shown again after saving.
				</Card.Description>
			</Card.Header>
			<Card.Content class="grid gap-4">
				{#if secrets.length}
					<ul class="divide-y rounded-lg border">
						{#each secrets as s (s.id)}
							<li class="flex items-center gap-3 px-3 py-2.5">
								<KeyRoundIcon class="size-4 shrink-0 text-muted-foreground" />
								<div class="min-w-0">
									<p class="truncate text-sm font-medium">{s.name}</p>
									<p class="text-xs text-muted-foreground">{s.kind} · <span class="font-mono">{s.hint}</span> · added {dateTime(s.created_at)}</p>
								</div>
								<Button type="button" variant="ghost" size="icon" class="ms-auto" aria-label={`Delete ${s.name}`} onclick={() => removeSecret(s)}>
									<Trash2Icon />
								</Button>
							</li>
						{/each}
					</ul>
				{:else}
					<p class="rounded-lg border border-dashed py-6 text-center text-sm text-muted-foreground">No keys yet.</p>
				{/if}

				<form onsubmit={addSecret} class="grid gap-3 sm:grid-cols-[1fr_9rem]">
					<Input bind:value={secretName} placeholder="Name, e.g. Anthropic (work)" required aria-label="Secret name" />
					<Select.Root type="single" bind:value={secretKind}>
						<Select.Trigger class="w-full capitalize">{secretKind}</Select.Trigger>
						<Select.Content>
							{#each kinds as k (k)}<Select.Item value={k} label={k} class="capitalize">{k}</Select.Item>{/each}
						</Select.Content>
					</Select.Root>
					<Input type="password" autocomplete="off" bind:value={secretValue} placeholder="Key or token" required class="font-mono sm:col-span-2" aria-label="Secret value" />
					{#if secretError}<p class="text-sm text-destructive sm:col-span-2" role="alert">{secretError}</p>{/if}
					<Button type="submit" variant="secondary" class="justify-self-start sm:col-span-2">Add key</Button>
				</form>
			</Card.Content>
		</Card.Root>
	{/if}
</div>
