<script lang="ts">
	import SettingsSection from '$lib/components/SettingsSection.svelte'
	import { Button } from '$lib/components/ui/button/index.js'
	import { allThemes, appearance, appearancePresets, duplicateThemeOf, setAppearance, setTheme, theme } from '$lib/appearance'
	import { router } from '$lib/router.svelte'
	import { findTheme, isBuiltinTheme, type Theme } from '$lib/themes'
	import { cn } from '$lib/utils'
	import CopyIcon from '@lucide/svelte/icons/copy'
	import PencilIcon from '@lucide/svelte/icons/pencil'
	import PlusIcon from '@lucide/svelte/icons/plus'

	const selectedTheme = $derived(findTheme($theme, $allThemes)?.name ?? '')
	const selectedTypography = $derived(appearancePresets.find((choice) => choice.id === $appearance)?.name ?? 'Compact')

	// A miniature of the interface painted with the theme's own colours (not the active theme's), so every choice shows
	// what it will look like before it is picked: page, sidebar, a card with a primary button, and the meaning colours.
	const tones = ['green', 'yellow', 'violet', 'sky', 'rose'] as const
	const paint = (choice: Theme) => (name: keyof Theme['colors']) => `background-color: ${choice.colors[name]}`

	// A copy of a theme is yours to change, so it opens in the editor, on that theme, right away.
	function duplicate(id: string) {
		const copy = duplicateThemeOf(id)
		if (!copy) return
		setTheme(copy.id)
		router.navigate(`/settings/themes/${copy.id}`)
	}
</script>

<SettingsSection id="appearance" title="Appearance" description="Choose the look of Themis: its colours and its typography. Saved in this browser." summary="{selectedTheme}, {selectedTypography}" defaultOpen>
	<div class="space-y-6">
		<div>
			<div class="mb-3 flex items-center justify-between gap-3">
				<h3 class="text-sm font-medium">Theme</h3>
				<Button variant="outline" size="sm" onclick={() => duplicate($theme)} title="Start a new theme from the one in use"><PlusIcon /> New theme</Button>
			</div>
			<div class="grid gap-3 sm:grid-cols-3" role="group" aria-label="Theme">
				{#each $allThemes as choice (choice.id)}
					{@const selected = $theme === choice.id}
					{@const fill = paint(choice)}
					{@const custom = !isBuiltinTheme(choice.id)}
					<div class={cn('flex min-w-0 flex-col rounded-lg border transition-colors', selected ? 'border-primary bg-primary/5' : 'hover:border-foreground/25')}>
						<button
							type="button"
							aria-pressed={selected}
							onclick={() => setTheme(choice.id)}
							class="flex min-w-0 flex-1 flex-col items-start gap-2 rounded-t-lg p-3 text-start focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
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
								<span class="truncate text-sm font-semibold">{choice.name}</span>
								<span class="shrink-0 text-xs text-muted-foreground capitalize">{custom ? `Custom, ${choice.mode}` : choice.mode}</span>
							</span>
							<span class="text-xs leading-relaxed text-muted-foreground">{choice.description}</span>
						</button>
						<div class="flex gap-1 border-t px-2 py-1.5">
							{#if custom}
								<Button variant="ghost" size="sm" class="h-7 px-2 text-xs" onclick={() => router.navigate(`/settings/themes/${choice.id}`)}><PencilIcon /> Edit</Button>
							{/if}
							<Button variant="ghost" size="sm" class="h-7 px-2 text-xs" onclick={() => duplicate(choice.id)} title={custom ? 'Make a copy' : 'Make a copy you can edit'}><CopyIcon /> Duplicate</Button>
						</div>
					</div>
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
