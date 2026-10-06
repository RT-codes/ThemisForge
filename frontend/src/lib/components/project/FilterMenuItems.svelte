<script lang="ts">
	import type { PropertyDef } from '$lib/api'
	import { HARNESS_CHOICES, NO_VALUE, SCHEDULE_CHOICES, filterCount, selectProperties, toggled, type Filters } from '$lib/boardView'
	import * as DropdownMenu from '$lib/components/ui/dropdown-menu/index.js'

	// What to narrow the cards by. Each group is "any of these"; groups together are "all of these". A menu item
	// does not close the menu, so several can be ticked in a row.
	let { filters, defs, onchange }: { filters: Filters; defs: PropertyDef[]; onchange: (filters: Filters) => void } = $props()

	const selects = $derived(selectProperties(defs))
</script>

<DropdownMenu.Label class="text-xs text-muted-foreground">Schedule</DropdownMenu.Label>
{#each SCHEDULE_CHOICES as c (c.id)}
	<DropdownMenu.CheckboxItem checked={filters.schedule.includes(c.id)} onCheckedChange={() => onchange({ ...filters, schedule: toggled(filters.schedule, c.id) })}>
		{c.label}
	</DropdownMenu.CheckboxItem>
{/each}

<DropdownMenu.Separator />
<DropdownMenu.Label class="text-xs text-muted-foreground">Runs with</DropdownMenu.Label>
{#each HARNESS_CHOICES as c (c.id)}
	<DropdownMenu.CheckboxItem checked={filters.harness.includes(c.id)} onCheckedChange={() => onchange({ ...filters, harness: toggled(filters.harness, c.id) })}>
		{c.label}
	</DropdownMenu.CheckboxItem>
{/each}

{#each selects as d (d.key)}
	<DropdownMenu.Separator />
	<DropdownMenu.Label class="text-xs text-muted-foreground">{d.name}</DropdownMenu.Label>
	{#each [...d.options, NO_VALUE] as option (option)}
		<DropdownMenu.CheckboxItem
			checked={(filters.props[d.key] ?? []).includes(option)}
			onCheckedChange={() => onchange({ ...filters, props: { ...filters.props, [d.key]: toggled(filters.props[d.key] ?? [], option) } })}
		>
			{#if option !== NO_VALUE && d.colors?.[option]}
				<span class="size-2.5 shrink-0 rounded-full ring-1 ring-foreground/20" style:background-color={d.colors[option]}></span>
			{/if}
			{option === NO_VALUE ? `No ${d.name.toLowerCase()}` : option}
		</DropdownMenu.CheckboxItem>
	{/each}
{/each}

{#if filterCount(filters) > 0}
	<DropdownMenu.Separator />
	<DropdownMenu.Item closeOnSelect={false} onSelect={() => onchange({ schedule: [], harness: [], props: {} })}>Clear filters</DropdownMenu.Item>
{/if}
