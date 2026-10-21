<script lang="ts">
	import { ApiError } from '$lib/api/core'
	import { projectsApi, type Project } from '$lib/api/projects'
	import { settingsApi, type CellDefaults, type ProfileOverrides } from '$lib/api/settings'
	import CellChoice from '$lib/components/CellChoice.svelte'
	import IconField from '$lib/components/IconField.svelte'
	import FolderKanbanIcon from '@lucide/svelte/icons/folder-kanban'
	import { Button } from '$lib/components/ui/button/index.js'
	import * as Dialog from '$lib/components/ui/dialog/index.js'
	import { Input } from '$lib/components/ui/input/index.js'
	import { Label } from '$lib/components/ui/label/index.js'
	import { Textarea } from '$lib/components/ui/textarea/index.js'
	import { untrack } from 'svelte'

	// Makes a new project. A project that exists is edited on its Settings page, so this dialog only creates.
	let {
		open = $bindable(false),
		onsaved,
	}: { open: boolean; onsaved: (project: Project) => void } = $props()

	let name = $state('')
	let purpose = $state('')
	let description = $state('')
	let icon = $state('')
	let profile = $state<ProfileOverrides | null>(null)
	let formVersion = $state(0) // bumped each time the dialog opens, so the cell control starts from this project
	let defaults = $state<CellDefaults | null>(null)
	let error = $state('')
	let saving = $state(false)

	$effect(() => {
		if (open) {
			name = purpose = description = icon = ''
			profile = null
			untrack(() => formVersion++)
			error = ''
			settingsApi.systemStatus().then((s) => (defaults = s.cell_defaults)).catch(() => {}) // only fills the placeholders
		}
	})

	async function save(e: SubmitEvent) {
		e.preventDefault()
		error = ''
		saving = true
		try {
			onsaved(await projectsApi.createProject({ name, purpose, description, icon, cell_profile: profile }))
			open = false
		} catch (err) {
			error = err instanceof ApiError || err instanceof Error ? err.message : 'Could not save the project'
		} finally {
			saving = false
		}
	}
</script>

<Dialog.Root bind:open>
	<Dialog.Content class="sm:max-w-lg">
		<Dialog.Header>
			<Dialog.Title>New project</Dialog.Title>
			<Dialog.Description>A project is one agentic system: its tasks, boards and schedules.</Dialog.Description>
		</Dialog.Header>
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
			<div class="grid gap-2">
				<Label>Cell</Label>
				<p class="-mt-1 text-xs text-muted-foreground">The container this project's tasks run in. Agents can still ask for something different.</p>
				{#key formVersion}
					<CellChoice
						bind:value={profile}
						inherited={defaults}
						source="the default from Settings"
						prefix="project"
						imagePlaceholder={defaults ? `${defaults.image} (agents bring their own)` : ''}
					/>
				{/key}
			</div>
			{#if error}
				<p class="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive" role="alert">{error}</p>
			{/if}
			<Dialog.Footer>
				<Button type="button" variant="ghost" onclick={() => (open = false)}>Cancel</Button>
				<Button type="submit" disabled={saving || !name.trim()}>Create project</Button>
			</Dialog.Footer>
		</form>
	</Dialog.Content>
</Dialog.Root>
