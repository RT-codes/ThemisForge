<script lang="ts">
	import { allThemes, deleteTheme, duplicateThemeOf, setTheme, theme, themesSaveFailed, updateTheme } from '$lib/appearance'
	import ThemeColorField from '$lib/components/ThemeColorField.svelte'
	import ThemePalette from '$lib/components/ThemePalette.svelte'
	import * as AlertDialog from '$lib/components/ui/alert-dialog/index.js'
	import { Button } from '$lib/components/ui/button/index.js'
	import { Input } from '$lib/components/ui/input/index.js'
	import { router } from '$lib/router.svelte'
	import { EDITOR_SECTIONS, isMainToken, type ColorToken, type DerivedToken } from '$lib/themeColors'
	import { findTheme, isBuiltinTheme, MAX_PALETTE, MAX_THEME_NAME, newPaletteColor, radiusFromRem, radiusRem, shadowFromStrength, shadowStrength } from '$lib/themes'
	import { toasts } from '$lib/toasts.svelte'
	import { cn } from '$lib/utils'
	import ArrowLeftIcon from '@lucide/svelte/icons/arrow-left'
	import ChevronRightIcon from '@lucide/svelte/icons/chevron-right'
	import CircleAlertIcon from '@lucide/svelte/icons/circle-alert'
	import CircleCheckIcon from '@lucide/svelte/icons/circle-check'
	import CopyIcon from '@lucide/svelte/icons/copy'
	import Trash2Icon from '@lucide/svelte/icons/trash-2'
	import { untrack } from 'svelte'

	// The editor of a custom theme. It edits the theme that is in use, so every change shows on this very page (and
	// everywhere else) as you make it, and each change is saved in this browser at once, so there is no Save button: the bar
	// at the top says so, and Done leads back. The built-in themes cannot be edited, but they can be duplicated, and the copy
	// is yours to change.
	//
	// Each section has a few colours to choose; the colours that follow from them (card, border, hover, ...) are folded
	// away and change with them until one is set by hand, which marks it "custom" until it is told to follow again.
	let { themeId }: { themeId: string } = $props()

	const current = $derived(findTheme(themeId, $allThemes))
	const builtin = $derived(isBuiltinTheme(themeId))
	const editable = $derived(!!current && !builtin)

	// live editing needs the theme to be the one in use
	$effect(() => {
		if (editable && $theme !== themeId) setTheme(themeId)
	})

	// The name is saved as it is typed (like every colour), as long as it is not empty. The field keeps what was typed,
	// so a trailing space is not eaten under the cursor; it only goes back to the saved name when the theme changes or
	// the field is left empty.
	let nameDraft = $state('')
	$effect(() => {
		themeId
		untrack(() => (nameDraft = current?.name ?? ''))
	})
	function typeName(text: string) {
		nameDraft = text
		if (editable && text.trim()) updateTheme(themeId, { name: text })
	}

	// every change is saved at once; the bar confirms each one for a moment so it is plain that nothing is left to save
	let justSaved = $state(false)
	let savedTimer: ReturnType<typeof setTimeout> | undefined
	$effect(() => {
		current // a new version of the theme: it was just saved
		untrack(() => {
			justSaved = true
			clearTimeout(savedTimer)
			savedTimer = setTimeout(() => (justSaved = false), 1500)
		})
		return () => clearTimeout(savedTimer)
	})

	const strength = $derived(current ? shadowStrength(current.shadowFloat) : null)
	let deleteOpen = $state(false)

	const follows = (token: ColorToken): 'auto' | 'custom' | null => (isMainToken(token) ? null : current?.pinned.includes(token as DerivedToken) ? 'custom' : 'auto')
	const setColour = (token: ColorToken, colour: string) => updateTheme(themeId, { colors: { [token]: colour } })

	function saveToPalette(color: string, name: string) {
		if (!current) return
		if (current.palette.length >= MAX_PALETTE) {
			toasts.push({ title: 'The palette is full', body: 'Delete a colour from it to make room.', ms: 4000 })
			return
		}
		updateTheme(themeId, { palette: [...current.palette, newPaletteColor(color, name)] })
		toasts.push({ title: 'Added to the palette', body: name, ms: 2500 })
	}

	function duplicate() {
		const copy = duplicateThemeOf(themeId)
		if (!copy) return
		setTheme(copy.id)
		router.navigate(`/settings/themes/${copy.id}`)
	}
</script>

<div class="w-full max-w-6xl px-6 pb-8">
	{#if !current}
		<a href="/settings" class="mt-8 inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground"><ArrowLeftIcon class="size-4" /> Settings</a>
		<h2 class="mt-4 text-2xl font-semibold tracking-tight">Theme not found</h2>
		<p class="mt-1 text-sm text-muted-foreground">This theme does not exist in this browser. Themes you make are saved per browser.</p>
	{:else if builtin}
		<a href="/settings" class="mt-8 inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground"><ArrowLeftIcon class="size-4" /> Settings</a>
		<h2 class="mt-4 text-2xl font-semibold tracking-tight">{current.name}</h2>
		<p class="mt-1 text-sm text-muted-foreground">Built-in themes cannot be edited. Duplicate it to make a copy that is yours to change.</p>
		<Button class="mt-6" onclick={duplicate}><CopyIcon /> Duplicate to edit</Button>
	{:else}
		<!-- stays in view while the page scrolls: where you are, that nothing is left to save, and the way back -->
		<div class="sticky top-0 z-10 -mx-6 flex items-center gap-4 border-b bg-background/90 px-6 py-3 backdrop-blur">
			<a href="/settings" class="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground"><ArrowLeftIcon class="size-4" /> Settings</a>
			<div class="ms-auto flex items-center gap-2 text-sm" role="status" aria-live="polite">
				{#if $themesSaveFailed}
					<CircleAlertIcon class="size-4 text-destructive" />
					<span class="text-destructive">Could not save in this browser. Your changes last until you close this page.</span>
				{:else}
					<CircleCheckIcon class={cn('size-4 transition-colors', justSaved ? 'text-tone-green' : 'text-muted-foreground')} />
					<span class={cn('transition-colors', justSaved ? 'text-tone-green' : 'text-muted-foreground')}>{justSaved ? 'Saved' : 'All changes saved in this browser'}</span>
				{/if}
			</div>
			<Button size="sm" onclick={() => router.navigate('/settings')}>Done</Button>
		</div>

		<h2 class="mt-6 text-2xl font-semibold tracking-tight">Edit theme</h2>
		<p class="mt-1 text-sm text-muted-foreground">Changes show across Themis as you make them. Leave whenever you like: everything is already saved.</p>

		<div class="mt-6 grid items-start gap-6 lg:grid-cols-[minmax(0,1fr)_17rem]">
			<div class="space-y-4">
				<section class="rounded-xl border bg-card p-5">
					<div class="flex flex-wrap items-end gap-4">
						<label class="min-w-56 flex-1">
							<span class="text-sm font-medium">Name</span>
							<Input
								value={nameDraft}
								maxlength={MAX_THEME_NAME}
								oninput={(e) => typeName(e.currentTarget.value)}
								onblur={() => (nameDraft = current?.name ?? '')}
								class="mt-1.5"
							/>
						</label>
						<div>
							<span class="text-sm font-medium">Surface</span>
							<div class="mt-1.5 flex rounded-md border p-0.5" role="group" aria-label="Light or dark surfaces">
								{#each ['dark', 'light'] as const as mode (mode)}
									<button
										type="button"
										aria-pressed={current.mode === mode}
										onclick={() => updateTheme(themeId, { mode })}
										class={cn('h-8 rounded px-3 text-sm capitalize transition-colors focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none', current.mode === mode ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:text-foreground')}
									>{mode}</button>
								{/each}
							</div>
						</div>
						<div class="flex gap-2">
							<Button variant="outline" onclick={duplicate}><CopyIcon /> Duplicate</Button>
							<Button variant="outline" class="text-destructive hover:text-destructive" onclick={() => (deleteOpen = true)}><Trash2Icon /> Delete</Button>
						</div>
					</div>
					<p class="mt-3 text-xs text-muted-foreground">
						The surface says whether the theme is light or dark underneath. It tells the browser how to draw its own scrollbars and form controls, and it is how the
						colours that follow (cards a step lighter or darker than the page, lines) are worked out.
					</p>
				</section>

				<section class="rounded-xl border bg-card p-5">
					<h3 class="text-base font-semibold">Shape</h3>
					<div class="mt-4 grid gap-5 sm:grid-cols-2">
						<label class="block">
							<span class="flex items-baseline justify-between text-sm"><span class="font-medium">Corner radius</span><span class="font-mono text-xs text-muted-foreground">{current.radius}</span></span>
							<input
								type="range" min="0" max="1.25" step="0.025"
								value={radiusRem(current.radius)}
								oninput={(e) => updateTheme(themeId, { radius: radiusFromRem(Number(e.currentTarget.value)) })}
								class="mt-2 w-full accent-primary"
							/>
						</label>
						<label class="block">
							<span class="flex items-baseline justify-between text-sm"><span class="font-medium">Shadow under panels</span><span class="font-mono text-xs text-muted-foreground">{strength === null ? 'custom' : Math.round(strength * 100) + '%'}</span></span>
							<input
								type="range" min="0" max="0.8" step="0.01"
								value={strength ?? 0.4}
								disabled={strength === null}
								oninput={(e) => updateTheme(themeId, { shadowFloat: shadowFromStrength(Number(e.currentTarget.value)) })}
								class="mt-2 w-full accent-primary disabled:opacity-50"
							/>
						</label>
					</div>
				</section>

				{#each EDITOR_SECTIONS as section (section.title)}
					{@const followers = section.followers.flatMap((group) => group.entries)}
					{@const custom = followers.filter((entry) => follows(entry.token) === 'custom')}
					<section class="rounded-xl border bg-card p-5">
						<h3 class="text-base font-semibold">{section.title}</h3>
						<p class="mt-0.5 text-sm text-muted-foreground">{section.description}</p>
						<div class="mt-4 grid gap-x-6 gap-y-1 sm:grid-cols-2">
							{#each section.main as { token, label, hint } (token)}
								<ThemeColorField {label} {hint} value={current.colors[token]} onchange={(colour) => setColour(token, colour)} onsave={saveToPalette} />
							{/each}
						</div>

						{#if followers.length}
							<details class="group mt-4 rounded-lg border bg-background/40">
								<summary class="flex cursor-pointer list-none items-center gap-2 rounded-lg px-3 py-2.5 text-sm hover:bg-accent/40 focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none [&::-webkit-details-marker]:hidden">
									<ChevronRightIcon class="size-4 shrink-0 text-muted-foreground transition-transform group-open:rotate-90" />
									<span class="font-medium">Colours that follow</span>
									<span class="text-muted-foreground">{followers.length} shades{custom.length ? `, ${custom.length} set by hand` : ''}</span>
									<span class="ms-auto flex shrink-0 -space-x-1" aria-hidden="true">
										{#each followers.slice(0, 8) as entry (entry.token)}
											<span class="size-4 rounded-full border border-background" style="background-color: {current.colors[entry.token]}"></span>
										{/each}
									</span>
								</summary>
								<div class="space-y-5 border-t p-3">
									{#each section.followers as group (group.title)}
										<div>
											<h4 class="text-xs font-medium tracking-wide text-muted-foreground uppercase">{group.title}</h4>
											<div class="mt-1.5 grid gap-x-4 gap-y-1 sm:grid-cols-2">
												{#each group.entries as { token, label, hint } (token)}
													<ThemeColorField
														{label}
														{hint}
														value={current.colors[token]}
														follows={follows(token)}
														onchange={(colour) => setColour(token, colour)}
														onfollow={() => updateTheme(themeId, { follow: [token as DerivedToken] })}
														onsave={saveToPalette}
													/>
												{/each}
											</div>
										</div>
									{/each}
									{#if custom.length}
										<Button variant="outline" size="sm" onclick={() => updateTheme(themeId, { follow: custom.map((entry) => entry.token as DerivedToken) })}>Make all of these follow automatically</Button>
									{/if}
								</div>
							</details>
						{/if}
					</section>
				{/each}
			</div>

			<aside class="lg:sticky lg:top-20">
				<ThemePalette palette={current.palette} onchange={(palette) => updateTheme(themeId, { palette })} />
			</aside>
		</div>
	{/if}
</div>

<AlertDialog.Root bind:open={deleteOpen}>
	<AlertDialog.Content>
		<AlertDialog.Header>
			<AlertDialog.Title>Delete "{current?.name}"?</AlertDialog.Title>
			<AlertDialog.Description>The theme is removed from this browser and Themis Default takes its place. This cannot be undone.</AlertDialog.Description>
		</AlertDialog.Header>
		<AlertDialog.Footer>
			<AlertDialog.Cancel>Keep it</AlertDialog.Cancel>
			<AlertDialog.Action
				onclick={() => {
					deleteOpen = false
					deleteTheme(themeId)
					router.navigate('/settings')
				}}>Delete theme</AlertDialog.Action
			>
		</AlertDialog.Footer>
	</AlertDialog.Content>
</AlertDialog.Root>
