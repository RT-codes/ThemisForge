<script lang="ts">
	import IconTile, { wash, type Tone } from '$lib/components/IconTile.svelte'
	import { cn } from '$lib/utils'
	import type { Component, Snippet } from 'svelte'

	// The header strip of a card: an optional icon tile, the title (children), optional actions on the right, and
	// generated art behind it. Drop an image named after `art` into src/assets/banners/ (e.g. tasks.webp) and it shows
	// up: no import to add, and a missing file just means a plain banner. Art is bundled by Vite, so it is hashed
	// and cached like the rest of the app.
	// Suggested source size: 1200x400 or wider (3:1 to 6:1). The picture always fills the banner's height, so its bottom
	// is always shown, and takes the width that gives, up to the right half of the card. When the card is narrower than
	// that (a small window, a zoomed page) it is cropped from its left edge, which the fade hides, rather than shrunk:
	// shrinking left a gap above it. Keep the subject on the right.
	// Originals live in assets/banners/source/; see the README there for how a banner is made from one.
	const files = import.meta.glob('/src/assets/banners/*.{webp,png,jpg,jpeg,avif}', {
		eager: true,
		query: '?url',
		import: 'default',
	}) as Record<string, string>
	const artByName = Object.fromEntries(
		Object.entries(files).map(([path, url]) => [path.split('/').pop()!.replace(/\.[^.]+$/, ''), url])
	)

	let {
		art,
		icon: Icon,
		tone,
		class: className,
		actionsClass,
		children,
		actions,
	}: {
		art?: string
		// eslint-disable-next-line @typescript-eslint/no-explicit-any
		icon?: Component<any>
		/** the colour of the icon tile and of the wash across the strip; no tone, no wash (the page headers) */
		tone?: Tone
		/** extra classes for the strip, e.g. a taller minimum height for a page header */
		class?: string
		/** extra classes for the box around the actions, e.g. to drop the backing where there is no card behind them */
		actionsClass?: string
		children: Snippet
		actions?: Snippet
	} = $props()
	const src = $derived(art ? artByName[art] : undefined)
</script>

<div class={cn('relative flex min-h-24 flex-wrap items-center justify-between gap-x-3 gap-y-3 overflow-hidden border-b px-5 py-4', tone && wash(tone), className)}>
	{#if src}
		<!-- decorative: the title beside it says what the card is for -->
		<img {src} alt="" aria-hidden="true" draggable="false" class="banner-art absolute inset-y-0 right-0 h-full w-auto max-w-1/2 object-cover object-right" />
	{/if}
	<div class="relative flex min-w-0 flex-1 basis-72 items-center gap-3">
		{#if Icon}<IconTile tone={tone ?? 'amber'}><Icon /></IconTile>{/if}
		<!-- a little shadow keeps the words readable where they run over the art -->
		<div class="min-w-0 [text-shadow:0_1px_6px_rgb(0_0_0/0.55)]">{@render children()}</div>
	</div>
	{#if actions}
		<!-- the art sits behind the buttons, so they get a soft backing to stay readable over it -->
		<div class={cn('relative shrink-0 rounded-md bg-card/70 backdrop-blur-sm', actionsClass)}>{@render actions()}</div>
	{/if}
</div>

<style>
	/* 0% opacity at the left edge of the image, 90% at the right, so it melts into the card instead of ending in an edge
	   and never quite covers it. The img is as wide as the picture it draws (w-auto), so the fade spans the picture, not
	   empty space beside it. */
	.banner-art {
		-webkit-mask-image: linear-gradient(to right, transparent, rgb(0 0 0 / 0.9));
		mask-image: linear-gradient(to right, transparent, rgb(0 0 0 / 0.9));
	}
</style>
