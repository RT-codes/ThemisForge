<script lang="ts">
	import { cn } from '$lib/utils'
	import ChevronDownIcon from '@lucide/svelte/icons/chevron-down'
	import { untrack, type Snippet } from 'svelte'
	import { slide } from 'svelte/transition'

	// A settings section you can fold away. When it is folded, one line says what is inside, so the page can be
	// scanned without opening anything. Open or folded is remembered per section, per browser.
	let {
		id,
		title,
		description = '',
		summary = '',
		status = null,
		defaultOpen = false,
		forceOpen = false,
		children,
	}: {
		id: string
		title: string
		description?: string
		summary?: string
		status?: 'ok' | 'warn' | null
		defaultOpen?: boolean
		forceOpen?: boolean // needs attention: stay open
		children: Snippet
	} = $props()

	const KEY = 'themis.settings.open'
	const read = (): Record<string, boolean> => {
		try {
			return JSON.parse(localStorage.getItem(KEY) ?? '{}')
		} catch {
			return {}
		}
	}
	let chosen = $state<boolean | undefined>(untrack(() => read()[id])) // the section's id never changes
	const open = $derived(forceOpen || (chosen ?? defaultOpen))

	function toggle() {
		chosen = !open
		try {
			localStorage.setItem(KEY, JSON.stringify({ ...read(), [id]: chosen }))
		} catch {
			// remembering is a convenience
		}
	}
</script>

<section class="overflow-hidden rounded-xl border bg-card">
	<button
		type="button"
		onclick={toggle}
		aria-expanded={open}
		aria-controls="section-{id}"
		class="flex w-full items-center gap-3 px-5 py-4 text-start transition-colors hover:bg-accent/30 focus-visible:bg-accent/30 focus-visible:outline-none"
	>
		<span class="min-w-0 flex-1">
			<span class="flex items-center gap-2 text-base font-semibold tracking-tight">
				{title}
				{#if status}<span class={cn('size-2 rounded-full', status === 'ok' ? 'bg-emerald-400' : 'bg-destructive')} aria-hidden="true"></span>{/if}
			</span>
			{#if description}<span class="mt-0.5 block text-sm text-muted-foreground">{description}</span>{/if}
		</span>
		{#if summary && !open}
			<span class="hidden max-w-[45%] shrink-0 truncate text-sm text-muted-foreground sm:block" transition:slide={{ axis: 'x', duration: 150 }}>{summary}</span>
		{/if}
		<ChevronDownIcon class={cn('size-4 shrink-0 text-muted-foreground transition-transform duration-200', open && 'rotate-180')} />
	</button>
	{#if open}
		<div id="section-{id}" class="grid gap-4 border-t px-5 py-5" transition:slide={{ duration: 200 }}>
			{@render children()}
		</div>
	{/if}
</section>
