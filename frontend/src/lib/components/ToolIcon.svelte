<script lang="ts">
	import { hueOf, initials } from '$lib/tools'
	import { cn } from '$lib/utils'

	// A tool's icon in the registry browser. The image comes straight from wherever its publisher (or GitHub, for the
	// owner's avatar) hosts it, loaded as the card scrolls into view and without telling that host which page asked.
	// When there is none, or it fails to load, the tool's initials are drawn on a colour its name always gets.
	let { src = '', name, title = '', class: className = '' }: { src?: string; name: string; title?: string; class?: string } = $props()

	let failed = $state(false)
	$effect(() => {
		src // a different tool in the same place gets a fresh try
		failed = false
	})
	const hue = $derived(hueOf(name))
</script>

<span
	class={cn('flex size-10 shrink-0 items-center justify-center overflow-hidden rounded-lg text-xs font-semibold', className)}
	style={src && !failed ? undefined : `background:hsl(${hue} 55% 88%);color:hsl(${hue} 45% 28%)`}
	aria-hidden="true"
>
	{#if src && !failed}
		<img {src} alt="" loading="lazy" decoding="async" referrerpolicy="no-referrer" class="size-full bg-muted object-contain" onerror={() => (failed = true)} />
	{:else}
		{initials(title || name.split('/').pop() || name)}
	{/if}
</span>
