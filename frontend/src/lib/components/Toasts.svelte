<script lang="ts">
	import { toasts } from '$lib/toasts.svelte'
	import { cn } from '$lib/utils'
	import ShieldCheckIcon from '@lucide/svelte/icons/shield-check'
	import XIcon from '@lucide/svelte/icons/x'
	import { fly } from 'svelte/transition'

	// The corner of the page where short messages appear (see toasts.svelte.ts). A toast goes away by itself, but not
	// while the pointer or the keyboard is on it, and it can be clicked to go to whatever it is about.
	const LEAST_LEFT_MS = 3000 // after being held, a toast stays at least this long, so it can be read and reached
	const calm = typeof matchMedia === 'function' && matchMedia('(prefers-reduced-motion: reduce)').matches

	function autoDismiss(node: HTMLElement, { ms, done }: { ms: number; done: () => void }) {
		let left = ms
		let startedAt = 0
		let timer: ReturnType<typeof setTimeout> | undefined
		const run = () => {
			startedAt = Date.now()
			timer = setTimeout(done, left)
		}
		const hold = () => {
			if (timer === undefined) return
			clearTimeout(timer)
			timer = undefined
			left = Math.max(LEAST_LEFT_MS, left - (Date.now() - startedAt))
		}
		const release = () => timer === undefined && run()
		node.addEventListener('pointerenter', hold)
		node.addEventListener('pointerleave', release)
		node.addEventListener('focusin', hold)
		node.addEventListener('focusout', release)
		run()
		return { destroy: () => clearTimeout(timer) }
	}
</script>

<div class="pointer-events-none fixed right-4 bottom-4 z-[60] flex w-[min(24rem,calc(100vw-2rem))] flex-col gap-2" role="region" aria-label="Notifications" aria-live="polite">
	{#each toasts.list as t (t.id)}
		<div
			class={cn('pointer-events-auto relative rounded-xl border bg-popover text-popover-foreground shadow-float', t.tone === 'attention' && 'border-amber-500/50')}
			use:autoDismiss={{ ms: t.ms ?? 10_000, done: () => toasts.dismiss(t.id) }}
			transition:fly={{ x: calm ? 0 : 32, duration: calm ? 0 : 200 }}
		>
			{#snippet content()}
				{#if t.tone === 'attention'}
					<span class="mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-md bg-amber-500/15 text-amber-500"><ShieldCheckIcon class="size-4" /></span>
				{/if}
				<span class="min-w-0 flex-1">
					<span class="block text-sm font-medium">{t.title}</span>
					{#if t.body}<span class="mt-0.5 line-clamp-2 block text-sm text-muted-foreground">{t.body}</span>{/if}
					{#if t.meta}<span class="mt-1 block truncate text-xs text-muted-foreground/80">{t.meta}</span>{/if}
				</span>
			{/snippet}
			{#if t.onSelect}
				<button
					type="button"
					class="flex w-full items-start gap-3 rounded-xl p-3 pe-10 text-start transition-colors hover:bg-accent/40 focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
					onclick={() => {
						t.onSelect?.()
						toasts.dismiss(t.id)
					}}
				>
					{@render content()}
				</button>
			{:else}
				<div class="flex items-start gap-3 p-3 pe-10">{@render content()}</div>
			{/if}
			<button
				type="button"
				class="absolute top-2 right-2 inline-flex size-6 items-center justify-center rounded-md text-muted-foreground hover:bg-accent hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
				aria-label="Dismiss"
				onclick={() => toasts.dismiss(t.id)}
			>
				<XIcon class="size-3.5" />
			</button>
		</div>
	{/each}
</div>
