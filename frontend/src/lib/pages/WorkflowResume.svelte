<script lang="ts">
	import { api } from '$lib/api'
	import { router } from '$lib/router.svelte'
	import { onMount } from 'svelte'

	// Opening "Workflow editor" lands on the workflow you edited last. Only a project without any workflow starts a new one.
	let { projectId }: { projectId: number } = $props()

	onMount(async () => {
		let target = `/projects/${projectId}/workflows/new`
		try {
			const latest = (await api.workflows(projectId)).toSorted((a, b) => b.updated_at.localeCompare(a.updated_at) || b.id - a.id)[0]
			if (latest) target = `/projects/${projectId}/workflows/${latest.id}`
		} catch {
			// the list could not be read: a blank workflow is still a way in
		}
		router.replace(target)
	})
</script>
