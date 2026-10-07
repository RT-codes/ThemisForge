<script lang="ts">
	import { auth } from '$lib/auth.svelte'
	import { Button } from '$lib/components/ui/button/index.js'
	import { system } from '$lib/system.svelte'
	import ArrowUpCircleIcon from '@lucide/svelte/icons/circle-arrow-up'
	import XIcon from '@lucide/svelte/icons/x'
	import { slide } from 'svelte/transition'

	// Tells administrators a newer Themis exists. It never installs anything: upgrading is `themis upgrade` on the server,
	// which backs up first and goes back by itself if the new version does not start. Closing it hides that version only,
	// so the next release shows it again. (Remembered in this browser; if storage is unavailable it just comes back.)
	const KEY = 'themis.update.dismissed'
	const read = () => {
		try {
			return localStorage.getItem(KEY)
		} catch {
			return null
		}
	}
	let dismissed = $state(read())
	const update = $derived(system.update)
	const show = $derived(!!auth.user?.is_admin && !!update?.available && update.latest !== dismissed)

	function dismiss() {
		dismissed = update?.latest ?? null
		try {
			if (dismissed) localStorage.setItem(KEY, dismissed)
		} catch {
			// not remembered, that is all
		}
	}
</script>

{#if show && update}
	<div class="flex items-center gap-3 border-b border-primary/30 bg-primary/10 px-4 py-2 text-sm" role="status" transition:slide={{ duration: 200 }}>
		<ArrowUpCircleIcon class="size-4 shrink-0 text-primary" />
		<p class="min-w-0 flex-1">
			<span class="font-medium">Themis {update.latest} is available</span>
			<span class="text-muted-foreground">(you have {update.current}).</span>
			Run <code class="rounded bg-muted px-1.5 py-0.5 font-mono text-xs">themis upgrade</code> on the server to install it.
			{#if update.url}<a href={update.url} target="_blank" rel="noreferrer" class="underline underline-offset-2 hover:text-foreground">What is new</a>{/if}
		</p>
		<Button variant="ghost" size="icon-sm" class="shrink-0 text-muted-foreground" aria-label="Hide this until the next release" onclick={dismiss}><XIcon /></Button>
	</div>
{/if}
