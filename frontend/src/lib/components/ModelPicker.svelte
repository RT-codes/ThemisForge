<script lang="ts">
	import * as Select from '$lib/components/ui/select/index.js'
	import { Label } from '$lib/components/ui/label/index.js'
	import { effectiveEffort, effortAfterModelChange, effortLabel, effortsOf, modelLabel, type ModelInfo } from '$lib/models'
	import type { fieldIcons } from '$lib/workflowIcons'

	// The model and the reasoning effort of an agent or of one workflow step, as two dropdowns. Empty means "inherit",
	// and says what that is. The efforts offered follow the model, and changing the model drops an effort it does not
	// accept. Draws two grid cells, so the parent decides the layout. Both values go out in one call, so a parent that
	// keeps them in one object (a workflow node's settings) never overwrites one with the other.
	let {
		models,
		model,
		effort,
		onchange,
		inheritedModel,
		inheritedEffort,
		inheritLabel,
		prefix,
		modelIcon: ModelIcon,
		effortIcon: EffortIcon,
	}: {
		models: ModelInfo[]
		model: string
		effort: string
		onchange: (model: string, effort: string) => void
		inheritedModel: string // what an empty model resolves to, from the layer below
		inheritedEffort: string
		inheritLabel: string // where that comes from: "Default from Settings", "From the agent"
		prefix: string
		modelIcon?: (typeof fieldIcons)[string]
		effortIcon?: (typeof fieldIcons)[string]
	} = $props()

	const shownModel = $derived(model || inheritedModel)
	const known = $derived(models.some((m) => m.id === model))
	// a model of an agent file that is not in the list is still offered, so it does not silently change when saved
	const modelItems = $derived([
		{ value: '', label: `${inheritLabel}${inheritedModel ? ` (${modelLabel(models, inheritedModel)})` : ''}` },
		...(model && !known ? [{ value: model, label: model }] : []),
		...models.map((m) => ({ value: m.id, label: m.label })),
	])
	const supported = $derived(effortsOf(models, shownModel))
	// the effort that will really be used when none is chosen here (the layer below may ask for more than this model has)
	const inheritedUsed = $derived(inheritedEffort ? effectiveEffort(models, shownModel, inheritedEffort) : '')
	const effortItems = $derived([
		{ value: '', label: `${inheritLabel}${inheritedUsed ? ` (${effortLabel(inheritedUsed)})` : ''}` },
		...(effort && !supported.includes(effort) ? [{ value: effort, label: `${effortLabel(effort)} (not for this model)` }] : []),
		...supported.map((e) => ({ value: e, label: effortLabel(e) })),
	])
	const clamped = $derived(!effort && !!inheritedEffort && inheritedUsed !== inheritedEffort)

	const chooseModel = (id: string) => onchange(id, effortAfterModelChange(models, id || inheritedModel, effort))
</script>

<div class="grid gap-1.5">
	<Label for="{prefix}-model">
		{#if ModelIcon}<ModelIcon class="size-3.5 shrink-0 text-muted-foreground" />{/if}
		Model
	</Label>
	<Select.Root type="single" value={model} onValueChange={chooseModel}>
		<Select.Trigger id="{prefix}-model" class="w-full">{modelItems.find((i) => i.value === model)?.label ?? model}</Select.Trigger>
		<Select.Content>
			{#each modelItems as o (o.value)}<Select.Item value={o.value} label={o.label}>{o.label}</Select.Item>{/each}
		</Select.Content>
	</Select.Root>
</div>
<div class="grid gap-1.5">
	<Label for="{prefix}-effort">
		{#if EffortIcon}<EffortIcon class="size-3.5 shrink-0 text-muted-foreground" />{/if}
		Reasoning effort
	</Label>
	<Select.Root type="single" value={effort} onValueChange={(e) => onchange(model, e)}>
		<Select.Trigger id="{prefix}-effort" class="w-full">{effortItems.find((i) => i.value === effort)?.label ?? effort}</Select.Trigger>
		<Select.Content>
			{#each effortItems as o (o.value)}<Select.Item value={o.value} label={o.label}>{o.label}</Select.Item>{/each}
		</Select.Content>
	</Select.Root>
	{#if clamped}
		<p class="text-xs text-muted-foreground">{effortLabel(inheritedEffort)} is not available on {modelLabel(models, shownModel)}, so its own default is used.</p>
	{/if}
</div>
