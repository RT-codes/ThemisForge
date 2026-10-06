<script lang="ts">
	import type { PropertyDef } from '$lib/api'
	import { SORTS, filterCount, isDefaultColumn } from '$lib/boardView'
	import type { BoardViewStore } from '$lib/boardView.svelte'
	import { Button } from '$lib/components/ui/button/index.js'
	import * as DropdownMenu from '$lib/components/ui/dropdown-menu/index.js'
	import { cn } from '$lib/utils'
	import ArrowUpDownIcon from '@lucide/svelte/icons/arrow-up-down'
	import ListFilterIcon from '@lucide/svelte/icons/list-filter'
	import XIcon from '@lucide/svelte/icons/x'
	import FilterMenuItems from './FilterMenuItems.svelte'
	import SortMenuItems from './SortMenuItems.svelte'

	// The small bar under a status title: order and filter just this status, on top of the board's own settings.
	let { view, status, label, defs }: { view: BoardViewStore; status: string; label: string; defs: PropertyDef[] } = $props()

	const column = $derived(view.column(status))
	const filters = $derived(filterCount(column.filters))
</script>

<div class="flex items-center gap-0.5 px-2 pb-2">
	<DropdownMenu.Root>
		<DropdownMenu.Trigger>
			{#snippet child({ props })}
				<Button {...props} variant="ghost" size="xs" class={cn('text-muted-foreground', column.sort && 'text-primary')} aria-label={`Order ${label}`}>
					<ArrowUpDownIcon />
					{column.sort ? SORTS.find((s) => s.id === column.sort)?.label : 'Order'}
				</Button>
			{/snippet}
		</DropdownMenu.Trigger>
		<DropdownMenu.Content align="start" class="w-52">
			<DropdownMenu.Label class="text-xs text-muted-foreground">Order {label}</DropdownMenu.Label>
			<SortMenuItems value={column.sort} inherit="Same as the board" onchange={(sort) => view.setColumn(status, { sort })} />
		</DropdownMenu.Content>
	</DropdownMenu.Root>

	<DropdownMenu.Root>
		<DropdownMenu.Trigger>
			{#snippet child({ props })}
				<Button {...props} variant="ghost" size="xs" class={cn('text-muted-foreground', filters > 0 && 'text-primary')} aria-label={`Filter ${label}`}>
					<ListFilterIcon />
					Filter
					{#if filters > 0}<span class="rounded-full bg-primary/20 px-1 tabular-nums">{filters}</span>{/if}
				</Button>
			{/snippet}
		</DropdownMenu.Trigger>
		<DropdownMenu.Content align="start" class="max-h-[60vh] w-64 overflow-y-auto">
			<DropdownMenu.Label class="text-xs text-muted-foreground">Only in {label}</DropdownMenu.Label>
			<FilterMenuItems filters={column.filters} {defs} onchange={(f) => view.setColumn(status, { filters: f })} />
		</DropdownMenu.Content>
	</DropdownMenu.Root>

	{#if !isDefaultColumn(column)}
		<Button variant="ghost" size="icon-xs" class="ms-auto text-muted-foreground" aria-label={`Reset ${label}`} title="Reset this status" onclick={() => view.resetColumn(status)}>
			<XIcon />
		</Button>
	{/if}
</div>
