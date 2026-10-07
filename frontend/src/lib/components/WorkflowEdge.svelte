<script lang="ts">
	import { BaseEdge, getBezierPath, type EdgeProps } from '@xyflow/svelte'
	import { GLOW_MS, RUN_VIEW, type RunView } from '$lib/workflowRun.svelte'
	import { getContext } from 'svelte'

	// A connection between two nodes: the stock curved line, plus what a test run adds to it. A line the run has gone
	// along (both ends have started) is drawn thicker, and when the run moves on along it, a glow travels from one node to
	// the next: it starts large at the first, shrinks to half in the middle and grows back at the end, like a pulse.
	let { id, source, target, sourceX, sourceY, targetX, targetY, sourcePosition, targetPosition, markerEnd, style, interactionWidth }: EdgeProps = $props()

	const run = getContext<RunView | undefined>(RUN_VIEW)
	const [path] = $derived(getBezierPath({ sourceX, sourceY, targetX, targetY, sourcePosition, targetPosition }))
	const walked = $derived(!!run?.active && !!run.shown[source] && !!run.shown[target])
	const glow = $derived(run?.edgePulses[id] ?? 0)
	const dur = `${GLOW_MS}ms`
</script>

<BaseEdge {id} {path} {markerEnd} {style} {interactionWidth} class={walked ? 'run-walked' : ''} />

{#if glow > 0}
	<!-- a new key starts the animation again for every pulse -->
	{#key glow}
		<g class="run-glow" pointer-events="none">
			<circle r="9">
				<animateMotion {dur} {path} fill="freeze" calcMode="linear" />
				<animate attributeName="r" values="9;4.5;9" keyTimes="0;0.5;1" {dur} fill="freeze" />
				<animate attributeName="opacity" values="0;1;1;1;0" keyTimes="0;0.12;0.5;0.85;1" {dur} fill="freeze" />
			</circle>
		</g>
	{/key}
{/if}
