<script lang="ts">
	import IconTile, { wash, type Tone } from '$lib/components/IconTile.svelte'
	import { cn } from '$lib/utils'
	import type { Component, Snippet } from 'svelte'

	// The header strip of a card: an optional icon tile, the title (children) and optional actions on the right,
	// over a wash of the tone's colour.
	let {
		icon: Icon,
		tone,
		class: className,
		children,
		actions,
	}: {
		// eslint-disable-next-line @typescript-eslint/no-explicit-any
		icon?: Component<any>
		/** the colour of the icon tile and of the wash across the strip; no tone, no wash (the page headers) */
		tone?: Tone
		/** extra classes for the strip, e.g. a taller minimum height for a page header */
		class?: string
		children: Snippet
		actions?: Snippet
	} = $props()
</script>

<div class={cn('flex min-h-24 flex-wrap items-center justify-between gap-x-3 gap-y-3 overflow-hidden border-b px-5 py-4', tone && wash(tone), className)}>
	<div class="flex min-w-0 flex-1 basis-72 items-center gap-3">
		{#if Icon}<IconTile tone={tone ?? 'amber'}><Icon /></IconTile>{/if}
		<div class="min-w-0">{@render children()}</div>
	</div>
	{#if actions}
		<div class="shrink-0">{@render actions()}</div>
	{/if}
</div>
