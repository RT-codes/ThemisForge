<script lang="ts" module>
	import type { Tone as ThemeTone } from '$lib/themes'

	export type Tone = Exclude<ThemeTone, 'yellow' | 'teal'> | 'neutral'

	// A soft wash of the colour behind a stronger icon. The tone colours come from the active theme, so the tile reads on
	// every theme.
	// The colours carry meaning across the app: green is ready/good, violet is running, amber is attention and time,
	// rose is what is coming, sky is structure.
	const TONES: Record<Tone, string> = {
		amber: 'bg-tone-amber/15 text-tone-amber ring-tone-amber/25',
		green: 'bg-tone-green/15 text-tone-green ring-tone-green/25',
		violet: 'bg-tone-violet/15 text-tone-violet ring-tone-violet/25',
		rose: 'bg-tone-rose/15 text-tone-rose ring-tone-rose/25',
		sky: 'bg-tone-sky/15 text-tone-sky ring-tone-sky/25',
		neutral: 'bg-muted text-muted-foreground ring-border',
	}

	// The same colour as a wash across the element the tile sits in: strongest at its left edge, gone at 45% of its width,
	// and kept faint so it reads as a background, not a stripe. Whole class names, so Tailwind finds them.
	const WASHES: Record<Tone, string> = {
		amber: 'bg-linear-to-r from-tone-amber/6 to-transparent to-45%',
		green: 'bg-linear-to-r from-tone-green/6 to-transparent to-45%',
		violet: 'bg-linear-to-r from-tone-violet/6 to-transparent to-45%',
		rose: 'bg-linear-to-r from-tone-rose/6 to-transparent to-45%',
		sky: 'bg-linear-to-r from-tone-sky/6 to-transparent to-45%',
		neutral: 'bg-linear-to-r from-foreground/3 to-transparent to-45%',
	}
	export const wash = (tone: Tone) => WASHES[tone]

	// the icon inside is sized by the tile, so any icon (a Lucide component or a DynamicIcon) fits without its own size
	const SIZES = {
		sm: 'size-8 rounded-lg [&_svg]:size-4',
		md: 'size-10 rounded-xl [&_svg]:size-5',
		lg: 'size-14 rounded-2xl [&_svg]:size-7',
	}
</script>

<script lang="ts">
	import { cn } from '$lib/utils'
	import type { Snippet } from 'svelte'

	let {
		tone = 'amber',
		size = 'md',
		class: className,
		children,
	}: { tone?: Tone; size?: keyof typeof SIZES; class?: string; children: Snippet } = $props()
</script>

<span class={cn('inline-flex shrink-0 items-center justify-center ring-1 ring-inset', TONES[tone], SIZES[size], className)} aria-hidden="true">
	{@render children()}
</span>
