<script lang="ts">
	import { Button } from '$lib/components/ui/button/index.js'
	import * as Dialog from '$lib/components/ui/dialog/index.js'
	import { copyButtons, renderMarkdown } from '$lib/markdown'
	import { cn } from '$lib/utils'
	import Maximize2Icon from '@lucide/svelte/icons/maximize-2'

	let { text }: { text: string } = $props()
	let raw = $state(false)
	const rich = $derived(renderMarkdown(text, { untrusted: true }).html)
</script>

{#snippet viewControls()}
	<div class="inline-flex rounded-md border p-0.5" role="group" aria-label="How to show the result">
		<Button variant={raw ? 'ghost' : 'secondary'} size="sm" class="h-6 px-2 text-xs" aria-pressed={!raw} onclick={() => (raw = false)}>Rendered</Button>
		<Button variant={raw ? 'secondary' : 'ghost'} size="sm" class="h-6 px-2 text-xs" aria-pressed={raw} onclick={() => (raw = true)}>Raw</Button>
	</div>
{/snippet}

{#snippet resultBody(enlarged = false)}
	{#if raw}
		<pre class={cn('slim-scrollbar overflow-auto rounded-lg border bg-card p-4 text-xs break-words whitespace-pre-wrap', enlarged ? 'min-h-0 flex-1' : 'max-h-96')}>{text}</pre>
	{:else}
		<!-- trusted: agent results are rendered in untrusted mode, with no image resolver -->
		<div class={cn('docs-prose prose prose-sm prose-invert slim-scrollbar max-w-none overflow-auto rounded-lg border bg-card p-4 text-sm break-words', enlarged ? 'min-h-0 flex-1' : 'max-h-96')} use:copyButtons>
			{@html rich}
		</div>
	{/if}
{/snippet}

<Dialog.Root>
	<div class="min-w-0">
		<div class="mb-2 flex flex-wrap items-center justify-between gap-2">
			<h4 class="text-xs font-medium tracking-wide text-muted-foreground uppercase">Result</h4>
			<div class="flex flex-wrap items-center gap-2">
				{@render viewControls()}
				<Dialog.Trigger>
					{#snippet child({ props })}
						<Button variant="outline" size="sm" class="h-7 px-2 text-xs" {...props}>
							<Maximize2Icon class="size-3.5" />
							Enlarge result
						</Button>
					{/snippet}
				</Dialog.Trigger>
			</div>
		</div>
		{@render resultBody()}
	</div>

	<Dialog.Content class="flex h-[85dvh] min-w-0 flex-col gap-3 sm:max-w-5xl">
		<Dialog.Header class="pr-8">
			<Dialog.Title>Result</Dialog.Title>
			<Dialog.Description>Read the agent's report in Rendered or Raw view.</Dialog.Description>
		</Dialog.Header>
		<div class="flex shrink-0">
			{@render viewControls()}
		</div>
		{@render resultBody(true)}
	</Dialog.Content>
</Dialog.Root>
