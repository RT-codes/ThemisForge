<script lang="ts">
	import { api, type Project } from '$lib/api'
	import * as AlertDialog from '$lib/components/ui/alert-dialog/index.js'
	import { projects } from '$lib/projects.svelte'
	import { router } from '$lib/router.svelte'
	import ProjectDialog from './ProjectDialog.svelte'
	import PropertiesDialog from './PropertiesDialog.svelte'

	// The dialogs behind a project's "..." menu (edit it, its task properties, delete it), so every page that offers that
	// menu opens the same ones.
	let {
		project,
		editOpen = $bindable(false),
		propsOpen = $bindable(false),
		deleteOpen = $bindable(false),
		onchanged,
	}: {
		project: Project
		editOpen: boolean
		propsOpen: boolean
		deleteOpen: boolean
		/** the project was edited: the page reloads */
		onchanged: () => void
	} = $props()

	let deleteError = $state('')

	$effect(() => {
		if (deleteOpen) deleteError = ''
	})

	async function deleteProject() {
		deleteError = ''
		try {
			await api.deleteProject(project.id)
			await projects.refresh()
			deleteOpen = false
			router.navigate('/')
		} catch (e) {
			deleteError = e instanceof Error ? e.message : 'Could not delete the project'
		}
	}
</script>

<PropertiesDialog bind:open={propsOpen} projectId={project.id} defs={project.properties} onsaved={onchanged} />
<ProjectDialog bind:open={editOpen} {project} onsaved={onchanged} />

<AlertDialog.Root bind:open={deleteOpen}>
	<AlertDialog.Content>
		<AlertDialog.Header>
			<AlertDialog.Title>Delete "{project.name}"?</AlertDialog.Title>
			<AlertDialog.Description>
				All of its tasks and their history are removed permanently. The project's files on disk are kept.
			</AlertDialog.Description>
		</AlertDialog.Header>
		{#if deleteError}<p class="text-sm text-destructive" role="alert">{deleteError}</p>{/if}
		<AlertDialog.Footer>
			<AlertDialog.Cancel>Keep it</AlertDialog.Cancel>
			<AlertDialog.Action onclick={(e) => (e.preventDefault(), deleteProject())}>Delete project</AlertDialog.Action>
		</AlertDialog.Footer>
	</AlertDialog.Content>
</AlertDialog.Root>
