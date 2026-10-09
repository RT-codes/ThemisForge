<script lang="ts">
	import { cn } from '$lib/utils.js'

	let { size = 'md', class: className }: { size?: 'md' | 'lg'; class?: string } = $props()
</script>

<!-- A clean, faceted vector version of Themis's gold mark, with a soft amber halo. -->
<svg
	viewBox="0 0 32 32"
	fill="none"
	aria-hidden="true"
	class={cn('brand-mark shrink-0 select-none', size === 'lg' ? 'brand-mark-large size-12' : 'size-8', className)}
>
	<path d="M2.5 5.2h27L23.1 12 16 9.7 8.9 12 2.5 5.2Z" fill="#F2A116" />
	<path d="M2.5 5.2 16 9.7 8.9 12 2.5 5.2Z" fill="#FFD45B" />
	<path d="m16 9.7 13.5-4.5-6.4 6.8L16 9.7Z" fill="#DA7907" />
	<path d="m8.9 12 7.1-2.3 7.1 2.3-7.1 2.4L8.9 12Z" fill="#F8B52C" />
	<path d="m12.1 12 3.9 1.4 3.9-1.4v11.7L16 27l-3.9-3.3V12Z" fill="#F3A51C" />
	<path d="m16 13.4 3.9-1.4v11.7L16 27V13.4Z" fill="#D97808" />
</svg>

<style>
	.brand-mark {
		filter: drop-shadow(0 0 8px rgb(242 161 22 / 18%));
	}

	.brand-mark-large {
		filter: drop-shadow(0 0 10px rgb(242 161 22 / 28%));
	}
</style>
