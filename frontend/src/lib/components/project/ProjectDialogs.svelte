<script lang="ts">
	import { projectsApi, type Project } from '$lib/api/projects'
	import * as AlertDialog from '$lib/components/ui/alert-dialog/index.js'
	import { projects } from '$lib/projects.svelte'
	import { router } from '$lib/router.svelte'
	import PropertiesDialog from './PropertiesDialog.svelte'

	// The dialogs behind a project's Settings page: its task properties, and deleting it.
	let {
		project,
		propsOpen = $bindable(false),
		deleteOpen = $bindable(false),
		onchanged,
	}: {
		project: Project
		propsOpen: boolean
		deleteOpen: boolean
		/** the properties were edited: the page reloads */
		onchanged: () => void
	} = $props()

	let deleteError = $state('')

	$effect(() => {
		if (deleteOpen) deleteError = ''
	})

	async function deleteProject() {
		deleteError = ''
		try {
			await projectsApi.deleteProject(project.id)
			await projects.refresh()
			deleteOpen = false
			router.navigate('/')
		} catch (e) {
			deleteError = e instanceof Error ? e.message : 'Could not delete the project'
		}
	}
</script>

<PropertiesDialog bind:open={propsOpen} projectId={project.id} defs={project.properties} onsaved={onchanged} />

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
