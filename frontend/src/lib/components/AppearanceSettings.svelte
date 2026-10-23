<script lang="ts">
	import SettingsSection from '$lib/components/SettingsSection.svelte'
	import { appearance, appearancePresets, setAppearance, setTheme, theme } from '$lib/appearance'
	import { findTheme, themes, type Theme } from '$lib/themes'
	import { cn } from '$lib/utils'

	const selectedTheme = $derived(findTheme($theme)?.name ?? '')
	const selectedTypography = $derived(appearancePresets.find((choice) => choice.id === $appearance)?.name ?? 'Compact')

	// A miniature of the interface painted with the theme's own colours (not the active theme's), so every choice shows
	// what it will look like before it is picked: page, sidebar, a card with a primary button, and the meaning colours.
	const tones = ['green', 'yellow', 'violet', 'sky', 'rose'] as const
	const paint = (choice: Theme) => (name: keyof Theme['colors']) => `background-color: ${choice.colors[name]}`
</script>

<SettingsSection id="appearance" title="Appearance" description="Choose the look of Themis: its colours and its typography. Saved in this browser." summary="{selectedTheme}, {selectedTypography}" defaultOpen>
	<div class="space-y-6">
		<div>
			<h3 class="mb-3 text-sm font-medium">Theme</h3>
			<div class="grid gap-3 sm:grid-cols-3" role="group" aria-label="Theme">
				{#each themes as choice (choice.id)}
					{@const selected = $theme === choice.id}
					{@const fill = paint(choice)}
					<button
						type="button"
						aria-pressed={selected}
						onclick={() => setTheme(choice.id)}
						class={cn(
							'flex min-w-0 flex-col items-start gap-2 rounded-lg border p-3 text-start transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
							selected ? 'border-primary bg-primary/5' : 'hover:border-foreground/25 hover:bg-accent/30'
						)}
					>
						<span class="flex h-20 w-full overflow-hidden rounded-md border" style="{fill('background')}; border-color: {choice.colors.border}" aria-hidden="true">
							<span class="w-1/4 border-e" style="{fill('sidebar')}; border-color: {choice.colors['sidebar-border']}"></span>
							<span class="flex flex-1 flex-col gap-1.5 p-2">
								<span class="flex flex-1 items-end justify-between gap-2 rounded border p-1.5" style="{fill('card')}; border-color: {choice.colors.border}">
									<span class="flex gap-1">
										{#each tones as tone (tone)}
											<span class="size-1.5 rounded-full" style={fill(`tone-${tone}`)}></span>
										{/each}
									</span>
									<span class="h-2.5 w-7 rounded-sm" style={fill('primary')}></span>
								</span>
								<span class="h-1.5 w-2/3 rounded-full" style={fill('muted-foreground')}></span>
							</span>
						</span>
						<span class="flex w-full items-baseline justify-between gap-2">
							<span class="text-sm font-semibold">{choice.name}</span>
							<span class="text-xs text-muted-foreground capitalize">{choice.mode}</span>
						</span>
						<span class="text-xs leading-relaxed text-muted-foreground">{choice.description}</span>
					</button>
				{/each}
			</div>
		</div>

		<div>
			<h3 class="mb-3 text-sm font-medium">Typography</h3>
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
		</div>
	</div>
</SettingsSection>
