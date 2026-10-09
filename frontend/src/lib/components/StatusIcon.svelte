<script lang="ts">
	import type { Component } from 'svelte'
	import BoxIcon from '@lucide/svelte/icons/box'
	import BoxesIcon from '@lucide/svelte/icons/boxes'
	import Package2Icon from '@lucide/svelte/icons/package-2'
	import PackageCheckIcon from '@lucide/svelte/icons/package-check'
	import PackageMinusIcon from '@lucide/svelte/icons/package-minus'
	import PackageOpenIcon from '@lucide/svelte/icons/package-open'
	import PackageSearchIcon from '@lucide/svelte/icons/package-search'
	import PackageXIcon from '@lucide/svelte/icons/package-x'
	import DynamicIcon from './DynamicIcon.svelte'

	// The icon of a status: fixed for the seven built-in ones, the owner's choice (the box until one is picked) for a
	// status of your own. `icon` is the custom status's Lucide name; the built-in ones ignore it.
	let { status, icon = '', class: className }: { status: string; icon?: string; class?: string } = $props()

	// eslint-disable-next-line @typescript-eslint/no-explicit-any
	const BUILTIN: Record<string, Component<any>> = {
		backlog: BoxesIcon,
		ready: Package2Icon,
		running: PackageOpenIcon,
		review: PackageSearchIcon,
		done: PackageCheckIcon,
		blocked: PackageMinusIcon,
		failed: PackageXIcon,
	}
	const Fixed = $derived(BUILTIN[status])
</script>

{#if Fixed}
	<Fixed class={className} />
{:else}
	<DynamicIcon name={icon} fallback={BoxIcon} class={className} />
{/if}
