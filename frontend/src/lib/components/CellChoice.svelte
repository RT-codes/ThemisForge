<script lang="ts">
	import type { CellDefaults, ProfileOverrides } from '$lib/api'
	import ProfileFields from '$lib/components/ProfileFields.svelte'
	import { Button } from '$lib/components/ui/button/index.js'
	import { describeCell } from '$lib/cell'
	import { untrack } from 'svelte'

	// Which cell something runs in. Automatic by default: it says what it uses and nothing else, so nobody has to
	// understand the options. Only "Customise" shows them, and "Back to automatic" takes the overrides away again.
	let {
		value = $bindable(null),
		inherited,
		source,
		prefix,
		imagePlaceholder = '',
	}: {
		value: ProfileOverrides | null
		inherited: CellDefaults | null // what automatic means here
		source: string // where that comes from, as a phrase: "the project's cell"
		prefix: string
		imagePlaceholder?: string
	} = $props()

	// a choice, not a derived value: a person who opened the fields and has not typed yet is still customising
	let customising = $state(untrack(() => value !== null))

	function backToAutomatic() {
		value = null
		customising = false
	}
</script>

{#if customising}
	<div class="grid gap-3">
		<div class="flex flex-wrap items-center gap-x-3 gap-y-2">
			<p class="min-w-0 flex-1 basis-44 text-sm text-muted-foreground">Customised. Anything left empty still uses {source}.</p>
			<Button type="button" variant="outline" size="sm" onclick={backToAutomatic}>Back to automatic</Button>
		</div>
		<ProfileFields bind:value {inherited} {prefix} inheritedFrom={source} {imagePlaceholder} />
	</div>
{:else}
	<div class="flex min-w-0 items-center gap-3 rounded-lg border bg-background/40 px-3 py-2.5">
		<div class="min-w-0 flex-1">
			<p class="text-sm font-medium">Automatic</p>
			<p class="text-xs text-muted-foreground">Uses {source}{inherited ? `: ${describeCell(inherited)}` : ''}</p>
		</div>
		<Button type="button" variant="outline" size="sm" onclick={() => (customising = true)}>Customise</Button>
	</div>
{/if}
