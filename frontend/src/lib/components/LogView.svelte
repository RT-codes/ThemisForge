<script lang="ts">
	import { classify, type Kind } from '$lib/loglines'
	import { nextLogMatch, searchLog } from '$lib/logSearch'
	import { cn } from '$lib/utils'
	import ArrowDownIcon from '@lucide/svelte/icons/arrow-down'
	import ChevronUpIcon from '@lucide/svelte/icons/chevron-up'
	import ChevronDownIcon from '@lucide/svelte/icons/chevron-down'
	import SearchIcon from '@lucide/svelte/icons/search'
	import XIcon from '@lucide/svelte/icons/x'
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

	const rows = $derived(classify(text ? text.replace(/^\n+/, '').replace(/\n$/, '').split('\n') : []))
	let query = $state('')
	let selected = $state(0)
	const search = $derived(searchLog(rows.map((row) => row.text), query))
	const current = $derived(Math.min(selected, Math.max(0, search.count - 1)))

	let el = $state<HTMLDivElement>()
	let stick = $state(true) // follow new output while the reader is at the bottom
	let moving = false // our own smooth scroll is in flight, so its scroll events say nothing about the reader
	let reduceMotion = false
	let scrollTimer: ReturnType<typeof setTimeout>

	onMount(() => {
		reduceMotion = matchMedia('(prefers-reduced-motion: reduce)').matches
		scrollDown(false)
		return () => clearTimeout(scrollTimer)
	})

	const atBottom = () => !el || el.scrollHeight - el.scrollTop - el.clientHeight < 24

	function scrollDown(smooth: boolean) {
		if (!el) return
		clearTimeout(scrollTimer)
		moving = true
		stick = true
		el.scrollTo({ top: el.scrollHeight, behavior: smooth && !reduceMotion ? 'smooth' : 'auto' })
		scrollTimer = setTimeout(() => {
			moving = false
			stick = atBottom()
		}, smooth ? 450 : 0)
	}

	async function showMatch(index: number) {
		clearTimeout(scrollTimer)
		moving = false
		stick = false
		selected = index
		await tick()
		const match = el?.querySelector<HTMLElement>(`[data-log-match="${current}"]`)
		if (el && match) {
			el.scrollTo({ top: el.scrollTop + match.getBoundingClientRect().top - el.getBoundingClientRect().top - el.clientHeight / 2, behavior: 'auto' })
		}
	}

	function navigate(direction: number) {
		void showMatch(nextLogMatch(current, search.count, direction))
	}

	function clearSearch() {
		query = ''
		selected = 0
	}

	$effect(() => {
		void text
		if (stick) tick().then(() => { if (stick) scrollDown(true) })
	})
</script>

<div class={cn('relative flex min-h-16 flex-col overflow-hidden rounded-lg border bg-black/40', className)}>
	<div class="flex flex-wrap items-center gap-1 border-b bg-muted/30 px-2 py-1.5">
		<div class="flex min-w-24 flex-1 items-center gap-1.5 rounded-md border bg-background/60 px-2 focus-within:ring-1 focus-within:ring-ring">
			<SearchIcon class="size-3.5 shrink-0 text-muted-foreground" />
			<input
				type="search"
				aria-label="Search logs"
				placeholder="Search logs…"
				value={query}
				oninput={(event) => {
					query = event.currentTarget.value
					if (query) void showMatch(0)
					else clearSearch()
				}}
				onkeydown={(event) => {
					if (event.key === 'Enter') { event.preventDefault(); navigate(event.shiftKey ? -1 : 1) }
					if (event.key === 'Escape') { event.preventDefault(); event.stopPropagation(); clearSearch() }
				}}
				class="h-7 w-full min-w-0 bg-transparent text-xs outline-none [&::-webkit-search-cancel-button]:hidden"
			/>
			{#if query}
				<button type="button" aria-label="Clear log search" title="Clear search (Escape)" onclick={clearSearch} class="rounded p-1 text-muted-foreground hover:bg-accent hover:text-foreground"><XIcon class="size-3" /></button>
			{/if}
		</div>
		{#if query}
			<span role="status" class="px-1 text-xs whitespace-nowrap text-muted-foreground">{search.count ? `${current + 1} of ${search.count}` : 'No matches'}</span>
			<button type="button" aria-label="Previous match" title="Previous match (Shift+Enter)" disabled={!search.count} onclick={() => navigate(-1)} class="rounded p-1.5 hover:bg-accent disabled:opacity-30"><ChevronUpIcon class="size-3.5" /></button>
			<button type="button" aria-label="Next match" title="Next match (Enter)" disabled={!search.count} onclick={() => navigate(1)} class="rounded p-1.5 hover:bg-accent disabled:opacity-30"><ChevronDownIcon class="size-3.5" /></button>
		{/if}
		{#if corner}
			{@render corner()}
		{/if}
	</div>
	<div bind:this={el} onscroll={() => !moving && !query && (stick = atBottom())} class="min-h-0 flex-1 overflow-auto p-3 font-mono text-xs leading-relaxed">
		{#if rows.length}
			{#each rows as row, i (i)}
				<div class={cn('break-words whitespace-pre-wrap', tone[row.kind])}>{#each search.rows[i] as part}{#if part.match !== null}<mark data-log-match={part.match} aria-current={part.match === current ? 'true' : undefined} class={cn('rounded-sm bg-yellow-300/25 text-yellow-100', part.match === current && 'bg-amber-300 text-black outline outline-1 outline-amber-100')}>{part.text}</mark>{:else}{part.text || ' '}{/if}{/each}</div>
			{/each}
		{:else}
			<span class="text-muted-foreground">{empty}</span>
		{/if}
	</div>

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
