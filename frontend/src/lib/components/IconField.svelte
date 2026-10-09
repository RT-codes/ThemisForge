<script lang="ts">
	import type { Component } from 'svelte'
	import DynamicIcon from '$lib/components/DynamicIcon.svelte'
	import IconPlaceholder from '$lib/components/IconPlaceholder.svelte'
	import { Button } from '$lib/components/ui/button/index.js'
	import { Input } from '$lib/components/ui/input/index.js'
	import { iconNames } from '$lib/lucideIcons'
	import { matchIcons } from '$lib/iconSearch'
	import { cn } from '$lib/utils'
	import ChevronDownIcon from '@lucide/svelte/icons/chevron-down'
	import SearchIcon from '@lucide/svelte/icons/search'

	// "Click to change icon": a button showing the current icon, which opens a search box and a grid of Lucide icons.
	// The picker opens in place instead of as a second popup, so it works inside a popover or a dialog alike.
	let {
		value = $bindable(''),
		fallback,
	}: {
		/** a Lucide icon name; empty is the default icon */
		value: string
		/** the icon shown for the default */
		// eslint-disable-next-line @typescript-eslint/no-explicit-any
		fallback: Component<any>
	} = $props()

	const PAGE = 72
	let open = $state(false)
	let query = $state('')
	let shown = $state(PAGE)

	const matches = $derived(matchIcons(iconNames, query))

	$effect(() => {
		query // a new search starts at the first icons again
		shown = PAGE
	})

	function pick(name: string) {
		value = name
		open = false
	}
</script>

<div class="grid gap-2">
	<Button type="button" variant="outline" class="h-10 justify-start gap-2.5" aria-expanded={open} onclick={() => (open = !open)}>
		<DynamicIcon name={value} {fallback} class="size-5" />
		<span class="truncate text-sm">{value || 'Default icon'}</span>
		<span class="ms-auto flex items-center gap-1 text-xs text-muted-foreground">Click to change <ChevronDownIcon class={cn('size-3.5 transition-transform', open && 'rotate-180')} /></span>
	</Button>
	{#if open}
		<div class="grid gap-2 rounded-lg border bg-background/40 p-2">
			<div class="relative">
				<SearchIcon class="pointer-events-none absolute start-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
				<Input bind:value={query} placeholder="Search {iconNames.length} icons" class="h-8 ps-8" aria-label="Search icons" autofocus />
			</div>
			<div class="slim-scrollbar grid max-h-72 grid-cols-8 content-start gap-1 overflow-y-auto pe-1" role="listbox" aria-label="Icons">
				{#each matches.slice(0, shown) as name (name)}
					<button
						type="button"
						role="option"
						aria-selected={name === value}
						title={name}
						class={cn(
							'flex size-8 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-accent hover:text-foreground',
							name === value && 'bg-primary/15 text-primary'
						)}
						onclick={() => pick(name)}
					>
						<DynamicIcon {name} fallback={IconPlaceholder} class="size-4" />
					</button>
				{:else}
					<p class="col-span-8 px-1 py-4 text-center text-xs text-muted-foreground">No icon is called that.</p>
				{/each}
			</div>
			<div class="flex items-center justify-between gap-2">
				<Button type="button" variant="ghost" size="sm" disabled={!value} onclick={() => pick('')}>Use the default</Button>
				{#if matches.length > shown}
					<Button type="button" variant="ghost" size="sm" onclick={() => (shown += PAGE)}>Show more ({matches.length - shown})</Button>
				{/if}
			</div>
		</div>
	{/if}
</div>
