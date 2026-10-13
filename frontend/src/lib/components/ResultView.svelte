<script lang="ts">
	import { Button } from '$lib/components/ui/button/index.js'
	import { onCodeCopyClick, renderMarkdown } from '$lib/markdown'

	let { text }: { text: string } = $props()
	let raw = $state(false)
	const rich = $derived(renderMarkdown(text, { untrusted: true }).html)
</script>

<div class="min-w-0">
	<div class="mb-2 flex flex-wrap items-center justify-between gap-2">
		<h4 class="text-xs font-medium tracking-wide text-muted-foreground uppercase">Result</h4>
		<div class="inline-flex rounded-md border p-0.5" role="group" aria-label="How to show the result">
			<Button variant={raw ? 'ghost' : 'secondary'} size="sm" class="h-6 px-2 text-xs" aria-pressed={!raw} onclick={() => (raw = false)}>Rendered</Button>
			<Button variant={raw ? 'secondary' : 'ghost'} size="sm" class="h-6 px-2 text-xs" aria-pressed={raw} onclick={() => (raw = true)}>Raw</Button>
		</div>
	</div>
	{#if raw}
		<pre class="slim-scrollbar max-h-96 overflow-auto rounded-lg border bg-card p-4 text-xs break-words whitespace-pre-wrap">{text}</pre>
	{:else}
		<!-- trusted: agent results are rendered in untrusted mode, with no image resolver -->
		<!-- svelte-ignore a11y_click_events_have_key_events, a11y_no_static_element_interactions -->
		<div class="docs-prose prose prose-sm prose-invert slim-scrollbar max-h-96 max-w-none overflow-auto rounded-lg border bg-card p-4 text-sm break-words" onclick={onCodeCopyClick}>
			{@html rich}
		</div>
	{/if}
</div>
