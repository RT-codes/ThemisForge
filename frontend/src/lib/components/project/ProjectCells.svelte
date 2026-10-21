<script lang="ts">
	import { ApiError } from '$lib/api/core'
	import { projectsApi, type Project } from '$lib/api/projects'
	import { settingsApi, type CellDefaults, type ProfileOverrides } from '$lib/api/settings'
	import CellChoice from '$lib/components/CellChoice.svelte'
	import GuardFields from '$lib/components/GuardFields.svelte'
	import { Button } from '$lib/components/ui/button/index.js'
	import { Label } from '$lib/components/ui/label/index.js'
	import { onMount, untrack } from 'svelte'

	// How this project's work runs: the size of its cells, and the guard that stops workflows from moving a task around
	// for ever. Empty values use what Settings says, which is shown as the placeholder.
	let { project, onsaved }: { project: Project; onsaved: () => void } = $props()

	let profile = $state<ProfileOverrides | null>(untrack(() => (project.cell_profile ? { ...project.cell_profile } : null)))
	let cooldown = $state<number | null>(untrack(() => project.automation?.start_cooldown_seconds ?? null))
	let hops = $state<number | null>(untrack(() => project.automation?.max_hops ?? null))
	let defaults = $state<CellDefaults | null>(null)
	let error = $state('')
	let saving = $state(false)
	let justSaved = $state(false)

	onMount(() => {
		settingsApi.systemStatus().then((s) => (defaults = s.cell_defaults)).catch(() => {}) // only fills the placeholders
	})

	const guard = () => (cooldown === null && hops === null ? null : { start_cooldown_seconds: cooldown, max_hops: hops })
	const dirty = $derived(
		JSON.stringify([profile, guard()]) !== JSON.stringify([project.cell_profile, project.automation ? { start_cooldown_seconds: project.automation.start_cooldown_seconds ?? null, max_hops: project.automation.max_hops ?? null } : null]),
	)

	async function save(e: SubmitEvent) {
		e.preventDefault()
		error = ''
		saving = true
		try {
			await projectsApi.updateProject(project.id, { cell_profile: profile, automation: guard() })
			onsaved()
			justSaved = true
			setTimeout(() => (justSaved = false), 2500)
		} catch (err) {
			error = err instanceof ApiError || err instanceof Error ? err.message : 'Could not save'
		} finally {
			saving = false
		}
	}
</script>

<form onsubmit={save} class="grid gap-5">
	<div class="grid gap-2">
		<Label>Cell</Label>
		<p class="-mt-1 text-xs text-muted-foreground">The container this project's tasks run in. Agents can still ask for something different.</p>
		<CellChoice
			bind:value={profile}
			inherited={defaults}
			source="the default from Settings"
			prefix="project"
			imagePlaceholder={defaults ? `${defaults.image} (agents bring their own)` : ''}
		/>
	</div>
	<div class="grid gap-2">
		<Label>Automation guard</Label>
		<p class="-mt-1 text-xs text-muted-foreground">Keeps workflows from moving the same task around for ever. Empty boxes use the values from Settings; a single task can set its own.</p>
		<GuardFields bind:cooldown bind:hops prefix="project" fallback="Settings" />
	</div>
	{#if error}<p class="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive" role="alert">{error}</p>{/if}
	<div class="flex items-center justify-end gap-3">
		{#if justSaved}<span class="text-sm text-muted-foreground" role="status">Saved</span>{/if}
		<Button type="submit" disabled={saving || !dirty}>Save</Button>
	</div>
</form>
