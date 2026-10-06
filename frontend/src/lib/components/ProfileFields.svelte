<script lang="ts">
	import type { CellDefaults, ProfileOverrides } from '$lib/api'
	import { Input } from '$lib/components/ui/input/index.js'
	import { Label } from '$lib/components/ui/label/index.js'

	// The cell size a project or an agent may change. Every field is optional: empty means "keep what it inherits",
	// and the inherited value is shown as the placeholder so nobody has to guess what empty means.
	let {
		value = $bindable(null),
		inherited,
		prefix,
		inheritedFrom = 'the default',
		imagePlaceholder = '',
	}: {
		value: ProfileOverrides | null
		inherited: CellDefaults | null
		prefix: string
		inheritedFrom?: string
		imagePlaceholder?: string // what an empty image means here, when it is not simply the inherited one
	} = $props()

	// a field that is emptied leaves the override; when none are left, the whole override goes
	function set(key: keyof ProfileOverrides, raw: string) {
		const next: ProfileOverrides = { ...(value ?? {}) }
		const text = raw.trim()
		if (text === '') delete next[key]
		else if (key === 'image') next.image = text
		else next[key] = Number(text)
		value = Object.keys(next).length ? next : null
	}
	const text = (key: keyof ProfileOverrides) => (value?.[key] === undefined || value?.[key] === null ? '' : String(value[key]))
</script>

<div class="@container grid gap-3 @sm:grid-cols-3">
	<div class="grid gap-1.5">
		<Label for="{prefix}-cpus">CPUs</Label>
		<Input id="{prefix}-cpus" type="number" min="0.1" max="64" step="any" placeholder={inherited ? String(inherited.cpus) : ''} value={text('cpus')} oninput={(e) => set('cpus', e.currentTarget.value)} />
	</div>
	<div class="grid gap-1.5">
		<Label for="{prefix}-mem">Memory (MB)</Label>
		<Input id="{prefix}-mem" type="number" min="64" step="1" placeholder={inherited ? String(inherited.memory_mb) : ''} value={text('memory_mb')} oninput={(e) => set('memory_mb', e.currentTarget.value)} />
	</div>
	<div class="grid gap-1.5">
		<Label for="{prefix}-time">Time limit (s)</Label>
		<Input id="{prefix}-time" type="number" min="10" step="1" placeholder={inherited ? String(inherited.timeout_seconds) : ''} value={text('timeout_seconds')} oninput={(e) => set('timeout_seconds', e.currentTarget.value)} />
	</div>
	<div class="grid gap-1.5 @sm:col-span-3">
		<Label for="{prefix}-image">Image</Label>
		<Input id="{prefix}-image" class="font-mono" placeholder={imagePlaceholder || (inherited?.image ?? '')} value={text('image')} oninput={(e) => set('image', e.currentTarget.value)} />
		<p class="text-xs text-muted-foreground">
			Leave a field empty to keep {inheritedFrom}. Only set an image that has what the agent needs, such as the Codex CLI.
		</p>
	</div>
</div>
