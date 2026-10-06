<script lang="ts">
	import * as Card from '$lib/components/ui/card/index.js'
	import type { Snippet } from 'svelte'
	import Logo from './Logo.svelte'

	let {
		title,
		description,
		children,
		footer,
	}: { title: string; description: string; children: Snippet; footer?: Snippet } = $props()
</script>

<main class="forge-glow flex min-h-svh items-center justify-center p-4">
	<div class="w-full max-w-sm">
		<div class="mb-8 flex flex-col items-center gap-3 text-center">
			<Logo size="lg" />
			<div>
				<h1 class="text-2xl font-semibold tracking-tight">Themis</h1>
				<p class="text-sm text-muted-foreground">Forge your flows with clarity.</p>
			</div>
		</div>

		<Card.Root>
			<Card.Header>
				<Card.Title>{title}</Card.Title>
				<Card.Description>{description}</Card.Description>
			</Card.Header>
			<Card.Content>{@render children()}</Card.Content>
			{#if footer}
				<Card.Footer class="justify-center text-sm text-muted-foreground">{@render footer()}</Card.Footer>
			{/if}
		</Card.Root>
		<p class="mt-6 text-center text-xs text-muted-foreground">
			<a href="/docs" class="hover:text-foreground hover:underline">Read the documentation</a>
		</p>
	</div>
</main>
