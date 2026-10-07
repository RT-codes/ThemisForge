<script lang="ts">
	import { auth } from '$lib/auth.svelte'
	import { system } from '$lib/system.svelte'
	import AlertTriangleIcon from '@lucide/svelte/icons/triangle-alert'
	import { slide } from 'svelte/transition'

	// Shown on every page while Docker cannot run cells. Tasks are not failing: they wait, and start by themselves as
	// soon as Docker works again. Administrators are told what is wrong and where to fix it; everyone else who to ask.
	const docker = $derived(system.problems.find((p) => p.id === 'docker' && p.level === 'fail'))
</script>

{#if !system.cellsReady}
	<div class="flex items-start gap-3 border-b border-yellow-500/30 bg-yellow-500/10 px-4 py-2 text-sm text-yellow-200" role="alert" transition:slide={{ duration: 200 }}>
		<AlertTriangleIcon class="mt-0.5 size-4 shrink-0" />
		<p class="min-w-0">
			<span class="font-medium">Runs are paused.</span>
			{#if auth.user?.is_admin && docker}
				{docker.message.replace(/[.?!]+$/, '')}. {docker.hint}
				<a href="/settings#docker" class="underline underline-offset-2 hover:text-foreground">Open the Docker settings</a>.
			{:else if auth.user?.is_admin}
				Docker cannot run cells right now.
				<a href="/settings#docker" class="underline underline-offset-2 hover:text-foreground">Open the Docker settings</a>.
			{:else}
				Docker is not available on the server, so agents cannot start. Ask an administrator to look at it.
			{/if}
			Waiting tasks start by themselves once it works again.
		</p>
	</div>
{/if}
