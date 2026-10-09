<script lang="ts">
	import SettingsSection from '$lib/components/SettingsSection.svelte'
	import { appearance, appearancePresets, setAppearance } from '$lib/appearance'
	import { cn } from '$lib/utils'

	const selectedName = $derived(appearancePresets.find((choice) => choice.id === $appearance)?.name ?? 'Compact')
</script>

<SettingsSection id="appearance" title="Appearance" description="Choose the typography used across Themis. Saved in this browser." summary={selectedName} defaultOpen>
	<div class="grid gap-3 sm:grid-cols-3" role="group" aria-label="Typography style">
		{#each appearancePresets as choice (choice.id)}
			{@const selected = $appearance === choice.id}
			<button
				type="button"
				aria-pressed={selected}
				onclick={() => setAppearance(choice.id)}
				class={cn(
					'flex min-w-0 flex-col items-start gap-2 rounded-lg border p-3 text-start transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
					selected ? 'border-primary bg-primary/5' : 'hover:border-foreground/25 hover:bg-accent/30'
				)}
			>
				<span class="flex min-h-14 w-full items-center justify-between rounded-md bg-muted/50 px-3">
					<span class="text-2xl font-semibold tracking-tight" style="font-family: {choice.previewFont}">Aa</span>
					<span class="text-xs text-muted-foreground" style="font-family: {choice.previewMono}">Ag 0123</span>
				</span>
				<span class="flex w-full items-baseline justify-between gap-2">
					<span class="text-sm font-semibold">{choice.name}</span>
					<span class="text-xs text-muted-foreground">{choice.font}</span>
				</span>
				<span class="text-xs leading-relaxed text-muted-foreground">{choice.description}</span>
			</button>
		{/each}
	</div>
</SettingsSection>
