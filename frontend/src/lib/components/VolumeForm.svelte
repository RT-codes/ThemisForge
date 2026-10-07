<script lang="ts">
	import { api, ApiError, type Volume } from '$lib/api'
	import { Button } from '$lib/components/ui/button/index.js'
	import { Input } from '$lib/components/ui/input/index.js'
	import { Label } from '$lib/components/ui/label/index.js'
	import * as Select from '$lib/components/ui/select/index.js'
	import { accessLabel } from '$lib/format'
	import { slide } from 'svelte/transition'

	// The form for a new shared folder of a project. The overview and the Files page both use it.
	let { projectId, onadded, oncancel }: { projectId: number; onadded: (volume: Volume) => void; oncancel: () => void } = $props()

	let name = $state('')
	let kind = $state<'managed' | 'host'>('managed')
	let hostPath = $state('')
	let mode = $state<'ro' | 'rw'>('rw')
	let saving = $state(false)
	let error = $state('')

	async function add(e: SubmitEvent) {
		e.preventDefault()
		saving = true
		error = ''
		try {
			onadded(await api.createVolume(projectId, { name, kind, host_path: kind === 'host' ? hostPath : '', mode }))
		} catch (err) {
			error = err instanceof ApiError || err instanceof Error ? err.message : 'Could not add the folder'
		} finally {
			saving = false
		}
	}
</script>

<form onsubmit={add} class="grid gap-4">
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
			<Select.Trigger id="folder-mode" class="w-full sm:w-64">{accessLabel(mode)}</Select.Trigger>
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
		<Button type="button" variant="ghost" onclick={oncancel}>Cancel</Button>
		<Button type="submit" disabled={saving || !name.trim() || (kind === 'host' && !hostPath.trim())}>Add folder</Button>
	</div>
</form>
