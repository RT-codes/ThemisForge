<script lang="ts">
	import { api, ApiError, type AppSettings, type DockerStatus, type Secret, type SystemStatus } from '$lib/api'
	import { auth } from '$lib/auth.svelte'
	import { Button } from '$lib/components/ui/button/index.js'
	import CodexConnection from '$lib/components/CodexConnection.svelte'
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

	import NumberField from '$lib/components/NumberField.svelte'
	import SettingsSection from '$lib/components/SettingsSection.svelte'
	import { fly } from 'svelte/transition'

	const dockerSummary = $derived(docker ? (docker.ok ? `Connected, Docker ${docker.version}` : 'Not reachable') : 'Checking...')
	const cellSummary = $derived(
		form ? `${form.cell_image} · ${form.cell_cpus} CPU · ${form.cell_memory_mb} MB · ${form.max_concurrent_cells} at once` : ''
	)
	const agentSummary = $derived(form ? `${form.codex_model} · ${form.codex_reasoning_effort} effort` : '')
	const keySummary = $derived(`${secrets.length} ${secrets.length === 1 ? 'key' : 'keys'}`)

	function discard() {
		if (saved) form = { ...saved }
		saveError = ''
	}
</script>

<div class="w-full max-w-3xl px-6 py-8">
	<h2 class="text-2xl font-semibold tracking-tight">Settings</h2>
	<p class="mt-1 text-sm text-muted-foreground">Your own connections, and for administrators how this installation runs.</p>

	{#if auth.user?.is_admin && system?.insecure_secret_key}
		<p class="mt-6 rounded-lg border border-yellow-500/30 bg-yellow-500/5 p-3 text-sm" role="alert">
			<span class="font-medium text-yellow-300">Insecure secret key.</span>
			THEMIS_SECRET_KEY is still the development default, so sessions can be forged and stored keys are weakly protected. Set a real value in
			<code>backend/.env</code> (the installer does this for you) and restart. Keys saved before the change must be added again.
		</p>
	{/if}

	<div class="mt-8 grid gap-3">
		<h3 class="px-1 text-xs font-medium tracking-wide text-muted-foreground uppercase">Your account</h3>
		<SettingsSection id="codex" title="Codex" description="Sign in with ChatGPT so your tasks use your plan's Codex usage." defaultOpen>
			<CodexConnection bare />
		</SettingsSection>
	</div>

	{#if auth.user?.is_admin}
		<div class="mt-8 grid gap-3">
			<h3 class="px-1 text-xs font-medium tracking-wide text-muted-foreground uppercase">Administration</h3>
			{#if loadError}
				<p class="text-sm text-destructive" role="alert">{loadError}</p>
			{:else if form}
				<form onsubmit={save} class="grid gap-3">
					<SettingsSection
						id="docker"
						title="Docker"
						description="Cells are Docker containers, so ThemisForge needs to reach a Docker engine."
						summary={dockerSummary}
						status={docker ? (docker.ok ? 'ok' : 'warn') : null}
						forceOpen={!!docker && !docker.ok}
					>
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
					</SettingsSection>

					<SettingsSection id="cells" title="Cells" description="Defaults for every container a task runs in." summary={cellSummary}>
						<div class="grid gap-4 sm:grid-cols-2">
							<div class="grid gap-2 sm:col-span-2">
								<Label for="cell-image">Image</Label>
								<Input id="cell-image" bind:value={form.cell_image} class="font-mono" required />
							</div>
							<div class="grid gap-2">
								<Label for="cell-cpus">CPUs per cell</Label>
								<NumberField id="cell-cpus" bind:value={form.cell_cpus} unit="CPUs" min={0.1} max={64} step={0.1} />
							</div>
							<div class="grid gap-2">
								<Label for="cell-mem">Memory per cell</Label>
								<NumberField id="cell-mem" bind:value={form.cell_memory_mb} unit="MB" min={64} step={64} />
							</div>
							<div class="grid gap-2">
								<Label for="cell-timeout">Time limit per run</Label>
								<NumberField id="cell-timeout" bind:value={form.cell_timeout_seconds} unit="seconds" min={10} step={10} />
							</div>
							<div class="grid gap-2">
								<Label for="cell-max">Cells at the same time</Label>
								<NumberField id="cell-max" bind:value={form.max_concurrent_cells} unit="cells" min={1} max={64} />
							</div>
							<div class="grid gap-2 sm:col-span-2">
								<Label for="keep-days">Keep working folders for</Label>
								<NumberField id="keep-days" bind:value={form.keep_workspaces_days} unit="days" min={0} max={3650} />
								<p class="text-xs text-muted-foreground">Every run gets its own private working folder. Old ones are deleted after this long; 0 deletes them right away.</p>
							</div>
						</div>
					</SettingsSection>

					<SettingsSection id="agents" title="Codex agents" description="The image and model tasks use when they run with a Codex agent." summary={agentSummary}>
						<div class="grid gap-4 sm:grid-cols-2">
							<div class="grid gap-2 sm:col-span-2">
								<Label for="codex-image">Image</Label>
								<Input id="codex-image" bind:value={form.codex_image} class="font-mono" required />
								<p class="text-xs text-muted-foreground">Build the default with <code>./themis build-images</code>.</p>
							</div>
							<div class="grid gap-2">
								<Label for="codex-model">Model</Label>
								<Input id="codex-model" bind:value={form.codex_model} class="font-mono" required />
							</div>
							<div class="grid gap-2">
								<Label for="codex-effort">Reasoning effort</Label>
								<Select.Root type="single" bind:value={form.codex_reasoning_effort}>
									<Select.Trigger id="codex-effort" class="w-full capitalize">{form.codex_reasoning_effort}</Select.Trigger>
									<Select.Content>
										{#each ['low', 'medium', 'high'] as e (e)}<Select.Item value={e} label={e} class="capitalize">{e}</Select.Item>{/each}
									</Select.Content>
								</Select.Root>
							</div>
						</div>
					</SettingsSection>

					<SettingsSection id="timezone" title="Time zone" description="Repeating tasks run at these clock times." summary={form.timezone}>
						<div class="grid gap-2">
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
						</div>
					</SettingsSection>

					{#if dirty || saving || justSaved || saveError}
						<div class="sticky bottom-4 z-10" transition:fly={{ y: 16, duration: 200 }}>
							<div class="flex items-center gap-3 rounded-xl border bg-popover/95 px-4 py-3 shadow-lg backdrop-blur">
								<p class={cn('flex-1 text-sm', saveError ? 'text-destructive' : justSaved && !dirty ? 'text-emerald-400' : '')} role={saveError ? 'alert' : 'status'}>
									{saveError || (justSaved && !dirty ? 'Saved' : 'You have unsaved changes')}
								</p>
								<Button type="button" variant="ghost" disabled={!dirty || saving} onclick={discard}>Discard</Button>
								<Button type="submit" disabled={!dirty || saving}>Save changes</Button>
							</div>
						</div>
					{/if}
				</form>

				<SettingsSection id="keys" title="Keys" description="Credentials for model providers and tools. They are encrypted and never shown again." summary={keySummary}>
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
				</SettingsSection>
			{/if}
		</div>
	{/if}
</div>
