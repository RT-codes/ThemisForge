<script lang="ts">
	import type { AttemptFailure } from '$lib/api/tasks'
	import CircleAlertIcon from '@lucide/svelte/icons/circle-alert'

	let { failure }: { failure: AttemptFailure } = $props()

	const lines = $derived(failure.tail ? failure.tail.split('\n').length : 0)
</script>

<div class="rounded-lg border border-destructive/40 bg-destructive/10 p-3 text-sm" role="alert">
	<div class="flex items-start gap-2">
		<CircleAlertIcon class="mt-0.5 size-4 shrink-0 text-destructive" />
		<div class="min-w-0 flex-1">
			<p class="font-medium break-words">{failure.reason}</p>
			{#if failure.action}
				<p class="mt-1 break-words"><span class="text-muted-foreground">What to do: </span>{failure.action}</p>
			{/if}
			<p class="mt-1 text-xs text-muted-foreground">
				{failure.source === 'agent' ? 'Written by the agent when it stopped.' : 'Found by Themis from what the run did.'}
			</p>
		</div>
	</div>
	{#if lines}
		<details class="mt-2">
			<summary class="cursor-pointer text-xs text-muted-foreground hover:text-foreground">Last {lines} line{lines === 1 ? '' : 's'} of the log</summary>
			<pre class="slim-scrollbar mt-2 max-h-72 overflow-auto rounded-md border bg-card p-2 text-xs break-words whitespace-pre-wrap">{failure.tail}</pre>
		</details>
	{/if}
</div>
