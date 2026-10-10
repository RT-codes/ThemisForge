<script lang="ts">
	import { api, ApiError, type AppSettings, type DockerStatus, type Resources, type Secret, type SystemStatus } from '$lib/api'
	import { auth } from '$lib/auth.svelte'
	import { Button } from '$lib/components/ui/button/index.js'
	import ConnectionsSettings from '$lib/components/ConnectionsSettings.svelte'
	import AppearanceSettings from '$lib/components/AppearanceSettings.svelte'
	import { Input } from '$lib/components/ui/input/index.js'
	import { Label } from '$lib/components/ui/label/index.js'
	import * as Select from '$lib/components/ui/select/index.js'
	import { Switch } from '$lib/components/ui/switch/index.js'
	import * as Tooltip from '$lib/components/ui/tooltip/index.js'
	import { cellsThatFit } from '$lib/budget'
	import { dateTime } from '$lib/format'
	import { cn } from '$lib/utils'
	import ChevronDownIcon from '@lucide/svelte/icons/chevron-down'
	import CircleCheckIcon from '@lucide/svelte/icons/circle-check'
	import CircleXIcon from '@lucide/svelte/icons/circle-x'
	import InfoIcon from '@lucide/svelte/icons/info'
	import FolderIcon from '@lucide/svelte/icons/folder'
	import KeyRoundIcon from '@lucide/svelte/icons/key-round'
	import RefreshCwIcon from '@lucide/svelte/icons/refresh-cw'
	import Trash2Icon from '@lucide/svelte/icons/trash-2'
	import { onMount } from 'svelte'

	let saved = $state<AppSettings | null>(null)
	let form = $state<AppSettings | null>(null)
	let docker = $state<DockerStatus | null>(null)
	let resources = $state<Resources | null>(null)
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
	// the budget is a nested object, so a plain spread would share it between the form and the saved copy
	const copy = (s: AppSettings): AppSettings => ({ ...s, budget: { ...s.budget }, mount_roots: s.mount_roots.map((r) => ({ ...r })) })
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
				os_type: null,
				cpus: null,
				memory_mb: null,
				error: e instanceof Error ? e.message : 'Check failed',
				hint: null,
			}
		} finally {
			checking = false
		}
	}

	async function loadResources() {
		try {
			resources = await api.resources()
		} catch {
			resources = null
		}
	}

	async function load() {
		try {
			saved = await api.settings()
			form = copy(saved)
			secrets = await api.secrets()
			system = await api.systemStatus()
			await Promise.all([checkDocker(), loadResources()])
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
			form = copy(saved)
			justSaved = true
			setTimeout(() => (justSaved = false), 2500)
			checkDocker()
			loadResources()
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
	import { relative } from '$lib/format'
	import ArrowUpCircleIcon from '@lucide/svelte/icons/circle-arrow-up'
	import SettingsSection from '$lib/components/SettingsSection.svelte'
	import { fly } from 'svelte/transition'

	const update = $derived(system?.update ?? null)
	const updateSummary = $derived(
		update ? (update.available ? `${update.latest} available` : update.error ? 'Could not check' : update.enabled ? `Up to date, ${update.current}` : 'Checking is off') : ''
	)
	let checkingUpdates = $state(false)
	async function checkUpdatesNow() {
		checkingUpdates = true
		try {
			const found = await api.checkForUpdates()
			if (system) system = { ...system, update: found }
		} catch (e) {
			if (system?.update) system = { ...system, update: { ...system.update, error: e instanceof Error ? e.message : 'Could not check for updates' } }
		} finally {
			checkingUpdates = false
		}
	}

	const dockerSummary = $derived(docker ? (docker.ok ? `Connected, Docker ${docker.version}` : docker.version ? 'Needs attention' : 'Not reachable') : 'Checking...')
	const cellSummary = $derived(form ? `${form.cell_image} · ${form.cell_cpus} CPU · ${form.cell_memory_mb} MB` : '')
	const host = $derived(resources?.ok ? resources : null)
	const fits = $derived(form ? cellsThatFit(form.budget, { cpus: form.cell_cpus, memory_mb: form.cell_memory_mb }) : 0)
	const cpuOver = $derived(!!form && !!host && form.budget.cpus > (host.host_cpus ?? Infinity))
	const memoryOver = $derived(!!form && !!host && form.budget.memory_mb > (host.host_memory_mb ?? Infinity))
	const overCommitted = $derived(cpuOver || memoryOver)
	const diskUsed = $derived(resources && resources.disk_total_mb ? (1 - resources.disk_free_mb / resources.disk_total_mb) * 100 : 0)
	const resourceSummary = $derived(
		form ? `${form.budget.cpus} CPU · ${gb(form.budget.memory_mb)} · fits ${fits} ${fits === 1 ? 'cell' : 'cells'}` : ''
	)
	let newRoot = $state('')
	const rootSummary = $derived(form ? (form.mount_roots.length ? `${form.mount_roots.length} approved` : 'None approved') : '')
	function addRoot() {
		const path = newRoot.trim().replace(/\/+$/, '')
		if (!path || !form || form.mount_roots.some((r) => r.path === path)) return void (newRoot = '')
		form.mount_roots = [...form.mount_roots, { path, allow_write: false }]
		newRoot = ''
	}
	const agentSummary = $derived(form ? `${form.codex_model} · ${form.codex_reasoning_effort} effort` : '')
	const keySummary = $derived(`${secrets.length} ${secrets.length === 1 ? 'key' : 'keys'}`)

	function discard() {
		if (saved) form = copy(saved)
		saveError = ''
	}
</script>

{#snippet meter(label: string, value: string, caption: string, percent: number, warn: boolean)}
	<div class="rounded-lg border p-3">
		<div class="flex items-baseline justify-between gap-2 text-sm">
			<span class="text-muted-foreground">{label}</span>
			<span class="font-medium tabular-nums">{value}</span>
		</div>
		<div class="mt-2 h-1.5 overflow-hidden rounded-full bg-muted">
			<div class={cn('h-full rounded-full transition-[width] duration-200', warn ? 'bg-destructive' : 'bg-primary')} style="width: {Math.min(100, Math.max(0, percent))}%"></div>
		</div>
		<p class="mt-1.5 text-xs text-muted-foreground">{caption}</p>
	</div>
{/snippet}

{#snippet signInSetup(provider: string)}
	{#if provider === 'github' && form}
		<details class="group border-t px-3 py-2.5">
			<summary class="flex cursor-pointer list-none items-center gap-2 text-sm text-muted-foreground hover:text-foreground">
				<ChevronDownIcon class="size-4 transition-transform group-open:rotate-180" />
				Sign in setup (administrator)
				<span class="ms-auto text-xs">{form.github_client_id ? 'Set up' : 'Not set up, tokens only'}</span>
			</summary>
			<div class="mt-3 grid gap-2">
				<Label for="github-client-id">OAuth App client ID</Label>
				<Input id="github-client-id" bind:value={form.github_client_id} class="font-mono" placeholder="Iv1.0123456789abcdef" maxlength={100} />
				<p class="text-xs text-muted-foreground">
					Lets people connect GitHub by signing in instead of pasting a token. Create an OAuth App at github.com/settings/developers, switch on <em>Enable Device Flow</em>, and paste its client ID here. It is public, so it is not a secret. Saved with the Save changes bar.
				</p>
			</div>
		</details>
	{/if}
{/snippet}

<div class="w-full max-w-6xl px-6 py-8">
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
		<AppearanceSettings />
	</div>

	<div class="mt-8 grid gap-3">
		<h3 class="px-1 text-xs font-medium tracking-wide text-muted-foreground uppercase">Connections</h3>
		<SettingsSection id="connections" title="Your connections" description="Your sign ins to AI models and services like GitHub. Projects and their agents use them." defaultOpen>
			<ConnectionsSettings setup={auth.user?.is_admin ? signInSetup : undefined} />
		</SettingsSection>
		{#if auth.user?.is_admin}
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

	{#if auth.user?.is_admin}
		<div class="mt-8 grid gap-8">
			{#if loadError}
				<p class="text-sm text-destructive" role="alert">{loadError}</p>
			{:else if form}
				<form onsubmit={save} class="grid gap-8">
					<div class="grid gap-3">
					<h3 class="px-1 text-xs font-medium tracking-wide text-muted-foreground uppercase">Cells and agents</h3>
					<SettingsSection
						id="docker"
						title="Docker"
						description="Cells are Docker containers, so Themis needs to reach a Docker engine."
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
									<p class="font-medium">{docker.installed ? (docker.version ? 'Docker cannot be used' : 'Docker is not reachable') : 'Docker is not installed'}</p>
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

					<SettingsSection
						id="resources"
						title="Resources"
						description="How much of this machine all running cells together may use."
						summary={resourceSummary}
						status={fits === 0 || overCommitted ? 'warn' : 'ok'}
						forceOpen={fits === 0}
					>
						{#if resources && !resources.ok}
							<p class="text-sm text-muted-foreground">The machine could not be read: {resources.error}. You can still set a budget.</p>
						{/if}
						<div class="grid gap-3 sm:grid-cols-3">
							{@render meter(
								'CPUs',
								host ? `${host.host_cpus}` : '-',
								`${form.budget.cpus} in the budget`,
								host?.host_cpus ? (form.budget.cpus / host.host_cpus) * 100 : 0,
								cpuOver
							)}
							{@render meter(
								'Memory',
								host ? gb(host.host_memory_mb) : '-',
								`${gb(form.budget.memory_mb)} in the budget`,
								host?.host_memory_mb ? (form.budget.memory_mb / host.host_memory_mb) * 100 : 0,
								memoryOver
							)}
							{@render meter(
								'Disk free',
								resources ? gb(resources.disk_free_mb) : '-',
								resources ? `${Math.round(diskUsed)}% of ${gb(resources.disk_total_mb)} used` : '',
								diskUsed,
								diskUsed > 90
							)}
						</div>
						<p class="-mt-2 text-xs text-muted-foreground">
							Docker reports the CPUs and memory (it can be another machine). The disk is the one Themis keeps its data on.
						</p>
						<div class="grid gap-4 sm:grid-cols-2">
							<div class="grid gap-2">
								<Label for="budget-cpus">CPUs for all cells</Label>
								<NumberField id="budget-cpus" bind:value={form.budget.cpus} unit="CPUs" min={0.1} max={4096} step="any" />
							</div>
							<div class="grid gap-2">
								<Label for="budget-mem">Memory for all cells</Label>
								<NumberField id="budget-mem" bind:value={form.budget.memory_mb} unit="MB" min={64} step={1} />
							</div>
						</div>
						<div class="flex flex-wrap items-center gap-x-4 gap-y-2 text-sm">
							<p class={cn(fits === 0 ? 'text-destructive' : 'text-muted-foreground')} role={fits === 0 ? 'alert' : undefined}>
								{#if fits === 0}
									Not even one cell of the default size fits, so tasks would fail. Raise the budget or shrink the cells.
								{:else}
									Fits <span class="font-medium text-foreground">{fits}</span>
									{fits === 1 ? 'cell' : 'cells'} of the default size ({form.cell_cpus} CPU, {form.cell_memory_mb} MB) at the same time.
								{/if}
							</p>
							{#if overCommitted}
								<p class="text-yellow-300">This is more than the machine has.</p>
							{/if}
							{#if resources?.recommended}
								<Button
									type="button"
									variant="outline"
									size="sm"
									class="ms-auto"
									onclick={() => (form!.budget = { ...resources!.recommended! })}
								>
									Use recommended ({resources.recommended.cpus} CPU, {gb(resources.recommended.memory_mb)})
								</Button>
							{/if}
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
							<div class="grid content-start gap-2">
								<Label for="cell-timeout">Time limit per run</Label>
								<NumberField id="cell-timeout" bind:value={form.cell_timeout_seconds} unit="seconds" min={10} step={10} />
							</div>
							<div class="grid content-start gap-2">
								<Label for="start-cooldown">Wait before a Ready task starts</Label>
								<NumberField id="start-cooldown" bind:value={form.start_cooldown_seconds} unit="seconds" min={0} max={3600} />
								<p class="text-xs text-muted-foreground">A task starts this long after it was moved to Ready or its last run ended, and a workflow starts for a task no sooner than this after the last one did. It stops loops from hammering the machine; 0 starts right away. A project or a single task can set its own.</p>
							</div>
							<div class="grid content-start gap-2">
								<Label for="max-hops">Most automatic moves of one task in a row</Label>
								<NumberField id="max-hops" bind:value={form.max_automation_hops} unit="moves" min={1} max={100} />
								<p class="text-xs text-muted-foreground">Workflows that move or make the same task over and over stop after this many, until a person acts on the task. It catches two boards that keep sending a task back and forth. A project or a single task can set its own.</p>
							</div>
							<div class="grid content-start gap-2">
								<Label for="keep-days">Keep working folders for</Label>
								<NumberField id="keep-days" bind:value={form.keep_workspaces_days} unit="days" min={0} max={3650} />
								<p class="text-xs text-muted-foreground">Every run gets its own private working folder. Old ones are deleted after this long; 0 deletes them right away.</p>
							</div>
						</div>
					</SettingsSection>

					<SettingsSection
						id="mounts"
						title="Mount roots"
						description="Folders on this machine that agents may be given. Nothing outside them can be mounted."
						summary={rootSummary}
					>
						<p class="rounded-lg border border-yellow-500/30 bg-yellow-500/5 p-3 text-sm">
							<span class="font-medium text-yellow-300">Mind what you approve.</span>
							Agents run unattended. A folder they may <em>write</em> to can have files changed or deleted, with no undo. Approve only folders you are
							fine with that for, and leave "Allow writing" off wherever reading is enough. Everything inside an approved folder is covered.
						</p>
						{#if form.mount_roots.length}
							<ul class="divide-y rounded-lg border">
								{#each form.mount_roots as root, i (root.path)}
									<li class="flex items-center gap-3 px-3 py-2.5">
										<FolderIcon class="size-4 shrink-0 text-muted-foreground" />
										<span class="min-w-0 flex-1 truncate font-mono text-sm">{root.path}</span>
										<label class="flex items-center gap-2 text-xs text-muted-foreground">
											<Switch checked={root.allow_write} onCheckedChange={(on) => (form!.mount_roots[i].allow_write = on)} aria-label="Allow writing in {root.path}" />
											Allow writing
											<Tooltip.Root>
												<Tooltip.Trigger type="button" class="text-muted-foreground/70 hover:text-foreground" aria-label="What does allow writing mean?">
													<InfoIcon class="size-3.5" />
												</Tooltip.Trigger>
												<Tooltip.Content class="max-w-64">
													Off: cells can only read files here. On: they can also create, change and delete them. A real, unattended agent has no undo.
												</Tooltip.Content>
											</Tooltip.Root>
										</label>
										<Button type="button" variant="ghost" size="icon-sm" aria-label="Stop approving {root.path}" class="-me-1 text-muted-foreground/60 hover:text-destructive" onclick={() => (form!.mount_roots = form!.mount_roots.filter((_, j) => j !== i))}>
											<Trash2Icon />
										</Button>
									</li>
								{/each}
							</ul>
						{/if}
						<div class="flex gap-2">
							<Input
								bind:value={newRoot}
								placeholder={system?.platform === 'windows' ? 'C:\\Users\\you\\notes' : '/home/you/notes'}
								class="font-mono"
								aria-label="Folder to approve"
								onkeydown={(e) => e.key === 'Enter' && (e.preventDefault(), addRoot())}
							/>
							<Button type="button" variant="outline" disabled={!newRoot.trim()} onclick={addRoot}>Approve folder</Button>
						</div>
						<p class="text-xs text-muted-foreground">
							Projects then add these as shared folders. Themis's own data and configuration can never be mounted, and a link that leads out of an approved folder does not count.
						</p>
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

					</div>

					<div class="grid gap-3">
					<h3 class="px-1 text-xs font-medium tracking-wide text-muted-foreground uppercase">General</h3>
					<SettingsSection
						id="updates"
						title="Updates"
						description="Whether a newer Themis exists, and how it is found."
						summary={updateSummary}
						forceOpen={!!update?.available}
					>
						<div class="grid gap-4">
							{#if update}
								<div class={cn('flex items-start gap-3 rounded-lg border p-3', update.available ? 'border-primary/40 bg-primary/5' : 'border-border')} role="status">
									{#if update.available}
										<ArrowUpCircleIcon class="mt-0.5 size-5 shrink-0 text-primary" />
									{:else if update.error}
										<CircleXIcon class="mt-0.5 size-5 shrink-0 text-yellow-300" />
									{:else}
										<CircleCheckIcon class="mt-0.5 size-5 shrink-0 text-emerald-400" />
									{/if}
									<div class="min-w-0 text-sm">
										{#if update.available}
											<p class="font-medium">Themis {update.latest} is available</p>
											<p class="text-muted-foreground">You have {update.current}. On the server, run <code class="rounded bg-muted px-1.5 py-0.5 font-mono text-xs">themis upgrade</code>: it makes a backup first and goes back by itself if the new version does not start.</p>
											{#if update.url}<a href={update.url} target="_blank" rel="noreferrer" class="text-primary underline underline-offset-2">What is new in {update.latest}</a>{/if}
										{:else if update.kind === 'checkout'}
											<p class="font-medium">This is a development checkout</p>
											<p class="text-muted-foreground">It is run from the source code, so it is updated with <code>git pull</code>, not <code>themis upgrade</code>. The newest release is {update.latest || 'not known yet'}.</p>
										{:else if update.error}
											<p class="font-medium">Could not check for updates</p>
											<p class="break-words text-muted-foreground">{update.error}</p>
										{:else if !update.enabled}
											<p class="font-medium">Checking is switched off</p>
											<p class="text-muted-foreground">You have {update.current}. Look for new versions yourself with <code>themis upgrade --check</code>.</p>
										{:else}
											<p class="font-medium">You have the newest version, {update.current}</p>
											<p class="text-muted-foreground">{update.checked_at ? `Checked ${relative(update.checked_at)}.` : 'Not checked yet: it is done a minute after Themis starts, then daily.'}</p>
										{/if}
									</div>
									<Button type="button" variant="ghost" size="icon" class="ms-auto shrink-0" aria-label="Check now" disabled={checkingUpdates || !update.enabled} onclick={checkUpdatesNow}>
										<RefreshCwIcon class={checkingUpdates ? 'animate-spin' : ''} />
									</Button>
								</div>
							{/if}
							<div class="flex items-start justify-between gap-4">
								<div class="grid gap-1">
									<Label for="check-updates">Look for new versions</Label>
									<p class="text-xs text-muted-foreground">
										Once a day Themis asks GitHub for the list of releases. That is all: nothing about you, your projects or this machine is sent. Nothing is installed by itself.
									</p>
								</div>
								<Switch id="check-updates" bind:checked={form.check_for_updates} />
							</div>
							<div class="grid gap-2 sm:max-w-xs">
								<Label for="update-channel">Which versions</Label>
								<Select.Root type="single" bind:value={form.update_channel}>
									<Select.Trigger id="update-channel" class="w-full" disabled={!form.check_for_updates}>{form.update_channel === 'beta' ? 'Stable and beta' : 'Stable only'}</Select.Trigger>
									<Select.Content>
										<Select.Item value="stable" label="Stable only">Stable only</Select.Item>
										<Select.Item value="beta" label="Stable and beta">Stable and beta</Select.Item>
									</Select.Content>
								</Select.Root>
								<p class="text-xs text-muted-foreground">Beta versions are previews: they may have rough edges.</p>
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

					</div>

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

			{/if}
			{#if system}
				<!-- which build this is: what to quote in a bug report, and the doctor (themis doctor) prints the same -->
				<p class="px-1 pt-1 text-xs text-muted-foreground">Themis {system.version}</p>
			{/if}
		</div>
	{/if}
</div>
