<script lang="ts">
	import ScaleIcon from '@lucide/svelte/icons/scale'
	import { cn } from '$lib/utils.js'

	let { size = 'md', class: className }: { size?: 'md' | 'lg'; class?: string } = $props()
</script>

<span
	class={cn(
		'inline-flex items-center justify-center rounded-lg bg-primary text-primary-foreground shadow-[0_0_24px_-4px] shadow-primary/50',
		size === 'lg' ? 'size-12 rounded-xl' : 'size-8',
		className
	)}
>
	<ScaleIcon class={size === 'lg' ? 'size-6' : 'size-4.5'} />
</span>
