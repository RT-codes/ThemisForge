<script lang="ts">
	import type { Component } from 'svelte'
	import { cachedIcon, loadIcon } from '$lib/lucideIcons'

	// A Lucide icon picked by name. The icon is fetched when it is first needed; until it arrives, and for a name that
	// is empty or unknown, the fallback is shown, so a page never waits on an icon or breaks on a bad one.
	// eslint-disable-next-line @typescript-eslint/no-explicit-any
	let { name, fallback, class: className }: { name: string; fallback: Component<any>; class?: string } = $props()

	let loaded = $state<Component | null>(null)

	$effect(() => {
		const wanted = name
		const known = wanted ? cachedIcon(wanted) : null // null: nothing asked for or no such icon; undefined: not loaded yet
		if (known !== undefined) {
			loaded = known
			return
		}
		loaded = null
		let current = true
		loadIcon(wanted).then((component) => current && (loaded = component))
		return () => (current = false)
	})

	const Shown = $derived(loaded ?? fallback)
</script>

<Shown class={className} />
