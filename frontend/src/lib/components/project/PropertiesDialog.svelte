<script lang="ts">
	import { api, ApiError, type PropertyDef, type PropertyType } from '$lib/api'
	import { Button } from '$lib/components/ui/button/index.js'
	import * as Dialog from '$lib/components/ui/dialog/index.js'
	import { Input } from '$lib/components/ui/input/index.js'
	import * as Select from '$lib/components/ui/select/index.js'
	import { slug } from '$lib/format'
	import PlusIcon from '@lucide/svelte/icons/plus'
	import XIcon from '@lucide/svelte/icons/x'

	let {
		open = $bindable(false),
		projectId,
		defs,
		onsaved,
	}: { open: boolean; projectId: number; defs: PropertyDef[]; onsaved: () => void } = $props()

	type Row = PropertyDef & { optionsText: string; existing: boolean }
	let rows = $state<Row[]>([])
	let error = $state('')
	let saving = $state(false)

	const types: { id: PropertyType; label: string }[] = [
		{ id: 'text', label: 'Text' },
		{ id: 'number', label: 'Number' },
		{ id: 'select', label: 'Select' },
		{ id: 'checkbox', label: 'Checkbox' },
		{ id: 'date', label: 'Date' },
	]

	$effect(() => {
		if (open) {
			rows = defs.map((d) => ({ ...d, optionsText: d.options.join(', '), existing: true }))
			error = ''
		}
	})

	function add() {
		rows.push({ key: '', name: '', type: 'text', options: [], optionsText: '', existing: false })
	}

	async function save(e: SubmitEvent) {
		e.preventDefault()
		error = ''
		const used = new Set(rows.filter((r) => r.existing).map((r) => r.key))
		const out: PropertyDef[] = []
		for (const r of rows) {
			let key = r.key
			if (!r.existing) {
				const base = slug(r.name)
				key = base
				for (let i = 2; used.has(key); i++) key = `${base}_${i}`
				used.add(key)
			}
			out.push({
				key,
				name: r.name.trim(),
				type: r.type,
				options: r.type === 'select' ? r.optionsText.split(',').map((o) => o.trim()).filter(Boolean) : [],
			})
		}
		saving = true
		try {
			await api.updateProject(projectId, { properties: out })
			onsaved()
			open = false
		} catch (err) {
			error = err instanceof ApiError || err instanceof Error ? err.message : 'Could not save'
		} finally {
			saving = false
		}
	}
</script>

<Dialog.Root bind:open>
	<Dialog.Content class="sm:max-w-xl">
		<Dialog.Header>
			<Dialog.Title>Task properties</Dialog.Title>
			<Dialog.Description>
				Custom fields for every task in this project, shown on cards and in the list. Removing a property hides its values.
			</Dialog.Description>
		</Dialog.Header>
		<form onsubmit={save} class="grid gap-4">
			<div class="grid max-h-[50vh] gap-2 overflow-y-auto pe-1">
				{#each rows as row, i (i)}
					<div class="grid gap-2 rounded-lg border p-2.5">
						<div class="flex gap-2">
							<Input bind:value={row.name} placeholder="Name, e.g. Priority" required maxlength={60} aria-label="Property name" />
							<Select.Root type="single" bind:value={row.type}>
								<Select.Trigger class="w-32 shrink-0">{types.find((t) => t.id === row.type)?.label}</Select.Trigger>
								<Select.Content>
									{#each types as t (t.id)}
										<Select.Item value={t.id} label={t.label}>{t.label}</Select.Item>
									{/each}
								</Select.Content>
							</Select.Root>
							<Button type="button" variant="ghost" size="icon" aria-label="Remove property" onclick={() => rows.splice(i, 1)}>
								<XIcon />
							</Button>
						</div>
						{#if row.type === 'select'}
							<Input bind:value={row.optionsText} placeholder="Options, separated by commas" required aria-label="Options" />
						{/if}
					</div>
				{:else}
					<p class="rounded-lg border border-dashed py-8 text-center text-sm text-muted-foreground">No custom properties yet.</p>
				{/each}
			</div>
			<Button type="button" variant="outline" size="sm" class="justify-self-start" onclick={add}><PlusIcon /> Add property</Button>
			{#if error}
				<p class="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive" role="alert">{error}</p>
			{/if}
			<Dialog.Footer>
				<Button type="button" variant="ghost" onclick={() => (open = false)}>Cancel</Button>
				<Button type="submit" disabled={saving}>Save</Button>
			</Dialog.Footer>
		</form>
	</Dialog.Content>
</Dialog.Root>
