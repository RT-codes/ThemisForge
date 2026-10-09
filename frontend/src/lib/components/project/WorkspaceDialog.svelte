<script lang="ts">
	import { api, ApiError, type Workspace } from '$lib/api'
	import IconField from '$lib/components/IconField.svelte'
	import LayersIcon from '@lucide/svelte/icons/layers'
	import { Button } from '$lib/components/ui/button/index.js'
	import * as Dialog from '$lib/components/ui/dialog/index.js'
	import { Input } from '$lib/components/ui/input/index.js'
	import { Label } from '$lib/components/ui/label/index.js'
	import { Textarea } from '$lib/components/ui/textarea/index.js'

	// Create a workspace of a project, or edit one (`workspace`): its name, one line on what it is for, and a description.
	let {
		open = $bindable(false),
		projectId,
		workspace = null,
		onsaved,
	}: { open: boolean; projectId: number; workspace?: Workspace | null; onsaved: (workspace: Workspace) => void } = $props()

	let name = $state('')
	let purpose = $state('')
	let description = $state('')
	let icon = $state('')
	let error = $state('')
	let saving = $state(false)

	$effect(() => {
		if (open) {
			name = workspace?.name ?? ''
			purpose = workspace?.purpose ?? ''
			description = workspace?.description ?? ''
			icon = workspace?.icon ?? ''
			error = ''
		}
	})

	async function save(e: SubmitEvent) {
		e.preventDefault()
		error = ''
		saving = true
		try {
			const body = { name, purpose, description, icon }
			onsaved(workspace ? await api.updateWorkspace(workspace.id, body) : await api.createWorkspace(projectId, body))
			open = false
		} catch (err) {
			error = err instanceof ApiError || err instanceof Error ? err.message : 'Could not save the workspace'
		} finally {
			saving = false
		}
	}
</script>

<Dialog.Root bind:open>
	<Dialog.Content class="sm:max-w-lg">
		<Dialog.Header>
			<Dialog.Title>{workspace ? 'Edit workspace' : 'New workspace'}</Dialog.Title>
			<Dialog.Description>
				A workspace groups the boards of one area of the project, such as research or publishing. It only organises: tasks, schedules and agents stay shared across the project.
			</Dialog.Description>
		</Dialog.Header>
		<form onsubmit={save} class="grid gap-4">
			<div class="grid gap-2">
				<Label>Icon</Label>
				<IconField bind:value={icon} fallback={LayersIcon} />
			</div>
			<div class="grid gap-2">
				<Label for="workspace-name">Name</Label>
				<Input id="workspace-name" bind:value={name} required maxlength={60} placeholder="Product factory" />
			</div>
			<div class="grid gap-2">
				<Label for="workspace-purpose">What it is for</Label>
				<Input id="workspace-purpose" bind:value={purpose} maxlength={200} placeholder="Build, test and ship the product" />
			</div>
			<div class="grid gap-2">
				<Label for="workspace-description">Description</Label>
				<Textarea id="workspace-description" bind:value={description} rows={3} maxlength={5000} />
			</div>
			{#if error}<p class="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive" role="alert">{error}</p>{/if}
			<Dialog.Footer>
				<Button type="button" variant="ghost" onclick={() => (open = false)}>Cancel</Button>
				<Button type="submit" disabled={saving || !name.trim()}>{workspace ? 'Save' : 'Create'}</Button>
			</Dialog.Footer>
		</form>
	</Dialog.Content>
</Dialog.Root>
