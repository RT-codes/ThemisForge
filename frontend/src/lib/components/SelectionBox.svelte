<script lang="ts">
	import { NodeToolbar, Position, ViewportPortal, useViewport, type Node } from '@xyflow/svelte'
	import { Button } from '$lib/components/ui/button/index.js'
	import Trash2Icon from '@lucide/svelte/icons/trash-2'
	import XIcon from '@lucide/svelte/icons/x'
	import { fade } from 'svelte/transition'

	// What shows when more than one node is selected, however it was selected (a box, Shift or Ctrl): a padded box around
	// all of them, and a toolbar on its top right corner to act on them together. The box ignores the pointer, so the nodes
	// inside stay as easy to grab, connect and drag as before (Svelte Flow's own selection overlay sits on top of them and
	// swallows every click, which is why it is hidden: see .svelte-flow__selection-wrapper in app.css).
	let { selected, ondelete, onclear }: { selected: Node[]; ondelete: () => void; onclear: () => void } = $props()

	const PAD = 16 // flow units around the nodes
	const viewport = useViewport()

	// nodes are about 208 x 56 until they have been measured
	const box = $derived.by(() => {
		if (selected.length < 2) return null
		let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity
		for (const n of selected) {
			x0 = Math.min(x0, n.position.x)
			y0 = Math.min(y0, n.position.y)
			x1 = Math.max(x1, n.position.x + (n.measured?.width ?? 208))
			y1 = Math.max(y1, n.position.y + (n.measured?.height ?? 56))
		}
		return { x: x0 - PAD, y: y0 - PAD, w: x1 - x0 + PAD * 2, h: y1 - y0 + PAD * 2 }
	})
</script>

{#if box}
	<ViewportPortal target="back">
		<div class="selection-box" style:width="{box.w}px" style:height="{box.h}px" style:transform="translate({box.x}px, {box.y}px)" transition:fade={{ duration: 180 }}></div>
	</ViewportPortal>
	<!-- the toolbar keeps its size at any zoom; it sits above the box's right end, clear of the padding -->
	<NodeToolbar nodeId={selected.map((n) => n.id)} isVisible position={Position.Top} align="end" offset={PAD * viewport.current.zoom + 8}>
		<div class="nodrag nopan flex items-center gap-1 rounded-lg border bg-popover p-1 text-popover-foreground shadow-md" in:fade={{ duration: 180 }}>
			<span class="px-2 text-xs text-muted-foreground">{selected.length} selected</span>
			<Button variant="ghost" size="icon-sm" class="size-7 text-muted-foreground" aria-label="Deselect" title="Deselect (Esc)" onclick={onclear}><XIcon class="size-3.5" /></Button>
			<Button variant="ghost" size="icon-sm" class="size-7 text-muted-foreground hover:text-destructive" aria-label="Delete the selected nodes" title="Delete the selected nodes" onclick={ondelete}><Trash2Icon class="size-3.5" /></Button>
		</div>
	</NodeToolbar>
{/if}
