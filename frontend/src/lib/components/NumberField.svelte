<script lang="ts">
	import { Input } from '$lib/components/ui/input/index.js'

	// A number with its unit inside the box, so labels do not need "(MB)" or "(seconds)".
	let {
		id,
		value = $bindable(0),
		unit,
		min,
		max,
		step,
		required = true,
	}: { id: string; value?: number; unit: string; min?: number; max?: number; step?: number; required?: boolean } = $props()
</script>

<div class="relative">
	<Input {id} type="number" {min} {max} {step} {required} bind:value class="pe-16" />
	<span class="pointer-events-none absolute end-3 top-1/2 -translate-y-1/2 text-xs text-muted-foreground">{unit}</span>
</div>
