<script lang="ts">
	import { api, ApiError, type Volume } from '$lib/api'
	import * as AlertDialog from '$lib/components/ui/alert-dialog/index.js'
	import { Button } from '$lib/components/ui/button/index.js'
	import { Input } from '$lib/components/ui/input/index.js'
	import { Label } from '$lib/components/ui/label/index.js'
	import * as Select from '$lib/components/ui/select/index.js'
	import { Switch } from '$lib/components/ui/switch/index.js'
	import { router } from '$lib/router.svelte'
	import FolderIcon from '@lucide/svelte/icons/folder'
	import HardDriveIcon from '@lucide/svelte/icons/hard-drive'
	import PlusIcon from '@lucide/svelte/icons/plus'
	import Trash2Icon from '@lucide/svelte/icons/trash-2'
	import { onMount, tick } from 'svelte'
	import { slide } from 'svelte/transition'

	// The shared folders of a project: what cells can mount at /workspace/NAME, so runs can hand files to each other.
	let { projectId }: { projectId: number } = $props()

	let volumes = $state<Volume[]>([])
	let loaded = $state(false)
	let error = $state('')
	let section = $state<HTMLElement>()
	let doomed = $state<Volume | null>(null)
	let confirmOpen = $state(false)

	let adding = $state(false)
	let name = $state('')
	let kind = $state<'managed' | 'host'>('managed')
	let hostPath = $state('')
	let mode = $state<'ro' | 'rw'>('rw')
	let saving = $state(false)

	const modeLabel = (m: 'ro' | 'rw') => (m === 'ro' ? 'Read only' : 'Read and write')

	async function load() {
		try {
			volumes = await api.volumes(projectId)
			error = ''
		} catch (e) {
			error = e instanceof Error ? e.message : 'Could not load the folders'
		} finally {
			loaded = true
		}
	}

	onMount(() => {
		load().then(async () => {
			await tick()
			if (router.hash === 'folders') section?.scrollIntoView({ behavior: 'smooth' }) // arrived from a folder picker
		})
	})

	function startAdding() {
		name = hostPath = ''
		kind = 'managed'
		mode = 'rw'
		error = ''
		adding = true
	}

	async function add(e: SubmitEvent) {
		e.preventDefault()
		saving = true
		error = ''
		try {
			await api.createVolume(projectId, { name, kind, host_path: kind === 'host' ? hostPath : '', mode })
			adding = false
			await load()
		} catch (err) {
			error = err instanceof ApiError || err instanceof Error ? err.message : 'Could not add the folder'
		} finally {
			saving = false
		}
	}

	async function change(v: Volume, patch: { mode?: 'ro' | 'rw'; exclusive_write?: boolean }) {
		try {
			await api.updateVolume(v.id, patch)
			await load()
		} catch (err) {
			error = err instanceof ApiError || err instanceof Error ? err.message : 'Could not change the folder'
		}
	}

	async function remove() {
		const target = doomed
		confirmOpen = false
		if (!target) return
		try {
			await api.deleteVolume(target.id)
			await load()
		} catch (err) {
			error = err instanceof ApiError || err instanceof Error ? err.message : 'Could not remove the folder'
		}
	}
</script>

<section bind:this={section} id="folders" class="mt-6 scroll-mt-6 rounded-xl border bg-card">
	<div class="flex items-center gap-3 p-5 pb-3">
		<div class="min-w-0 flex-1">
			<h3 class="text-base font-semibold tracking-tight">Shared folders</h3>
			<p class="text-sm text-muted-foreground">
				Folders that outlive a run. Cells see them inside their workspace, so one agent can hand files to the next.
			</p>
		</div>
		{#if !adding}<Button size="sm" onclick={startAdding}><PlusIcon /> New folder</Button>{/if}
	</div>

	{#if error && !adding}<p class="px-5 pb-3 text-sm text-destructive" role="alert">{error}</p>{/if}

	{#if adding}
		<form onsubmit={add} class="mx-5 mb-4 grid gap-4 rounded-lg border bg-background/40 p-4" transition:slide={{ duration: 160 }}>
			<div class="grid items-start gap-4 sm:grid-cols-2">
				<div class="grid gap-1.5">
					<Label for="folder-name">Name</Label>
					<Input id="folder-name" bind:value={name} required maxlength={40} placeholder="e.g. reports" class="font-mono" />
					<p class="text-xs text-muted-foreground">Seen by cells as <span class="font-mono">/workspace/{name.trim().toLowerCase() || 'name'}</span></p>
				</div>
				<div class="grid gap-1.5">
					<Label for="folder-kind">Where it lives</Label>
					<Select.Root type="single" bind:value={kind}>
						<Select.Trigger id="folder-kind" class="w-full">{kind === 'managed' ? 'Managed by Themis' : 'A folder on this machine'}</Select.Trigger>
						<Select.Content>
							<Select.Item value="managed" label="Managed by Themis">Managed by Themis</Select.Item>
							<Select.Item value="host" label="A folder on this machine">A folder on this machine</Select.Item>
						</Select.Content>
					</Select.Root>
				</div>
			</div>
			{#if kind === 'host'}
				<div class="grid gap-1.5" transition:slide={{ duration: 160 }}>
					<Label for="folder-path">Folder</Label>
					<Input id="folder-path" bind:value={hostPath} required placeholder="/home/you/notes" class="font-mono" />
					<p class="text-xs text-muted-foreground">It must be inside a folder an administrator approved under Settings, Mount roots.</p>
				</div>
			{/if}
			<div class="grid gap-1.5">
				<Label for="folder-mode">Cells may</Label>
				<Select.Root type="single" bind:value={mode}>
					<Select.Trigger id="folder-mode" class="w-full sm:w-64">{modeLabel(mode)}</Select.Trigger>
					<Select.Content>
						<Select.Item value="rw" label="Read and write">Read and write</Select.Item>
						<Select.Item value="ro" label="Read only">Read only</Select.Item>
					</Select.Content>
				</Select.Root>
				{#if kind === 'host' && mode === 'rw'}
					<p class="text-xs text-yellow-300">Read and write lets an unattended agent change or delete the real files in that folder.</p>
				{/if}
			</div>
			{#if error}<p class="text-sm text-destructive" role="alert">{error}</p>{/if}
			<div class="flex justify-end gap-2">
				<Button type="button" variant="ghost" onclick={() => (adding = false)}>Cancel</Button>
				<Button type="submit" disabled={saving || !name.trim() || (kind === 'host' && !hostPath.trim())}>Add folder</Button>
			</div>
		</form>
	{/if}

	{#if !loaded}
		<p class="px-5 pb-5 text-sm text-muted-foreground">Loading...</p>
	{:else}
		<ul class="divide-y border-t">
			{#each volumes as v (v.id)}
				<li class="flex flex-wrap items-center gap-3 px-5 py-3" transition:slide={{ duration: 200 }}>
					<span class="flex size-8 shrink-0 items-center justify-center rounded-md bg-primary/15 text-primary">
						{#if v.kind === 'host'}<HardDriveIcon class="size-4" />{:else}<FolderIcon class="size-4" />{/if}
					</span>
					<div class="min-w-0 flex-1 basis-48">
						<p class="truncate font-mono text-sm font-medium">/workspace/{v.name}</p>
						<p class={v.problem ? 'truncate text-xs text-destructive' : 'truncate text-xs text-muted-foreground'}>
							{#if v.problem}{v.problem}{:else if v.kind === 'host'}{v.host_path}{:else if v.is_default}In every cell of this project{:else}Managed by Themis{/if}
						</p>
					</div>
					{#if v.mode === 'rw' && !v.problem}
						<label class="flex items-center gap-2 text-xs text-muted-foreground" title="Only one run at a time may write here; the others wait for their turn">
							<Switch checked={v.exclusive_write} onCheckedChange={(on) => change(v, { exclusive_write: on })} aria-label="Writers take turns in {v.name}" />
							Writers take turns
						</label>
					{/if}
					<Select.Root type="single" value={v.mode} onValueChange={(m) => change(v, { mode: m as 'ro' | 'rw' })}>
						<Select.Trigger size="sm" class="w-40" aria-label="Access to {v.name}">{modeLabel(v.mode)}</Select.Trigger>
						<Select.Content>
							<Select.Item value="rw" label="Read and write" disabled={!v.can_write}>Read and write</Select.Item>
							<Select.Item value="ro" label="Read only">Read only</Select.Item>
						</Select.Content>
					</Select.Root>
					<Button
						variant="ghost"
						size="icon-sm"
						aria-label={`Remove ${v.name}`}
						disabled={v.is_default}
						title={v.is_default ? 'Every project keeps its shared folder' : undefined}
						class="-me-2 shrink-0 text-muted-foreground/60 transition-colors hover:text-destructive"
						onclick={() => ((doomed = v), (confirmOpen = true))}
					>
						<Trash2Icon />
					</Button>
				</li>
			{/each}
		</ul>
	{/if}
</section>

<AlertDialog.Root bind:open={confirmOpen}>
	<AlertDialog.Content>
		<AlertDialog.Header>
			<AlertDialog.Title>Remove this folder?</AlertDialog.Title>
			<AlertDialog.Description>
				"{doomed?.name}" is taken away from this project and from the agents that mount it. The files stay where they are; nothing is deleted.
			</AlertDialog.Description>
		</AlertDialog.Header>
		<AlertDialog.Footer>
			<AlertDialog.Cancel>Keep it</AlertDialog.Cancel>
			<AlertDialog.Action onclick={remove}>Remove</AlertDialog.Action>
		</AlertDialog.Footer>
	</AlertDialog.Content>
</AlertDialog.Root>
