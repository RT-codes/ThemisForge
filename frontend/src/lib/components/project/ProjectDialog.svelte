<script lang="ts">
	import { api, ApiError, type Project } from '$lib/api'
	import { Button } from '$lib/components/ui/button/index.js'
	import * as Dialog from '$lib/components/ui/dialog/index.js'
	import { Input } from '$lib/components/ui/input/index.js'
	import { Label } from '$lib/components/ui/label/index.js'
	import { Textarea } from '$lib/components/ui/textarea/index.js'

	let {
		open = $bindable(false),
		project = null,
		onsaved,
	}: { open: boolean; project?: Project | null; onsaved: (project: Project) => void } = $props()

	let name = $state('')
	let description = $state('')
	let error = $state('')
	let saving = $state(false)

	$effect(() => {
		if (open) {
			name = project?.name ?? ''
			description = project?.description ?? ''
			error = ''
		}
	})

	async function save(e: SubmitEvent) {
		e.preventDefault()
		error = ''
		saving = true
		try {
			const saved = project
				? await api.updateProject(project.id, { name, description })
				: await api.createProject(name, description)
			onsaved(saved)
			open = false
		} catch (err) {
			error = err instanceof ApiError || err instanceof Error ? err.message : 'Could not save the project'
		} finally {
			saving = false
		}
	}
</script>

<Dialog.Root bind:open>
	<Dialog.Content class="sm:max-w-md">
		<Dialog.Header>
			<Dialog.Title>{project ? 'Edit project' : 'New project'}</Dialog.Title>
			<Dialog.Description>
				{project ? 'Rename the project or change what it is about.' : 'A project is one agentic system: its tasks, schedules and workspace.'}
			</Dialog.Description>
		</Dialog.Header>
		<form onsubmit={save} class="grid gap-4">
			<div class="grid gap-2">
				<Label for="project-name">Name</Label>
				<Input id="project-name" bind:value={name} required maxlength={100} placeholder="e.g. Market research" />
			</div>
			<div class="grid gap-2">
				<Label for="project-desc">Description</Label>
				<Textarea id="project-desc" bind:value={description} rows={3} maxlength={2000} placeholder="What is this project for?" />
			</div>
			{#if error}
				<p class="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive" role="alert">{error}</p>
			{/if}
			<Dialog.Footer>
				<Button type="button" variant="ghost" onclick={() => (open = false)}>Cancel</Button>
				<Button type="submit" disabled={saving || !name.trim()}>{project ? 'Save' : 'Create project'}</Button>
			</Dialog.Footer>
		</form>
	</Dialog.Content>
</Dialog.Root>
