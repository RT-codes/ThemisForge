<script lang="ts">
	import LogView from '$lib/components/LogView.svelte'
	import { Button } from '$lib/components/ui/button/index.js'
	import * as Dialog from '$lib/components/ui/dialog/index.js'
	import Maximize2Icon from '@lucide/svelte/icons/maximize-2'

	// A log with the enlarge button in its corner; the button opens the same log in a big modal.
	let { text, title, subtitle = '', class: className = 'h-80', empty }: { text: string; title: string; subtitle?: string; class?: string; empty?: string } = $props()

	let open = $state(false)
</script>

<LogView {text} {empty} class={className}>
	{#snippet corner()}
		<Button
			type="button"
			variant="secondary"
			size="icon-sm"
			aria-label="Enlarge the log"
			title="Enlarge"
			onclick={() => (open = true)}
			class="size-7 opacity-60 backdrop-blur transition-all duration-200 hover:scale-110 hover:opacity-100"
		>
			<Maximize2Icon class="size-3.5" />
		</Button>
	{/snippet}
</LogView>

<Dialog.Root bind:open>
	<Dialog.Content class="flex h-[85vh] flex-col gap-3 duration-300 ease-out sm:max-w-5xl">
		<Dialog.Header>
			<Dialog.Title>{title}</Dialog.Title>
			<Dialog.Description>{subtitle}</Dialog.Description>
		</Dialog.Header>
		<LogView {text} {empty} class="min-h-0 flex-1" />
	</Dialog.Content>
</Dialog.Root>
