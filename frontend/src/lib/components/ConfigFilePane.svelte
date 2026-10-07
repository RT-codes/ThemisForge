<script lang="ts">
	import { api, ApiError, type FileEntry } from '$lib/api'
	import FilePreview from '$lib/components/FilePreview.svelte'
	import { isDirty, parentPath, type Draft } from '$lib/files'

	// One file of the project's config folder, shown and edited the way the Files page does (it is the same preview and
	// editor, saved through the same file API, so the server checks the file before it is stored). The parent decides
	// whether it may be edited and is told when there are unsaved changes, so it can ask before moving elsewhere.
	let {
		volumeId,
		path,
		canEdit = true,
		dirty = $bindable(false),
		onsaved,
	}: {
		volumeId: number
		path: string
		canEdit?: boolean
		dirty?: boolean
		onsaved?: () => void
	} = $props()

	let entry = $state<FileEntry | null>(null)
	let error = $state('')
	let draft = $state<Draft | null>(null)
	let saves = $state(0) // counts saves, so the preview reads the file again and shows what was written

	$effect(() => {
		dirty = isDirty(draft)
	})

	// found by listing its folder: the preview needs the file's size and modified time, which also tell it when to reload
	$effect(() => {
		void saves
		const file = path
		let stale = false
		error = ''
		api
			.listFiles(volumeId, parentPath(file))
			.then((got) => {
				const found = got?.listing.entries.find((e) => e.name === file.split('/').pop())
				if (stale) return
				if (found) entry = found
				else error = 'This file is not there any more'
			})
			.catch((e) => !stale && (error = e instanceof ApiError || e instanceof Error ? e.message : 'Could not open the file'))
		return () => (stale = true)
	})

	async function save(force: boolean) {
		const d = draft
		if (!d) return
		// refused with the reason when the file could not work (the server checks a skill, agent or tool file)
		await api.uploadFile(volumeId, d.path, new File([d.text], d.entry.name), true, force ? '' : d.entry.modified)
		draft = null
		saves += 1
		onsaved?.()
	}
</script>

<div class="relative min-h-0 flex-1">
	{#if error}
		<p class="m-4 text-sm text-destructive" role="alert">{error}</p>
	{:else if entry}
		{#key `${path}#${saves}`}
			<FilePreview {volumeId} {path} {entry} {canEdit} bind:draft onsave={save} onleave={() => (draft = null)} />
		{/key}
	{/if}
</div>
