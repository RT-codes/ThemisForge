<script lang="ts">
	import { SORTS, type SortKey } from '$lib/boardView'
	import * as DropdownMenu from '$lib/components/ui/dropdown-menu/index.js'

	// The choices for ordering cards. A column can also "follow the board" (value null).
	let { value, inherit, onchange }: { value: SortKey | null; inherit?: string; onchange: (sort: SortKey | null) => void } = $props()
</script>

<DropdownMenu.RadioGroup value={value ?? 'inherit'} onValueChange={(v) => onchange(v === 'inherit' ? null : (v as SortKey))}>
	{#if inherit}<DropdownMenu.RadioItem value="inherit" closeOnSelect>{inherit}</DropdownMenu.RadioItem>{/if}
	{#each SORTS as s (s.id)}
		<DropdownMenu.RadioItem value={s.id} closeOnSelect>{s.label}</DropdownMenu.RadioItem>
	{/each}
</DropdownMenu.RadioGroup>
