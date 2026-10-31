<script lang="ts">
	import { copiedColour, copyColour } from '$lib/colorClipboard'
	import { formatOklch, hexToOklch } from '$lib/colors'
	import { Button } from '$lib/components/ui/button/index.js'
	import { Input } from '$lib/components/ui/input/index.js'
	import { cleanPaletteName, MAX_PALETTE, MAX_PALETTE_NAME, newPaletteColor, type PaletteColor } from '$lib/themes'
	import { cn } from '$lib/utils'
	import CopyIcon from '@lucide/svelte/icons/copy'
	import PlusIcon from '@lucide/svelte/icons/plus'
	import Trash2Icon from '@lucide/svelte/icons/trash-2'

	// The colours saved with a theme, to reuse: up to MAX_PALETTE small boxes, each with a name. A box can be dragged onto any
	// colour of the editor, or picked up (it is copied) and pasted from a colour's menu. Colours are added here from the
	// menu of any colour ("Add to palette") or with the plus, which opens the colour picker.
	let { palette, onchange }: { palette: PaletteColor[]; onchange: (palette: PaletteColor[]) => void } = $props()

	let selectedId = $state<string | null>(null)
	const selected = $derived(palette.find((entry) => entry.id === selectedId) ?? null)
	const full = $derived(palette.length >= MAX_PALETTE)

	function select(entry: PaletteColor) {
		selectedId = entry.id
		copyColour(entry.color)
	}

	function add(hex: string) {
		const colour = hexToOklch(hex)
		if (!colour || full) return
		const entry = newPaletteColor(formatOklch(colour), `Colour ${palette.length + 1}`)
		onchange([...palette, entry])
		selectedId = entry.id
	}

	const rename = (id: string, name: string) => onchange(palette.map((entry) => (entry.id === id ? { ...entry, name: cleanPaletteName(name) || entry.name } : entry)))

	function remove(id: string) {
		onchange(palette.filter((entry) => entry.id !== id))
		selectedId = null
	}

	// the name is kept as typed in its own field so a trailing space is not eaten; empty names are not saved
	let nameDraft = $state('')
	$effect(() => {
		nameDraft = selected?.name ?? ''
	})
</script>

<section class="rounded-xl border bg-card p-4" aria-label="Palette">
	<div class="flex items-center justify-between gap-2">
		<h3 class="text-base font-semibold">Palette</h3>
		<span class="text-xs text-muted-foreground tabular-nums">{palette.length} / {MAX_PALETTE}</span>
	</div>
	<p class="mt-1 text-xs text-muted-foreground">Colours kept with this theme. Drag one onto a colour, or open a colour's menu and paste it.</p>

	<div class="mt-3 grid grid-cols-5 gap-2">
		{#each palette as entry (entry.id)}
			<button
				type="button"
				draggable="true"
				ondragstart={(e) => e.dataTransfer?.setData('text/plain', entry.color)}
				onclick={() => select(entry)}
				title="{entry.name}: {entry.color}"
				aria-label={entry.name}
				aria-pressed={selectedId === entry.id}
				class={cn('relative aspect-square cursor-grab overflow-hidden rounded-md border focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none', selectedId === entry.id && 'ring-2 ring-primary')}
			>
				<span class="absolute inset-0 bg-[repeating-conic-gradient(var(--muted)_0%_25%,transparent_0%_50%)] bg-size-[8px_8px]"></span>
				<span class="absolute inset-0" style="background-color: {entry.color}"></span>
			</button>
		{/each}
		{#if !full}
			<label class="relative flex aspect-square cursor-pointer items-center justify-center rounded-md border border-dashed text-muted-foreground hover:border-foreground/40 hover:text-foreground focus-within:ring-2 focus-within:ring-ring" title="Add a colour">
				<PlusIcon class="size-4" />
				<input type="color" class="absolute inset-0 size-full cursor-pointer opacity-0" aria-label="Add a colour to the palette" onchange={(e) => add(e.currentTarget.value)} />
			</label>
		{/if}
	</div>

	{#if full}
		<p class="mt-2 text-xs text-muted-foreground">The palette is full. Delete a colour to make room.</p>
	{:else if palette.length === 0}
		<p class="mt-3 text-xs text-muted-foreground">Nothing here yet. Use a colour's menu, or the plus.</p>
	{/if}

	{#if selected}
		<div class="mt-4 space-y-2 border-t pt-3">
			<Input
				value={nameDraft}
				maxlength={MAX_PALETTE_NAME}
				aria-label="Colour name"
				oninput={(e) => {
					nameDraft = e.currentTarget.value
					if (nameDraft.trim()) rename(selected.id, nameDraft)
				}}
				onblur={() => (nameDraft = selected?.name ?? '')}
				class="h-8"
			/>
			<div class="truncate font-mono text-xs text-muted-foreground" title={selected.color}>{selected.color}</div>
			<div class="flex gap-2">
				<Button variant="outline" size="sm" class="h-7 text-xs" onclick={() => copyColour(selected.color)}><CopyIcon /> {$copiedColour === selected.color ? 'Copied' : 'Copy'}</Button>
				<Button variant="outline" size="sm" class="h-7 text-xs text-destructive hover:text-destructive" onclick={() => remove(selected.id)}><Trash2Icon /> Delete</Button>
			</div>
		</div>
	{/if}
</section>
