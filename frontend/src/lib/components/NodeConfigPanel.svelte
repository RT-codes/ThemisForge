<script lang="ts">
	import { Button } from '$lib/components/ui/button/index.js'
	import { Input } from '$lib/components/ui/input/index.js'
	import { Label } from '$lib/components/ui/label/index.js'
	import * as Select from '$lib/components/ui/select/index.js'
	import { Textarea } from '$lib/components/ui/textarea/index.js'
	import { kindInfo, visibleFields, type WorkflowNodeData } from '$lib/workflow'
	import { nodeIcons } from '$lib/workflowIcons'
	import Trash2Icon from '@lucide/svelte/icons/trash-2'
	import XIcon from '@lucide/svelte/icons/x'
	import { slide } from 'svelte/transition'

	let {
		id,
		data,
		onchange,
		onclose,
		ondelete,
	}: {
		id: string
		data: WorkflowNodeData
		onchange: (patch: Partial<WorkflowNodeData>) => void
		onclose: () => void
		ondelete: () => void
	} = $props()

	const info = $derived(kindInfo(data.kind))
	const Icon = $derived(nodeIcons[data.kind])
	const fields = $derived(visibleFields(data.kind, data.config))
	const setConfig = (key: string, value: string) => onchange({ config: { ...data.config, [key]: value } })
</script>

<div class="flex h-full w-80 flex-col">
	<div class="flex items-center gap-3 border-b px-4 py-3">
		<div class="flex size-8 shrink-0 items-center justify-center rounded-md bg-primary/15 text-primary"><Icon class="size-4" /></div>
		<div class="min-w-0 flex-1">
			<p class="truncate text-sm font-medium">{info.label} node</p>
			<p class="truncate text-xs text-muted-foreground">{info.description}</p>
		</div>
		<Button variant="ghost" size="icon-sm" aria-label="Close the panel" onclick={onclose}><XIcon /></Button>
	</div>

	<div class="grid min-h-0 flex-1 content-start gap-4 overflow-y-auto p-4">
		<div class="grid gap-1.5">
			<Label for="node-{id}-label">Name</Label>
			<Input id="node-{id}-label" value={data.label} oninput={(e) => onchange({ label: e.currentTarget.value })} />
		</div>

		{#each fields as f (f.key)}
			<div class="grid gap-1.5" transition:slide={{ duration: 160 }}>
				<Label for="node-{id}-{f.key}">{f.label}</Label>
				{#if f.type === 'select'}
					<Select.Root type="single" value={data.config[f.key]} onValueChange={(v) => setConfig(f.key, v)}>
						<Select.Trigger id="node-{id}-{f.key}" class="w-full">{f.options?.find((o) => o.value === data.config[f.key])?.label}</Select.Trigger>
						<Select.Content>
							{#each f.options ?? [] as o (o.value)}<Select.Item value={o.value} label={o.label}>{o.label}</Select.Item>{/each}
						</Select.Content>
					</Select.Root>
				{:else if f.type === 'time'}
					<Input id="node-{id}-{f.key}" type="time" value={data.config[f.key]} oninput={(e) => setConfig(f.key, e.currentTarget.value)} />
				{:else if f.type === 'textarea'}
					<Textarea id="node-{id}-{f.key}" rows={5} placeholder={f.placeholder} value={data.config[f.key]} oninput={(e) => setConfig(f.key, e.currentTarget.value)} />
				{:else}
					<Input id="node-{id}-{f.key}" placeholder={f.placeholder} value={data.config[f.key]} oninput={(e) => setConfig(f.key, e.currentTarget.value)} />
				{/if}
				{#if f.hint}<p class="text-xs text-muted-foreground">{f.hint}</p>{/if}
			</div>
		{/each}
	</div>

	<div class="border-t p-3">
		<Button variant="outline" size="sm" class="w-full text-destructive hover:text-destructive" onclick={ondelete}><Trash2Icon /> Delete node</Button>
	</div>
</div>
