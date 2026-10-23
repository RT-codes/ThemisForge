<script lang="ts">
	import OctagonXIcon from '@lucide/svelte/icons/octagon-x'

	// Shown for as long as a project or a board is halted, so a quiet board is never a mystery. The Resume button is in
	// the page's own header, next to where the halt was made.
	let { scope, name }: { scope: 'project' | 'board'; name: string } = $props()
</script>

<div class="flex items-center gap-2 rounded-lg border border-tone-amber/40 bg-tone-amber/10 px-3 py-2 text-sm text-tone-amber" role="status">
	<OctagonXIcon class="size-4 shrink-0" />
	<span class="min-w-0">
		<span class="font-medium">{scope === 'project' ? 'This project is halted' : `"${name}" is halted`}.</span>
		Nothing {scope === 'project' ? 'in it' : 'on this board'} will start until it is resumed.
	</span>
</div>
