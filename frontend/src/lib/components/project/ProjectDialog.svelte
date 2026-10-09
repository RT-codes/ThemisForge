<script lang="ts">
	import { api, ApiError, type CellDefaults, type ProfileOverrides, type Project } from '$lib/api'
	import CellChoice from '$lib/components/CellChoice.svelte'
	import GuardFields from '$lib/components/GuardFields.svelte'
	import { Button } from '$lib/components/ui/button/index.js'
	import * as Dialog from '$lib/components/ui/dialog/index.js'
	import { Input } from '$lib/components/ui/input/index.js'
	import { Label } from '$lib/components/ui/label/index.js'
	import { Textarea } from '$lib/components/ui/textarea/index.js'
	import { untrack } from 'svelte'

	let {
		open = $bindable(false),
		project = null,
		onsaved,
	}: { open: boolean; project?: Project | null; onsaved: (project: Project) => void } = $props()

	let name = $state('')
	let description = $state('')
	let profile = $state<ProfileOverrides | null>(null)
	let cooldown = $state<number | null>(null)
	let hops = $state<number | null>(null)
	let formVersion = $state(0) // bumped each time the dialog opens, so the cell control starts from this project
	let defaults = $state<CellDefaults | null>(null)
	let error = $state('')
	let saving = $state(false)

	$effect(() => {
		if (open) {
			name = project?.name ?? ''
			description = project?.description ?? ''
			profile = project?.cell_profile ? { ...project.cell_profile } : null
			cooldown = project?.automation?.start_cooldown_seconds ?? null
			hops = project?.automation?.max_hops ?? null
			untrack(() => formVersion++)
			error = ''
			api.systemStatus().then((s) => (defaults = s.cell_defaults)).catch(() => {}) // only fills the placeholders
		}
	})

	async function save(e: SubmitEvent) {
		e.preventDefault()
		error = ''
		saving = true
		try {
			const saved = project
				? await api.updateProject(project.id, { name, description, cell_profile: profile, automation: cooldown === null && hops === null ? null : { start_cooldown_seconds: cooldown, max_hops: hops } })
				: await api.createProject(name, description, profile)
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
	<Dialog.Content class="sm:max-w-lg">
		<Dialog.Header>
			<Dialog.Title>{project ? 'Edit project' : 'New project'}</Dialog.Title>
			<Dialog.Description>
				{project ? 'Rename the project or change what it is about.' : 'A project is one agentic system: its tasks, boards and schedules.'}
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
			{#if project}
				<div class="grid gap-2">
					<Label>Automation guard</Label>
					<p class="-mt-1 text-xs text-muted-foreground">Keeps workflows from moving the same task around for ever. Empty boxes use the values from Settings; a single task can set its own.</p>
					<GuardFields bind:cooldown bind:hops prefix="project" fallback="Settings" />
				</div>
			{/if}
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
