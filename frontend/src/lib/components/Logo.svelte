<script lang="ts">
	import { cn } from '$lib/utils.js'

	let { size = 'md', class: className }: { size?: 'md' | 'lg'; class?: string } = $props()
</script>

<!-- The small logo in the sidebars uses the detailed artwork with no frame; the large one (auth screens) keeps the flat icon and its glow. -->
<img
	src={size === 'lg' ? '/favicon.png' : '/logo.png'}
	alt=""
	aria-hidden="true"
	draggable="false"
	class={cn(
		'shrink-0 select-none',
		size === 'lg' ? 'size-12 drop-shadow-[0_0_6px_oklch(0.76_0.17_58/45%)]' : 'size-8',
		className
	)}
/>
