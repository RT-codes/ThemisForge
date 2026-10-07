<script lang="ts">
	import { api, type FileEntry } from '$lib/api'
	import { Button } from '$lib/components/ui/button/index.js'
	import { clampPan, scaleToSlider, sliderToScale, zoomAt, type Zoom } from '$lib/files'
	import ZoomInIcon from '@lucide/svelte/icons/zoom-in'
	import ZoomOutIcon from '@lucide/svelte/icons/zoom-out'
	import { fade } from 'svelte/transition'

	// A picture that can be zoomed: the wheel, the slider and a drag all change the same view. It fills its parent, which
	// FilePreview positions; `loading` says the picture is not there yet (the spinner is FilePreview's).
	let {
		volumeId,
		path,
		entry,
		loading,
		onload,
		onerror,
	}: { volumeId: number; path: string; entry: FileEntry; loading: boolean; onload: () => void; onerror: () => void } = $props()

	const FIT: Zoom = { scale: 1, x: 0, y: 0 }
	let zoom = $state<Zoom>(FIT)
	let smooth = $state(false) // buttons and reset glide; the wheel and dragging follow the hand without delay
	let box = $state<HTMLElement>()
	let picture = $state<HTMLElement>()
	let panning: { x: number; y: number; from: Zoom } | null = null
	const zoomed = $derived(zoom.scale > 1.001)

	// layout sizes: they do not change with the zoom, which is what the limits are worked out from
	function sizes() {
		const rect = box!.getBoundingClientRect()
		return { rect, box: { w: rect.width, h: rect.height }, image: { w: picture!.offsetWidth, h: picture!.offsetHeight } }
	}

	/** zoom to `scale` around a point of the view (default: its centre) */
	function zoomTo(scale: number, at = { x: 0, y: 0 }, glide = true) {
		if (!box || !picture) return
		smooth = glide
		const { box: b, image } = sizes()
		zoom = zoomAt(zoom, scale, at, b, image)
	}

	$effect(() => {
		const el = box
		if (!el) return
		// not a plain onwheel: it has to be able to stop the page from scrolling while the pointer is over the picture
		const onwheel = (e: WheelEvent) => {
			e.preventDefault()
			const { rect } = sizes()
			const at = { x: e.clientX - (rect.left + rect.width / 2), y: e.clientY - (rect.top + rect.height / 2) }
			// a pinch on a trackpad arrives as a wheel with ctrl held, in much smaller steps
			zoomTo(zoom.scale * Math.exp(-e.deltaY * (e.ctrlKey ? 0.01 : 0.0015)), at, false)
		}
		el.addEventListener('wheel', onwheel, { passive: false })
		return () => el.removeEventListener('wheel', onwheel)
	})

	function grab(e: PointerEvent) {
		if (!zoomed) return
		panning = { x: e.clientX, y: e.clientY, from: zoom }
		;(e.currentTarget as HTMLElement).setPointerCapture(e.pointerId)
	}
	function move(e: PointerEvent) {
		if (!panning) return
		smooth = false
		const { box: b, image } = sizes()
		zoom = { scale: zoom.scale, ...clampPan(panning.from.x + e.clientX - panning.x, panning.from.y + e.clientY - panning.y, zoom.scale, b, image) }
	}
	const fit = () => ((smooth = true), (zoom = FIT))
</script>

<div bind:this={box} class="relative flex min-h-0 flex-1 items-center justify-center overflow-hidden">
	<!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
	<img
		bind:this={picture}
		src={api.fileUrl(volumeId, path, false, entry.modified)}
		alt={entry.name}
		draggable="false"
		class="border object-contain select-none {entry.name.toLowerCase().endsWith('.svg') ? 'h-full w-full' : 'max-h-full max-w-full'} {zoomed ? 'cursor-grab active:cursor-grabbing' : ''}"
		style:opacity={loading ? 0 : 1}
		style:transform="translate({zoom.x}px, {zoom.y}px) scale({zoom.scale})"
		style:transition="opacity 300ms, transform {smooth ? '200ms' : '0ms'}"
		{onload}
		{onerror}
		onpointerdown={grab}
		onpointermove={move}
		onpointerup={() => (panning = null)}
		onpointercancel={() => (panning = null)}
		ondblclick={fit}
	/>
	{#if !loading}
		<!-- the zoom controls: a slider that follows the wheel, with the percentage as the way back to "fit" -->
		<div class="absolute end-2 bottom-2 flex flex-col items-center gap-1.5 rounded-full border bg-card/80 px-1 py-2 backdrop-blur" transition:fade={{ duration: 200 }}>
			<Button variant="ghost" size="icon-sm" class="size-6 text-muted-foreground" aria-label="Zoom in" onclick={() => zoomTo(zoom.scale * 1.5)}><ZoomInIcon class="size-3.5" /></Button>
			<input
				type="range"
				min="0"
				max="100"
				step="1"
				value={scaleToSlider(zoom.scale)}
				aria-label="Zoom"
				class="h-24 w-4 cursor-pointer accent-primary"
				style="writing-mode: vertical-lr; direction: rtl"
				oninput={(e) => zoomTo(sliderToScale(Number(e.currentTarget.value)), undefined, false)}
			/>
			<Button variant="ghost" size="icon-sm" class="size-6 text-muted-foreground" aria-label="Zoom out" onclick={() => zoomTo(zoom.scale / 1.5)}><ZoomOutIcon class="size-3.5" /></Button>
			<button
				type="button"
				class="min-w-9 rounded px-1 text-center text-[0.65rem] text-muted-foreground tabular-nums transition-colors hover:text-foreground disabled:pointer-events-none"
				title="Fit to view"
				aria-label="Fit to view"
				disabled={!zoomed}
				onclick={fit}
			>
				{Math.round(zoom.scale * 100)}%
			</button>
		</div>
	{/if}
</div>
