<script lang="ts">
	import { cn } from '$lib/utils'
	import PlusIcon from '@lucide/svelte/icons/plus'

	// The small plus in the sidebar (new project, new workflow). On hover the plus turns, grows and gets bolder,
	// the circle lights up, and a ring of four arcs spins around it for as long as the pointer stays.
	let { label, href, onclick, class: className }: { label: string; href?: string; onclick?: () => void; class?: string } = $props()

	const look =
		'group/plus absolute flex size-5 items-center justify-center rounded-full text-sidebar-foreground/70 outline-hidden transition-[color,background-color] duration-150 hover:bg-sidebar-accent hover:text-primary focus-visible:bg-sidebar-accent focus-visible:text-primary after:absolute after:-inset-2'
	const plus =
		'size-4 transition-[scale,rotate,stroke-width] duration-300 ease-out group-hover/plus:scale-[1.55] group-hover/plus:rotate-90 group-hover/plus:stroke-[3] group-focus-visible/plus:scale-[1.55] group-focus-visible/plus:rotate-90 group-focus-visible/plus:stroke-[3]'
	const ring =
		'pointer-events-none absolute -start-1.5 -top-1.5 size-8 text-primary/60 opacity-0 transition-opacity duration-150 group-hover/plus:animate-[spin_2.4s_linear_infinite] group-hover/plus:opacity-100 group-focus-visible/plus:animate-[spin_2.4s_linear_infinite] group-focus-visible/plus:opacity-100'
</script>

{#snippet inner()}
	<!-- four arcs with a gap between each: 18 on, 7 off, four times round the circle -->
	<svg class={ring} viewBox="0 0 32 32" fill="none" aria-hidden="true">
		<circle cx="16" cy="16" r="14" pathLength="100" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-dasharray="17 8" />
	</svg>
	<PlusIcon class={plus} />
	<span class="sr-only">{label}</span>
{/snippet}

{#if href}
	<a {href} title={label} data-pulse-sibling class={cn(look, className)}>{@render inner()}</a>
{:else}
	<button type="button" title={label} {onclick} class={cn(look, className)}>{@render inner()}</button>
{/if}
