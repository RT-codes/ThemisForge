<script lang="ts">
	import { cn } from '$lib/utils'
	import type { Component, Snippet } from 'svelte'

	// The small label with an icon that opens a group of cards on a project page ("Project", "Work", "Workspaces"), so a
	// long page reads as a few named parts. The caller spaces the group; this is only the label.
	let {
		icon: Icon,
		class: className,
		children,
	}: {
		// eslint-disable-next-line @typescript-eslint/no-explicit-any
		icon: Component<any>
		/** e.g. text-destructive for a danger zone */
		class?: string
		children: Snippet
	} = $props()
</script>

<h2 class={cn('flex items-center gap-2 px-1 text-xs font-medium tracking-wide text-muted-foreground uppercase', className)}>
	<Icon class="size-4" />{@render children()}
</h2>
