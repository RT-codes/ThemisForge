<script lang="ts">
	import type { RunStatus } from '$lib/api/workflows'
	import { STAGE_TONE } from '$lib/stageTrack'
	import { cn } from '$lib/utils'
	import BanIcon from '@lucide/svelte/icons/ban'
	import CircleCheckIcon from '@lucide/svelte/icons/circle-check'
	import CircleDotIcon from '@lucide/svelte/icons/circle-dot'
	import CircleDashedIcon from '@lucide/svelte/icons/circle-dashed'
	import CircleXIcon from '@lucide/svelte/icons/circle-x'
	import LoaderCircleIcon from '@lucide/svelte/icons/loader-circle'

	// The icon of a stage: dashed circle until it starts, then a spinner, a check, a cross or a slashed circle.
	// `still` swaps the spinner for a dot that does not move, where something else beside it already spins.
	let { status, still = false, class: className }: { status: 'pending' | RunStatus; still?: boolean; class?: string } = $props()

	const icons = {
		pending: CircleDashedIcon,
		running: LoaderCircleIcon,
		succeeded: CircleCheckIcon,
		failed: CircleXIcon,
		cancelled: BanIcon,
	}
	const spinning = $derived(status === 'running' && !still)
	const Icon = $derived(status === 'running' && still ? CircleDotIcon : icons[status])
</script>

<Icon class={cn('shrink-0', STAGE_TONE[status], spinning && 'animate-spin', className)} />
