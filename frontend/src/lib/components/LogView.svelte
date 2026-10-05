<script lang="ts">
	import { classify, type Kind } from '$lib/loglines'
	import { cn } from '$lib/utils'
	import ArrowDownIcon from '@lucide/svelte/icons/arrow-down'
	import { onMount, tick, type Snippet } from 'svelte'
	import { fade, fly } from 'svelte/transition'

	let {
		text,
		empty = 'No output yet.',
		class: className = '',
		corner,
	}: { text: string; empty?: string; class?: string; corner?: Snippet } = $props()

	const tone: Record<Kind, string> = {
		plain: 'text-foreground',
		command: 'font-medium text-sky-300',
		output: 'text-muted-foreground',
		thinking: 'text-violet-300/80 italic',
		note: 'text-muted-foreground/60',
		error: 'text-red-400',
	}

	const rows = $derived(classify(text ? text.replace(/\n$/, '').split('\n') : []))

	let el = $state<HTMLDivElement>()
	let stick = $state(true) // follow new output while the reader is at the bottom
	let moving = false // our own smooth scroll is in flight, so its scroll events say nothing about the reader
	let reduceMotion = false

	onMount(() => {
		reduceMotion = matchMedia('(prefers-reduced-motion: reduce)').matches
		scrollDown(false)
	})

	const atBottom = () => !el || el.scrollHeight - el.scrollTop - el.clientHeight < 24

	function scrollDown(smooth: boolean) {
		if (!el) return
		moving = true
		stick = true
		el.scrollTo({ top: el.scrollHeight, behavior: smooth && !reduceMotion ? 'smooth' : 'auto' })
		setTimeout(() => {
			moving = false
			stick = atBottom()
		}, smooth ? 450 : 0)
	}

	$effect(() => {
		void text
		if (stick) tick().then(() => scrollDown(true))
	})
</script>

<div class={cn('relative flex min-h-16 flex-col overflow-hidden rounded-lg border bg-black/40', className)}>
	<div bind:this={el} onscroll={() => !moving && (stick = atBottom())} class="min-h-0 flex-1 overflow-auto p-3 font-mono text-xs leading-relaxed">
		{#if rows.length}
			{#each rows as row, i (i)}
				<div class={cn('break-words whitespace-pre-wrap', tone[row.kind])}>{row.text || ' '}</div>
			{/each}
		{:else}
			<span class="text-muted-foreground">{empty}</span>
		{/if}
	</div>

	{#if corner}
		<div class="absolute top-2 right-3">{@render corner()}</div>
	{/if}

	{#if !stick}
		<div class="pointer-events-none absolute inset-x-0 bottom-3 flex justify-center">
			<button
				type="button"
				in:fly={{ y: 10, duration: 220 }}
				out:fade={{ duration: 150 }}
				onclick={() => scrollDown(true)}
				class="pointer-events-auto flex items-center gap-1.5 rounded-full border bg-popover/90 px-3 py-1 text-xs shadow-lg backdrop-blur transition-colors hover:bg-accent"
			>
				<ArrowDownIcon class="size-3" />Latest
			</button>
		</div>
	{/if}
</div>
