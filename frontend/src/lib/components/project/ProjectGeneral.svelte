<script lang="ts">
	import { ApiError } from '$lib/api/core'
	import { projectsApi, type Project } from '$lib/api/projects'
	import IconField from '$lib/components/IconField.svelte'
	import { Button } from '$lib/components/ui/button/index.js'
	import { Input } from '$lib/components/ui/input/index.js'
	import { Label } from '$lib/components/ui/label/index.js'
	import { Textarea } from '$lib/components/ui/textarea/index.js'
	import FolderKanbanIcon from '@lucide/svelte/icons/folder-kanban'
	import { untrack } from 'svelte'

	// Who the project is: its icon, name and what it is for. Saved here, on the project's Settings page.
	let { project, onsaved }: { project: Project; onsaved: () => void } = $props()

	let name = $state(untrack(() => project.name))
	let purpose = $state(untrack(() => project.purpose))
	let description = $state(untrack(() => project.description))
	let icon = $state(untrack(() => project.icon))
	let error = $state('')
	let saving = $state(false)
	let justSaved = $state(false)

	const dirty = $derived(
		name !== project.name || purpose !== project.purpose || description !== project.description || icon !== project.icon,
	)

	async function save(e: SubmitEvent) {
		e.preventDefault()
		error = ''
		saving = true
		try {
			await projectsApi.updateProject(project.id, { name, purpose, description, icon })
			onsaved()
			justSaved = true
			setTimeout(() => (justSaved = false), 2500)
		} catch (err) {
			error = err instanceof ApiError || err instanceof Error ? err.message : 'Could not save the project'
		} finally {
			saving = false
		}
	}
</script>

<form onsubmit={save} class="grid gap-4">
	<div class="grid gap-2">
		<Label>Icon</Label>
		<IconField bind:value={icon} fallback={FolderKanbanIcon} />
	</div>
	<div class="grid gap-2">
		<Label for="project-name">Name</Label>
		<Input id="project-name" bind:value={name} required maxlength={100} placeholder="e.g. Market research" />
	</div>
	<div class="grid gap-2">
		<Label for="project-purpose">What it is for</Label>
		<Input id="project-purpose" bind:value={purpose} maxlength={200} placeholder="One line, e.g. Find out what customers want" />
	</div>
	<div class="grid gap-2">
		<Label for="project-desc">Description</Label>
		<Textarea id="project-desc" bind:value={description} rows={3} maxlength={2000} placeholder="What is this project for?" />
	</div>
	{#if error}<p class="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive" role="alert">{error}</p>{/if}
	<div class="flex items-center justify-end gap-3">
		{#if justSaved}<span class="text-sm text-muted-foreground" role="status">Saved</span>{/if}
		<Button type="submit" disabled={saving || !dirty || !name.trim()}>Save</Button>
	</div>
</form>
