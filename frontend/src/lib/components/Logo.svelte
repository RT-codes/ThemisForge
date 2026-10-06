<script lang="ts">
	import { cn } from '$lib/utils.js'

	let { size = 'md', class: className }: { size?: 'md' | 'lg'; class?: string } = $props()
</script>

<img src="/logo.png" alt="" aria-hidden="true" draggable="false" class={cn('shrink-0 select-none drop-shadow-[0_0_6px_oklch(0.76_0.17_58/45%)]', size === 'lg' ? 'size-12' : 'size-8', className)} />
