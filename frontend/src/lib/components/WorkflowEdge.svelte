<script lang="ts">
	import { BaseEdge, EdgeToolbar, getBezierPath, getSmoothStepPath, useSvelteFlow, type EdgeProps } from '@xyflow/svelte'
	import { EDGE_CURVES, type EdgeCurve } from '$lib/workflow'
	import { GLOW_MS, RUN_VIEW, type RunView } from '$lib/workflowRun.svelte'
	import { getContext } from 'svelte'

	// A connection between two nodes: a line in one of two styles (organic is the stock curve, angular only runs straight
	// up, down or sideways), plus what a test run adds to it. Selecting a line offers the choice. A line the run has gone
	// along (both ends have started) is drawn thicker, and when the run moves on along it, a glow travels from one node to
	// the next: it starts large at the first, shrinks to half in the middle and grows back at the end, like a pulse.
	let { id, source, target, sourceX, sourceY, targetX, targetY, sourcePosition, targetPosition, markerEnd, style, interactionWidth, selected, data }: EdgeProps = $props()

	const run = getContext<RunView | undefined>(RUN_VIEW)
	const { updateEdge } = useSvelteFlow()
	const curve = $derived<EdgeCurve>(data?.curve === 'angular' ? 'angular' : 'organic')
	// a smooth-step path with no corner radius is the "step" line: only horizontal and vertical pieces, sharp corners
	const [path, labelX, labelY] = $derived(
		curve === 'angular'
			? getSmoothStepPath({ sourceX, sourceY, targetX, targetY, sourcePosition, targetPosition, borderRadius: 0 })
			: getBezierPath({ sourceX, sourceY, targetX, targetY, sourcePosition, targetPosition }),
	)
	const setCurve = (value: EdgeCurve) => updateEdge(id, { data: { ...data, curve: value } })
	const walked = $derived(!!run?.active && !!run.shown[source] && !!run.shown[target])
	const glow = $derived(run?.edgePulses[id] ?? 0)
	const dur = `${GLOW_MS}ms`
</script>

<BaseEdge {id} {path} {markerEnd} {style} {interactionWidth} class={walked ? 'run-walked' : ''} />

{#if selected}
	<EdgeToolbar x={labelX} y={labelY} isVisible>
		<div class="flex gap-0.5 rounded-md border bg-card p-0.5 shadow-sm" role="group" aria-label="Line style">
			{#each EDGE_CURVES as c (c.value)}
				<button
					type="button"
					aria-pressed={curve === c.value}
					class="rounded px-2 py-0.5 text-xs transition-colors {curve === c.value ? 'bg-primary/20 text-foreground' : 'text-muted-foreground hover:text-foreground'}"
					onclick={() => setCurve(c.value)}>{c.label}</button
				>
			{/each}
		</div>
	</EdgeToolbar>
{/if}

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
