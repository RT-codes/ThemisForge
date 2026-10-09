<script lang="ts">
	import { Input } from '$lib/components/ui/input/index.js'
	import { Label } from '$lib/components/ui/label/index.js'

	// The two numbers of the automation guard. An empty box means "use the default": a project's boxes fall back to
	// Settings, a task's to its project (see app/automation.py on the server).
	let {
		cooldown = $bindable(null),
		hops = $bindable(null),
		prefix,
		fallback,
	}: {
		cooldown: number | null
		hops: number | null
		/** makes the element ids unique when two of these are on a page */
		prefix: string
		/** where an empty box gets its value, in words: "Settings" or "the project" */
		fallback: string
	} = $props()

	const read = (text: string) => (text.trim() === '' ? null : Number(text))
</script>

<div class="grid gap-3 sm:grid-cols-2">
	<div class="grid gap-1.5">
		<Label for="{prefix}-cooldown">Wait before starting</Label>
		<div class="relative">
			<Input
				id="{prefix}-cooldown"
				type="number"
				min={0}
				max={3600}
				value={cooldown ?? ''}
				placeholder="From {fallback}"
				class="pe-16"
				oninput={(e) => (cooldown = read(e.currentTarget.value))}
			/>
			<span class="pointer-events-none absolute end-3 top-1/2 -translate-y-1/2 text-xs text-muted-foreground">seconds</span>
		</div>
		<p class="text-xs text-muted-foreground">How long after a change a task, or a workflow for it, may start.</p>
	</div>
	<div class="grid gap-1.5">
		<Label for="{prefix}-hops">Most automatic moves in a row</Label>
		<Input
			id="{prefix}-hops"
			type="number"
			min={1}
			max={100}
			value={hops ?? ''}
			placeholder="From {fallback}"
			oninput={(e) => (hops = read(e.currentTarget.value))}
		/>
		<p class="text-xs text-muted-foreground">Then workflows stop moving or making the same task, until a person acts on it.</p>
	</div>
</div>
