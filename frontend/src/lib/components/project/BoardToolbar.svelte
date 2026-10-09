<script lang="ts">
	import type { PropertyDef } from '$lib/api'
	import { SORTS, filterCount, isDefaultColumn, isDefaultView } from '$lib/boardView'
	import type { BoardViewStore } from '$lib/boardView.svelte'
	import { Button } from '$lib/components/ui/button/index.js'
	import * as DropdownMenu from '$lib/components/ui/dropdown-menu/index.js'
	import { Input } from '$lib/components/ui/input/index.js'
	import type { ColumnInfo } from '$lib/boards'
	import { cn } from '$lib/utils'
	import ArrowUpDownIcon from '@lucide/svelte/icons/arrow-up-down'
	import EyeIcon from '@lucide/svelte/icons/eye'
	import ListFilterIcon from '@lucide/svelte/icons/list-filter'
	import SearchIcon from '@lucide/svelte/icons/search'
	import XIcon from '@lucide/svelte/icons/x'
	import FilterMenuItems from './FilterMenuItems.svelte'
	import SortMenuItems from './SortMenuItems.svelte'

	// The controls for the whole board: search, order and filters. Each status can add its own below its title.
	let { view, defs, columns, onmanage }: { view: BoardViewStore; defs: PropertyDef[]; columns: ColumnInfo[]; onmanage: () => void } = $props()

	const sorted = $derived(view.board.sort !== 'manual')
	const filters = $derived(filterCount(view.board.filters))
	const hiddenCount = $derived(columns.filter((s) => view.hidden.includes(s.id)).length)
	const anything = $derived(!isDefaultView(view.board) || Object.values(view.columns).some((c) => !isDefaultColumn(c)))
</script>

<div class="flex flex-wrap items-center gap-2">
	<div class="relative">
		<SearchIcon class="pointer-events-none absolute start-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
		<Input
			value={view.board.search}
			oninput={(e) => view.setBoard({ search: e.currentTarget.value })}
			placeholder="Search tasks"
			aria-label="Search tasks"
			class="h-8 w-48 ps-8 pe-8"
		/>
		{#if view.board.search}
			<button
				type="button"
				aria-label="Clear the search"
				class="absolute end-1.5 top-1/2 flex size-5 -translate-y-1/2 items-center justify-center rounded text-muted-foreground transition-colors hover:text-foreground"
				onclick={() => view.setBoard({ search: '' })}
			>
				<XIcon class="size-3.5" />
			</button>
		{/if}
	</div>

	<DropdownMenu.Root>
		<DropdownMenu.Trigger>
			{#snippet child({ props })}
				<Button {...props} variant="outline" size="sm" class={cn('h-8 gap-1.5', sorted && 'border-primary/50 text-primary')} aria-label="Order the whole board">
					<ArrowUpDownIcon />
					{sorted ? SORTS.find((s) => s.id === view.board.sort)?.label : 'Order'}
				</Button>
			{/snippet}
		</DropdownMenu.Trigger>
		<DropdownMenu.Content align="start" class="w-52">
			<DropdownMenu.Label class="text-xs text-muted-foreground">Order every status by</DropdownMenu.Label>
			<SortMenuItems value={view.board.sort} onchange={(sort) => view.setBoard({ sort: sort ?? 'manual' })} />
		</DropdownMenu.Content>
	</DropdownMenu.Root>

	<DropdownMenu.Root>
		<DropdownMenu.Trigger>
			{#snippet child({ props })}
				<Button {...props} variant="outline" size="sm" class={cn('h-8 gap-1.5', filters > 0 && 'border-primary/50 text-primary')} aria-label="Filter the whole board">
					<ListFilterIcon />
					Filter
					{#if filters > 0}<span class="rounded-full bg-primary/20 px-1.5 text-xs tabular-nums">{filters}</span>{/if}
				</Button>
			{/snippet}
		</DropdownMenu.Trigger>
		<DropdownMenu.Content align="start" class="max-h-[70vh] w-64 overflow-y-auto">
			<FilterMenuItems filters={view.board.filters} {defs} onchange={(f) => view.setBoard({ filters: f })} />
		</DropdownMenu.Content>
	</DropdownMenu.Root>

	<DropdownMenu.Root>
		<DropdownMenu.Trigger>
			{#snippet child({ props })}
				<Button {...props} variant="outline" size="sm" class={cn('h-8 gap-1.5', hiddenCount > 0 && 'border-primary/50 text-primary')} aria-label="Choose which statuses to show">
					<EyeIcon />
					Statuses
					{#if hiddenCount > 0}<span class="rounded-full bg-primary/20 px-1.5 text-xs tabular-nums">{columns.length - hiddenCount}/{columns.length}</span>{/if}
				</Button>
			{/snippet}
		</DropdownMenu.Trigger>
		<DropdownMenu.Content align="start" class="w-52">
			<DropdownMenu.Label class="text-xs text-muted-foreground">Show these statuses</DropdownMenu.Label>
			{#each columns as s (s.id)}
				<DropdownMenu.CheckboxItem checked={!view.hidden.includes(s.id)} onCheckedChange={() => view.toggleHidden(s.id)}>
					{s.label}
				</DropdownMenu.CheckboxItem>
			{/each}
			{#if hiddenCount > 0}
				<DropdownMenu.Separator />
				<DropdownMenu.Item closeOnSelect={false} onSelect={() => view.showAll()}>Show all</DropdownMenu.Item>
			{/if}
			<DropdownMenu.Separator />
			<DropdownMenu.Item onSelect={onmanage}>Add or edit statuses...</DropdownMenu.Item>
		</DropdownMenu.Content>
	</DropdownMenu.Root>

	{#if anything}
		<Button variant="ghost" size="sm" class="h-8 text-muted-foreground" onclick={() => view.reset()}>Reset</Button>
	{/if}
</div>
