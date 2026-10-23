<script lang="ts">
	import { formatOklch, hexToOklch, isColor, parseOklch, swatchHex } from '$lib/colors'
	import { Input } from '$lib/components/ui/input/index.js'
	import { cn } from '$lib/utils'

	// One colour of a theme: a swatch that opens the browser's colour picker, and a field for any CSS colour (oklch, hex,
	// rgb()...), so a colour with transparency can be typed. Every valid change is passed on at once, so the editor shows
	// it live; a half-typed colour is kept in the field and not passed on until it is valid.
	let { label, value, onchange }: { label: string; value: string; onchange: (colour: string) => void } = $props()

	let draft = $state('')
	$effect(() => {
		draft = value
	})
	const valid = $derived(isColor(draft))

	function type(text: string) {
		draft = text
		if (isColor(text)) onchange(text.trim())
	}

	// The picker only speaks opaque hex, so a colour that had transparency keeps it, and the result is stored as oklch
	// like the built-in themes write theirs.
	function pick(hex: string) {
		const picked = hexToOklch(hex, parseOklch(value)?.alpha ?? 1)
		if (picked) onchange(formatOklch(picked))
	}
</script>

<div class="flex items-center gap-2">
	<!-- the swatch is painted with the real colour (transparency included); the picker input sits invisibly over it -->
	<label class="relative size-8 shrink-0 cursor-pointer overflow-hidden rounded-md border focus-within:ring-2 focus-within:ring-ring" title="Pick {label.toLowerCase()}">
		<span class="absolute inset-0 bg-[repeating-conic-gradient(var(--muted)_0%_25%,transparent_0%_50%)] bg-size-[8px_8px]"></span>
		<span class="absolute inset-0" style="background-color: {valid ? draft : value}"></span>
		<input type="color" class="absolute inset-0 size-full cursor-pointer opacity-0" aria-label={label} value={swatchHex(value)} oninput={(e) => pick(e.currentTarget.value)} />
	</label>
	<div class="min-w-0 flex-1">
		<div class="truncate text-sm">{label}</div>
		<Input
			value={draft}
			oninput={(e) => type(e.currentTarget.value)}
			onblur={() => (draft = value)}
			aria-label="{label} colour value"
			aria-invalid={!valid}
			spellcheck="false"
			class={cn('mt-0.5 h-7 px-2 font-mono text-xs md:text-xs')}
		/>
	</div>
</div>
