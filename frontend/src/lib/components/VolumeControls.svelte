<script lang="ts">
	import type { Volume } from '$lib/api'
	import * as Select from '$lib/components/ui/select/index.js'
	import { Switch } from '$lib/components/ui/switch/index.js'
	import { accessLabel } from '$lib/format'

	// What can be set on a shared folder: whether cells may write, and whether writers take turns. Both the project
	// overview and the Files page show these, so a change made in one place is the same change as in the other.
	let { volume: v, onchange }: { volume: Volume; onchange: (patch: { mode?: 'ro' | 'rw'; exclusive_write?: boolean }) => void } = $props()
</script>

{#if v.mode === 'rw' && !v.problem}
	<label class="flex items-center gap-2 text-xs text-muted-foreground" title="Only one run at a time may write here; the others wait for their turn">
		<Switch checked={v.exclusive_write} onCheckedChange={(on) => onchange({ exclusive_write: on })} aria-label="Writers take turns in {v.name}" />
		Writers take turns
	</label>
{/if}
<Select.Root type="single" value={v.mode} onValueChange={(m) => onchange({ mode: m as 'ro' | 'rw' })}>
	<Select.Trigger size="sm" class="w-40" aria-label="Access to {v.name}">{accessLabel(v.mode)}</Select.Trigger>
	<Select.Content>
		<Select.Item value="rw" label="Read and write" disabled={!v.can_write}>Read and write</Select.Item>
		<Select.Item value="ro" label="Read only">Read only</Select.Item>
	</Select.Content>
</Select.Root>
