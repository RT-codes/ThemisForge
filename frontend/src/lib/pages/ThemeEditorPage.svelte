<script lang="ts">
	import { allThemes, deleteTheme, duplicateThemeOf, setTheme, theme, updateTheme } from '$lib/appearance'
	import ThemeColorField from '$lib/components/ThemeColorField.svelte'
	import * as AlertDialog from '$lib/components/ui/alert-dialog/index.js'
	import { Button } from '$lib/components/ui/button/index.js'
	import { Input } from '$lib/components/ui/input/index.js'
	import { router } from '$lib/router.svelte'
	import { findTheme, isBuiltinTheme, MAX_THEME_NAME, radiusFromRem, radiusRem, shadowFromStrength, shadowStrength, THEME_COLOR_GROUPS } from '$lib/themes'
	import { cn } from '$lib/utils'
	import { untrack } from 'svelte'
	import ArrowLeftIcon from '@lucide/svelte/icons/arrow-left'
	import CopyIcon from '@lucide/svelte/icons/copy'
	import Trash2Icon from '@lucide/svelte/icons/trash-2'

	// The editor of a custom theme. It edits the theme that is in use, so every change shows on this very page (and
	// everywhere else) as you make it, and each change is saved in this browser at once, so there is no Save button. The
	// built-in themes cannot be edited, but they can be duplicated, and the copy is yours to change.
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

	const strength = $derived(current ? shadowStrength(current.shadowFloat) : null)
	let deleteOpen = $state(false)

	function duplicate() {
		const copy = duplicateThemeOf(themeId)
		if (!copy) return
		setTheme(copy.id)
		router.navigate(`/settings/themes/${copy.id}`)
	}
</script>

<div class="w-full max-w-4xl px-6 py-8">
	<a href="/settings" class="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground"><ArrowLeftIcon class="size-4" /> Settings</a>

	{#if !current}
		<h2 class="mt-4 text-2xl font-semibold tracking-tight">Theme not found</h2>
		<p class="mt-1 text-sm text-muted-foreground">This theme does not exist in this browser. Themes you make are saved per browser.</p>
	{:else if builtin}
		<h2 class="mt-4 text-2xl font-semibold tracking-tight">{current.name}</h2>
		<p class="mt-1 text-sm text-muted-foreground">Built-in themes cannot be edited. Duplicate it to make a copy that is yours to change.</p>
		<Button class="mt-6" onclick={duplicate}><CopyIcon /> Duplicate to edit</Button>
	{:else}
		<h2 class="mt-4 text-2xl font-semibold tracking-tight">Edit theme</h2>
		<p class="mt-1 text-sm text-muted-foreground">Changes show across Themis as you make them and are saved in this browser.</p>

		<section class="mt-6 rounded-xl border bg-card p-5">
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
				The surface says whether the theme is light or dark underneath: it tells the browser how to draw its own scrollbars and form controls.
			</p>
		</section>

		<section class="mt-4 rounded-xl border bg-card p-5">
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

		{#each THEME_COLOR_GROUPS as group (group.title)}
			<section class="mt-4 rounded-xl border bg-card p-5">
				<h3 class="text-base font-semibold">{group.title}</h3>
				<p class="mt-0.5 text-sm text-muted-foreground">{group.description}</p>
				<div class="mt-4 grid gap-x-6 gap-y-3 sm:grid-cols-2">
					{#each group.tokens as { token, label } (token)}
						<ThemeColorField {label} value={current.colors[token]} onchange={(colour) => updateTheme(themeId, { colors: { [token]: colour } })} />
					{/each}
				</div>
			</section>
		{/each}
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
