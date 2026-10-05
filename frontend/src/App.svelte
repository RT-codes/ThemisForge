<script lang="ts">
	import { auth } from '$lib/auth.svelte'
	import AppSidebar from '$lib/components/AppSidebar.svelte'
	import FlowCanvas from '$lib/components/FlowCanvas.svelte'
	import LoginScreen from '$lib/components/LoginScreen.svelte'
	import * as Sidebar from '$lib/components/ui/sidebar/index.js'
	import { Separator } from '$lib/components/ui/separator/index.js'
	import { onMount } from 'svelte'

	onMount(() => auth.init())
</script>

{#if auth.loading}
	<div class="min-h-svh"></div>
{:else if !auth.user}
	<LoginScreen />
{:else}
	<Sidebar.Provider>
		<AppSidebar />
		<Sidebar.Inset>
			<header class="flex h-14 shrink-0 items-center gap-2 border-b px-4">
				<Sidebar.Trigger class="-ms-1" />
				<Separator orientation="vertical" class="me-2 h-4 data-[orientation=vertical]:h-4 data-[orientation=vertical]:self-center" />
				<h1 class="text-sm font-medium">Home</h1>
			</header>
			<div class="forge-glow flex flex-1 flex-col">
				<div class="px-6 pt-8 pb-4">
					<h2 class="text-2xl font-semibold tracking-tight">Welcome, {auth.user.name.split(' ')[0]}</h2>
					<p class="text-sm text-muted-foreground">Your forge is ready. This canvas is powered by Svelte Flow.</p>
				</div>
				<div class="mx-6 mb-6 min-h-96 flex-1 overflow-hidden rounded-xl border">
					<FlowCanvas />
				</div>
			</div>
		</Sidebar.Inset>
	</Sidebar.Provider>
{/if}
