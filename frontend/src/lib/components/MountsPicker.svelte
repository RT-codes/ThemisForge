<script lang="ts">
	import { api, type MountRef, type Volume } from '$lib/api'
	import { Checkbox } from '$lib/components/ui/checkbox/index.js'
	import * as Select from '$lib/components/ui/select/index.js'
	import FolderIcon from '@lucide/svelte/icons/folder'
	import { onMount } from 'svelte'

	// Which of a project's shared folders a cell gets, and whether it may change them. The project's own `shared`
	// folder is always mounted, so it is listed as something that is already there.
	let { projectId, value = $bindable([]), onchange }: { projectId: number; value?: MountRef[]; onchange?: (value: MountRef[]) => void } = $props()
	const update = (next: MountRef[]) => ((value = next), onchange?.(next))

	let volumes = $state<Volume[]>([])
	let loaded = $state(false)

	onMount(async () => {
		try {
			volumes = await api.volumes(projectId)
		} catch {
			// the list only fills the picker
		} finally {
			loaded = true
		}
	})

	const chosen = (v: Volume) => value.find((m) => m.volume_id === v.id)
	function toggle(v: Volume, on: boolean) {
		update(on ? [...value, { volume_id: v.id, mode: v.mode === 'ro' ? 'ro' : 'rw' }] : value.filter((m) => m.volume_id !== v.id))
	}
	function setMode(v: Volume, mode: 'ro' | 'rw') {
		update(value.map((m) => (m.volume_id === v.id ? { ...m, mode } : m)))
	}
	const label = (m: 'ro' | 'rw') => (m === 'ro' ? 'Read only' : 'Read and write')
</script>

<div class="grid gap-2">
	{#each volumes as v (v.id)}
		<div class="flex flex-wrap items-center gap-x-3 gap-y-2 rounded-lg border px-3 py-2">
			{#if v.is_default}
				<FolderIcon class="size-4 shrink-0 text-muted-foreground" />
			{:else}
				<Checkbox checked={!!chosen(v)} onCheckedChange={(on) => toggle(v, !!on)} aria-label="Mount {v.name}" disabled={!!v.problem} />
			{/if}
			<div class="min-w-0 flex-1 basis-32">
				<p class="truncate font-mono text-sm">/workspace/{v.name}</p>
				{#if v.problem}
					<p class="text-xs text-destructive">{v.problem}</p>
				{:else if v.is_default}
					<p class="text-xs text-muted-foreground">Always there, for handing files between runs</p>
				{/if}
			</div>
			{#if chosen(v) && !v.problem}
				<Select.Root type="single" value={chosen(v)!.mode} onValueChange={(m) => setMode(v, m as 'ro' | 'rw')}>
					<Select.Trigger size="sm" class="w-40" aria-label="Access to {v.name}">{label(chosen(v)!.mode)}</Select.Trigger>
					<Select.Content>
						<Select.Item value="rw" label="Read and write" disabled={v.mode === 'ro' || !v.can_write}>Read and write</Select.Item>
						<Select.Item value="ro" label="Read only">Read only</Select.Item>
					</Select.Content>
				</Select.Root>
			{/if}
		</div>
	{:else}
		{#if loaded}<p class="text-sm text-muted-foreground">No folders yet.</p>{/if}
	{/each}
	{#if loaded && volumes.length <= 1}
		<p class="text-xs text-muted-foreground">Add more folders under <a class="text-primary hover:underline" href="/projects/{projectId}#folders">Shared folders</a> on the project overview.</p>
	{/if}
</div>
