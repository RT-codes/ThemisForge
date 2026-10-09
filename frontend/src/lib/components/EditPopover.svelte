<script lang="ts" module>
	export type Details = { name: string; purpose: string; description: string; icon: string }
</script>

<script lang="ts">
	import type { Component } from 'svelte'
	import IconField from '$lib/components/IconField.svelte'
	import { Button } from '$lib/components/ui/button/index.js'
	import { Input } from '$lib/components/ui/input/index.js'
	import { Label } from '$lib/components/ui/label/index.js'
	import { Textarea } from '$lib/components/ui/textarea/index.js'
	import { cn } from '$lib/utils'
	import PencilIcon from '@lucide/svelte/icons/pencil'
	import { Popover } from 'bits-ui'

	// The pencil beside a project or a workspace in the sidebar: a small popup, right where it was clicked, with the
	// basics (icon, name, what it is for, description). It is for quick edits; the pages have the rest.
	let {
		kind,
		current,
		fallback,
		onsave,
		class: className,
	}: {
		kind: 'project' | 'workspace'
		current: Details
		/** the icon of this kind when none is chosen */
		// eslint-disable-next-line @typescript-eslint/no-explicit-any
		fallback: Component<any>
		onsave: (details: Details) => Promise<void>
		class?: string
	} = $props()

	let open = $state(false)
	let form = $state<Details>({ name: '', purpose: '', description: '', icon: '' })
	let error = $state('')
	let saving = $state(false)

	$effect(() => {
		if (open) {
			form = { ...current }
			error = ''
		}
	})

	async function save(e: SubmitEvent) {
		e.preventDefault()
		saving = true
		error = ''
		try {
			await onsave({ ...form, name: form.name.trim() })
			open = false
		} catch (err) {
			error = err instanceof Error ? err.message : 'Could not save'
		} finally {
			saving = false
		}
	}
</script>

<Popover.Root bind:open>
	<Popover.Trigger
		aria-label="Edit {kind} {current.name}"
		title="Edit {kind}"
		class={cn(
			'absolute flex size-5 items-center justify-center rounded-md text-sidebar-foreground/70 opacity-0 transition-[opacity,color,background-color] outline-hidden hover:bg-sidebar-accent hover:text-primary focus-visible:opacity-100 focus-visible:ring-2 focus-visible:ring-sidebar-ring data-[state=open]:bg-sidebar-accent data-[state=open]:text-primary data-[state=open]:opacity-100',
			className
		)}
	>
		<PencilIcon class="size-3.5" />
	</Popover.Trigger>
	<Popover.Portal>
		<Popover.Content
			side="right"
			align="start"
			sideOffset={10}
			collisionPadding={12}
			class="data-open:animate-in data-closed:animate-out data-closed:fade-out-0 data-open:fade-in-0 data-closed:zoom-out-95 data-open:zoom-in-95 z-[60] w-80 rounded-lg border bg-popover p-3 text-popover-foreground shadow-float outline-none"
		>
			<form onsubmit={save} class="grid gap-3">
				<p class="text-sm font-medium">Edit {kind}</p>
				<div class="grid gap-1.5">
					<Label>Icon</Label>
					<IconField bind:value={form.icon} {fallback} />
				</div>
				<div class="grid gap-1.5">
					<Label for="edit-{kind}-name">Name</Label>
					<Input id="edit-{kind}-name" bind:value={form.name} required maxlength={kind === 'project' ? 100 : 60} />
				</div>
				<div class="grid gap-1.5">
					<Label for="edit-{kind}-purpose">What it is for</Label>
					<Input id="edit-{kind}-purpose" bind:value={form.purpose} maxlength={200} placeholder="One line" />
				</div>
				<div class="grid gap-1.5">
					<Label for="edit-{kind}-description">Description</Label>
					<Textarea id="edit-{kind}-description" bind:value={form.description} rows={3} maxlength={kind === 'project' ? 2000 : 5000} />
				</div>
				{#if error}<p class="rounded-md bg-destructive/10 px-3 py-2 text-xs text-destructive" role="alert">{error}</p>{/if}
				<div class="flex justify-end gap-2">
					<Button type="button" variant="ghost" size="sm" onclick={() => (open = false)}>Cancel</Button>
					<Button type="submit" size="sm" disabled={saving || !form.name.trim()}>Save</Button>
				</div>
			</form>
		</Popover.Content>
	</Popover.Portal>
</Popover.Root>
