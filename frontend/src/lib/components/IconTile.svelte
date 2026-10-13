<script lang="ts" module>
	export type Tone = 'amber' | 'green' | 'violet' | 'rose' | 'sky' | 'neutral'

	// A soft wash of the colour behind a stronger icon. Written with a light and a dark shade so it reads on both themes.
	// The colours carry meaning across the app: green is ready/good, violet is running, amber is attention and time,
	// rose is what is coming, sky is structure.
	const TONES: Record<Tone, string> = {
		amber: 'bg-amber-500/15 text-amber-600 ring-amber-500/25 dark:text-amber-400',
		green: 'bg-emerald-500/15 text-emerald-600 ring-emerald-500/25 dark:text-emerald-400',
		violet: 'bg-violet-500/15 text-violet-600 ring-violet-500/25 dark:text-violet-400',
		rose: 'bg-rose-500/15 text-rose-600 ring-rose-500/25 dark:text-rose-400',
		sky: 'bg-sky-500/15 text-sky-600 ring-sky-500/25 dark:text-sky-400',
		neutral: 'bg-muted text-muted-foreground ring-border',
	}

	// The same colour as a wash across the element the tile sits in: strongest at its left edge, gone at 45% of its width,
	// and kept faint so it reads as a background, not a stripe. Whole class names, so Tailwind finds them.
	const WASHES: Record<Tone, string> = {
		amber: 'bg-linear-to-r from-amber-500/6 to-transparent to-45%',
		green: 'bg-linear-to-r from-emerald-500/6 to-transparent to-45%',
		violet: 'bg-linear-to-r from-violet-500/6 to-transparent to-45%',
		rose: 'bg-linear-to-r from-rose-500/6 to-transparent to-45%',
		sky: 'bg-linear-to-r from-sky-500/6 to-transparent to-45%',
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
