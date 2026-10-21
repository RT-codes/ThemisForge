<script lang="ts">
	import type { Volume } from '$lib/api/volumes'
	import { Button } from '$lib/components/ui/button/index.js'
	import * as Dialog from '$lib/components/ui/dialog/index.js'
	import { Input } from '$lib/components/ui/input/index.js'
	import VolumeControls from '$lib/components/VolumeControls.svelte'
	import { isValidFolderName } from '$lib/files'
	import { untrack } from 'svelte'

	// The settings of one shared folder: its name, and what cells may do in it. The page does the saving (and then
	// refreshes what it shows); this keeps the state of the name field.
	let {
		open = $bindable(false),
		volume,
		onrename,
		onchange,
	}: {
		open: boolean
		volume: Volume | null
		/** saves the new name; throws with the reason when the server refuses it */
		onrename: (name: string) => Promise<void>
		onchange: (patch: { mode?: 'ro' | 'rw'; exclusive_write?: boolean }) => void
	} = $props()

	// the name field starts from the folder's current name each time the dialog opens
	let newName = $state('')
	let renameError = $state('')
	let renaming = $state(false)
	$effect(() => {
		if (open) untrack(() => ((newName = volume?.name ?? ''), (renameError = ''))) // only when it opens
	})
	const renamable = $derived(!!volume && !volume.is_default)
	const nameChanged = $derived(!!volume && newName.trim().toLowerCase() !== volume.name)

	async function rename(e: SubmitEvent) {
		e.preventDefault()
		if (!volume || !isValidFolderName(newName)) return
		renaming = true
		renameError = ''
		try {
			await onrename(newName)
		} catch (err) {
			renameError = err instanceof Error ? err.message : 'Could not rename the folder'
		} finally {
			renaming = false
		}
	}
</script>

<Dialog.Root bind:open>
	<Dialog.Content class="sm:max-w-md">
		<Dialog.Header>
			<Dialog.Title>Settings of <span class="font-mono">{volume?.name}</span></Dialog.Title>
			<Dialog.Description>
				{#if volume?.kind === 'host'}{volume.host_path}{:else}Managed by Themis. Cells see it at <span class="font-mono">/workspace/{volume?.name}</span>.{/if}
			</Dialog.Description>
		</Dialog.Header>
		{#if volume}
			{#if volume.problem}<p class="text-sm text-destructive" role="alert">{volume.problem}</p>{/if}
			<form onsubmit={rename} class="grid gap-1.5">
				<label for="folder-rename" class="text-sm">Name</label>
				<div class="flex gap-2">
					<Input id="folder-rename" bind:value={newName} maxlength={40} class="font-mono" disabled={!renamable || renaming} />
					{#if renamable}
						<Button type="submit" variant="outline" disabled={renaming || !nameChanged || !isValidFolderName(newName)}>Rename</Button>
					{/if}
				</div>
				{#if renameError}
					<p class="text-xs text-destructive" role="alert">{renameError}</p>
				{:else if !renamable}
					<p class="text-xs text-muted-foreground">The shared folder keeps its name: every cell expects it.</p>
				{:else}
					<p class="text-xs text-muted-foreground">
						Cells will see it as <span class="font-mono">/workspace/{newName.trim().toLowerCase() || 'name'}</span>. Agents, workflows and runs keep the folder, but
						instructions, skills or scripts that mention the old name have to be changed by hand.
					</p>
				{/if}
			</form>
			<div class="flex flex-wrap items-center gap-3">
				<span class="text-sm">Cells may</span>
				<VolumeControls {volume} {onchange} />
			</div>
			<p class="text-xs text-muted-foreground">Removing a folder from the project is done in the project's Settings, under Shared folders. Its files are never deleted.</p>
		{/if}
	</Dialog.Content>
</Dialog.Root>
