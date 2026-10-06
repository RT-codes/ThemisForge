<script lang="ts">
	import { PALETTE, normalizeHex } from '$lib/colors'
	import { cn } from '$lib/utils'
	import BanIcon from '@lucide/svelte/icons/ban'
	import CheckIcon from '@lucide/svelte/icons/check'
	import { Popover } from 'bits-ui'

	// A small colour dot; pressing it opens a few swatches and a field for any colour of your own.
	let { value, onchange, label = 'Choose a colour' }: { value?: string; onchange: (colour: string | undefined) => void; label?: string } = $props()

	let open = $state(false)
	let typed = $state('')
	$effect(() => {
		if (open) typed = value ?? ''
	})

	// choosing a swatch (or no colour) is a decision, so the popup closes; dragging in the colour field keeps it open
	const pick = (c: string | undefined, close = true) => {
		onchange(c)
		if (close) open = false
	}
	function commitTyped() {
		const hex = normalizeHex(typed)
		if (hex) pick(hex)
		else typed = value ?? '' // not a colour: back to what it was
	}
</script>

<Popover.Root bind:open>
	<Popover.Trigger
		aria-label={label}
		title={label}
		class="inline-flex size-5 shrink-0 items-center justify-center rounded-full transition-transform hover:scale-110 focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
	>
		<span
			class={cn('size-3.5 rounded-full ring-1 ring-foreground/25', !value && 'bg-[conic-gradient(from_0deg,#f87171,#fbbf24,#34d399,#60a5fa,#a78bfa,#f87171)]')}
			style:background-color={value}
		></span>
	</Popover.Trigger>
	<Popover.Portal>
		<Popover.Content
			align="start"
			sideOffset={6}
			class="data-open:animate-in data-closed:animate-out data-closed:fade-out-0 data-open:fade-in-0 data-closed:zoom-out-95 data-open:zoom-in-95 z-[60] w-60 rounded-lg border bg-popover p-3 text-popover-foreground shadow-lg outline-none"
		>
			<div class="grid grid-cols-5 gap-2" role="group" aria-label="Colours">
				{#each PALETTE as c (c.hex)}
					<button
						type="button"
						aria-label={c.name}
						title={c.name}
						onclick={() => pick(c.hex)}
						class="flex size-8 items-center justify-center rounded-full ring-1 ring-foreground/20 transition-transform hover:scale-110 focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
						style:background-color={c.hex}
					>
						{#if value?.toLowerCase() === c.hex}<CheckIcon class="size-4 text-black/70" />{/if}
					</button>
				{/each}
			</div>
			<div class="mt-3 flex items-center gap-2 border-t pt-3">
				<input
					type="color"
					aria-label="Pick any colour"
					value={value ?? '#60a5fa'}
					oninput={(e) => pick(e.currentTarget.value, false)}
					class="size-8 shrink-0 cursor-pointer rounded-md border bg-transparent p-0.5"
				/>
				<input
					bind:value={typed}
					onchange={commitTyped}
					onkeydown={(e) => e.key === 'Enter' && (e.preventDefault(), commitTyped())}
					placeholder="#3b82f6"
					maxlength="7"
					spellcheck="false"
					aria-label="Colour code"
					class="h-8 min-w-0 flex-1 rounded-md border bg-transparent px-2 font-mono text-xs outline-none focus-visible:border-ring"
				/>
				<button
					type="button"
					aria-label="No colour"
					title="No colour"
					onclick={() => pick(undefined)}
					class="flex size-8 shrink-0 items-center justify-center rounded-md border text-muted-foreground transition-colors hover:text-foreground"
				>
					<BanIcon class="size-4" />
				</button>
			</div>
		</Popover.Content>
	</Popover.Portal>
</Popover.Root>
