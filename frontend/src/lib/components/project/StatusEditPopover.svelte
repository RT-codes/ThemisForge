<script lang="ts">
	import { api, ApiError, type Board } from '$lib/api'
	import { customId, type ColumnInfo } from '$lib/boards'
	import ColorPicker from '$lib/components/ColorPicker.svelte'
	import IconField from '$lib/components/IconField.svelte'
	import StatusIcon from '$lib/components/StatusIcon.svelte'
	import { Button } from '$lib/components/ui/button/index.js'
	import { Input } from '$lib/components/ui/input/index.js'
	import { Label } from '$lib/components/ui/label/index.js'
	import { Textarea } from '$lib/components/ui/textarea/index.js'
	import BoxIcon from '@lucide/svelte/icons/box'
	import LockIcon from '@lucide/svelte/icons/lock'
	import PencilIcon from '@lucide/svelte/icons/pencil'
	import { Popover } from 'bits-ui'

	// The pencil on a column: a small popup to edit the status. A status of your own can change its icon, name, colour and
	// what it is for. A built-in status is the same on every board, so the popup only shows it, locked.
	let {
		boardId,
		column,
		onchange,
	}: {
		boardId: number
		column: ColumnInfo
		/** the board after the change, with its new columns */
		onchange: (board: Board) => void
	} = $props()

	let open = $state(false)
	let name = $state('')
	let icon = $state('')
	let color = $state<string | undefined>(undefined)
	let description = $state('')
	let error = $state('')
	let saving = $state(false)

	const id = $derived(customId(column.id))

	$effect(() => {
		if (open) {
			name = column.label
			icon = column.icon
			color = column.color ?? undefined
			description = column.description
			error = ''
		}
	})

	async function save(e: SubmitEvent) {
		e.preventDefault()
		if (id === null) return
		saving = true
		error = ''
		try {
			onchange(await api.updateStatus(boardId, id, { name: name.trim(), icon, color: color ?? null, description }))
			open = false
		} catch (err) {
			error = err instanceof ApiError || err instanceof Error ? err.message : 'Could not save'
		} finally {
			saving = false
		}
	}
</script>

<Popover.Root bind:open>
	<Popover.Trigger
		class="rounded-md p-1 text-muted-foreground transition-colors hover:bg-accent hover:text-foreground data-[state=open]:bg-accent data-[state=open]:text-foreground"
		aria-label="Edit {column.label}"
		title="Edit {column.label}"
	>
		<PencilIcon class="size-4" />
	</Popover.Trigger>
	<Popover.Portal>
		<Popover.Content
			align="start"
			sideOffset={6}
			collisionPadding={12}
			class="data-open:animate-in data-closed:animate-out data-closed:fade-out-0 data-open:fade-in-0 data-closed:zoom-out-95 data-open:zoom-in-95 z-[60] w-80 rounded-lg border bg-popover p-3 text-popover-foreground shadow-float outline-none"
		>
			{#if id === null}
				<!-- a built-in status: shown, not changed -->
				<div class="grid gap-3">
					<p class="flex items-center gap-1.5 text-sm font-medium">Edit status <LockIcon class="size-3.5 text-muted-foreground" aria-label="Built-in" /></p>
					<div class="grid gap-1.5">
						<Label>Icon</Label>
						<div class="flex h-10 items-center gap-2.5 rounded-md border bg-muted/30 px-3 text-sm text-muted-foreground"><StatusIcon status={column.id} class="size-5" /> Fixed</div>
					</div>
					<div class="grid gap-1.5">
						<Label for="status-name-fixed">Name</Label>
						<Input id="status-name-fixed" value={column.label} disabled />
					</div>
					<div class="grid gap-1.5">
						<Label>What it is for</Label>
						<p class="rounded-md bg-muted/30 px-3 py-2 text-xs text-muted-foreground">{column.hint}</p>
					</div>
					<p class="text-xs text-muted-foreground">The seven built-in statuses are the same on every board, so their icon, name and meaning cannot be changed. Add a status of your own for anything else.</p>
					<div class="flex justify-end"><Button type="button" variant="ghost" size="sm" onclick={() => (open = false)}>Close</Button></div>
				</div>
			{:else}
				<form onsubmit={save} class="grid gap-3">
					<p class="text-sm font-medium">Edit status</p>
					<div class="grid gap-1.5">
						<Label>Icon</Label>
						<IconField bind:value={icon} fallback={BoxIcon} />
					</div>
					<div class="grid gap-1.5">
						<Label for="status-name">Name</Label>
						<div class="flex items-center gap-2">
							<ColorPicker value={color} label="Colour of the status" onchange={(c) => (color = c)} />
							<Input id="status-name" bind:value={name} required maxlength={40} />
						</div>
					</div>
					<div class="grid gap-1.5">
						<Label for="status-description">What it is for</Label>
						<Textarea id="status-description" bind:value={description} rows={3} maxlength={300} placeholder="Shown when someone points at the (i) of this status" />
					</div>
					{#if error}<p class="rounded-md bg-destructive/10 px-3 py-2 text-xs text-destructive" role="alert">{error}</p>{/if}
					<div class="flex justify-end gap-2">
						<Button type="button" variant="ghost" size="sm" onclick={() => (open = false)}>Cancel</Button>
						<Button type="submit" size="sm" disabled={saving || !name.trim()}>Save</Button>
					</div>
				</form>
			{/if}
		</Popover.Content>
	</Popover.Portal>
</Popover.Root>
