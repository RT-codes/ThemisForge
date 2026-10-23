<script lang="ts">
	import { copyColour, pasteColour } from '$lib/colorClipboard'
	import { formatOklch, hexToOklch, isColor, parseColor, swatchHex } from '$lib/colors'
	import * as DropdownMenu from '$lib/components/ui/dropdown-menu/index.js'
	import { Input } from '$lib/components/ui/input/index.js'
	import { toasts } from '$lib/toasts.svelte'
	import CopyIcon from '@lucide/svelte/icons/copy'
	import EllipsisIcon from '@lucide/svelte/icons/ellipsis'
	import ClipboardPasteIcon from '@lucide/svelte/icons/clipboard-paste'
	import RotateCcwIcon from '@lucide/svelte/icons/rotate-ccw'
	import SwatchBookIcon from '@lucide/svelte/icons/swatch-book'

	// One colour of a theme: a swatch that opens the browser's colour picker, and a field for the colour itself (oklch, hex
	// or rgb(), so a colour with transparency can be typed). Every valid change is passed on at once, so the editor shows it
	// live; a half-typed colour stays in the field until it is valid. A colour that follows from others says so, and the
	// menu has what can be done with a colour: copy it, paste one over it, keep it in the palette. A colour can also be
	// dropped onto the row from the palette.
	let {
		label,
		hint = '',
		value,
		follows = null,
		onchange,
		onfollow,
		onsave,
	}: {
		label: string
		hint?: string
		value: string
		/** null: a colour of its own. 'auto': follows from the main colours. 'custom': was set by hand, so it does not follow */
		follows?: 'auto' | 'custom' | null
		onchange: (colour: string) => void
		/** lets a hand-made colour follow the main colours again */
		onfollow?: () => void
		/** keeps the colour in the palette */
		onsave?: (colour: string, name: string) => void
	} = $props()

	let draft = $state('')
	$effect(() => {
		draft = value
	})
	const valid = $derived(isColor(draft))
	let dropping = $state(false)

	function type(text: string) {
		draft = text
		if (isColor(text)) onchange(text.trim())
	}

	// The picker only speaks opaque hex, so a colour that had transparency keeps it, and the result is stored as oklch
	// like the built-in themes write theirs.
	function pick(hex: string) {
		const picked = hexToOklch(hex, parseColor(value)?.alpha ?? 1)
		if (picked) onchange(formatOklch(picked))
	}

	async function paste() {
		const colour = await pasteColour()
		if (colour) onchange(colour)
		else toasts.push({ title: 'No colour to paste', body: 'Copy a colour first, or pick one from the palette.', ms: 4000 })
	}

	function drop(event: DragEvent) {
		dropping = false
		const text = event.dataTransfer?.getData('text/plain').trim() ?? ''
		if (!isColor(text)) return
		event.preventDefault()
		onchange(text)
	}
</script>

<div
	role="group"
	aria-label={label}
	class="flex items-center gap-2 rounded-lg p-1 transition-colors {dropping ? 'bg-accent ring-2 ring-ring' : ''}"
	ondragover={(e) => {
		e.preventDefault()
		dropping = true
	}}
	ondragleave={() => (dropping = false)}
	ondrop={drop}
>
	<!-- the swatch is painted with the real colour (transparency included); the picker input sits invisibly over it -->
	<label class="relative size-9 shrink-0 cursor-pointer overflow-hidden rounded-md border focus-within:ring-2 focus-within:ring-ring" title="Pick {label.toLowerCase()}">
		<span class="absolute inset-0 bg-[repeating-conic-gradient(var(--muted)_0%_25%,transparent_0%_50%)] bg-size-[8px_8px]"></span>
		<span class="absolute inset-0" style="background-color: {valid ? draft : value}"></span>
		<input type="color" class="absolute inset-0 size-full cursor-pointer opacity-0" aria-label={label} value={swatchHex(value)} oninput={(e) => pick(e.currentTarget.value)} />
	</label>
	<div class="min-w-0 flex-1">
		<div class="flex items-baseline gap-2">
			<span class="truncate text-sm font-medium">{label}</span>
			{#if follows === 'auto'}
				<span class="shrink-0 text-[0.7rem] text-muted-foreground">follows</span>
			{:else if follows === 'custom'}
				<span class="shrink-0 rounded-full bg-primary/15 px-1.5 text-[0.7rem] text-primary">custom</span>
			{/if}
		</div>
		{#if hint}<div class="truncate text-xs text-muted-foreground">{hint}</div>{/if}
		<Input
			value={draft}
			oninput={(e) => type(e.currentTarget.value)}
			onblur={() => (draft = value)}
			aria-label="{label} colour value"
			aria-invalid={!valid}
			spellcheck="false"
			class="mt-1 h-7 px-2 font-mono text-xs md:text-xs"
		/>
	</div>
	<DropdownMenu.Root>
		<DropdownMenu.Trigger class="inline-flex size-7 shrink-0 items-center justify-center rounded-md text-muted-foreground hover:bg-accent hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none" aria-label="Actions for {label.toLowerCase()}">
			<EllipsisIcon class="size-4" />
		</DropdownMenu.Trigger>
		<DropdownMenu.Content align="end" class="min-w-52">
			<DropdownMenu.Item onSelect={() => copyColour(value)}><CopyIcon /> Copy colour</DropdownMenu.Item>
			<DropdownMenu.Item onSelect={paste}><ClipboardPasteIcon /> Paste colour</DropdownMenu.Item>
			{#if onsave}
				<DropdownMenu.Item onSelect={() => onsave(value, label)}><SwatchBookIcon /> Add to palette</DropdownMenu.Item>
			{/if}
			{#if follows === 'custom' && onfollow}
				<DropdownMenu.Separator />
				<DropdownMenu.Item onSelect={onfollow}><RotateCcwIcon /> Follow automatically</DropdownMenu.Item>
			{/if}
		</DropdownMenu.Content>
	</DropdownMenu.Root>
</div>
