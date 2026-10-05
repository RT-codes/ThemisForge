<script lang="ts">
	import { cn } from '$lib/utils.js'

	let { size = 'md', class: className }: { size?: 'md' | 'lg'; class?: string } = $props()
</script>

<span
	class={cn(
		'inline-flex items-center justify-center rounded-lg bg-gradient-to-br from-amber-400 to-orange-600 text-[#1c1208] shadow-[0_0_24px_-4px] shadow-primary/50',
		size === 'lg' ? 'size-12 rounded-xl' : 'size-8',
		className
	)}
>
	<!-- anvil, same shape as public/favicon.svg -->
	<svg viewBox="0 0 32 32" fill="currentColor" aria-hidden="true" class="size-full">
		<path d="M3.5 10.5C3.5 9.4 4.4 9 5.5 9H27.5V14H22.8C22.8 16 21.8 17.2 20.6 18V20.5H24.5V24H7.5V20.5H11.4V18C11.4 16.4 9 14.6 6 14C4.6 13.7 3.5 12 3.5 10.5Z" />
	</svg>
</span>
