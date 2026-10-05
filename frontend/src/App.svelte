<script lang="ts">
	import { auth } from '$lib/auth.svelte'
	import AppSidebar from '$lib/components/AppSidebar.svelte'
	import LoginScreen from '$lib/components/LoginScreen.svelte'
	import * as Sidebar from '$lib/components/ui/sidebar/index.js'
	import { Separator } from '$lib/components/ui/separator/index.js'
	import HomePage from '$lib/pages/HomePage.svelte'
	import ProjectPage from '$lib/pages/ProjectPage.svelte'
	import SettingsPage from '$lib/pages/SettingsPage.svelte'
	import { projects } from '$lib/projects.svelte'
	import { router } from '$lib/router.svelte'
	import { onMount } from 'svelte'

	onMount(() => auth.init())

	// the sidebar's project list (and its running badges) follow the signed-in user
	$effect(() => {
		if (!auth.user) return
		projects.refresh()
		const timer = setInterval(() => !document.hidden && projects.refresh().catch(() => {}), 10_000)
		return () => clearInterval(timer)
	})

	const route = $derived(router.route)
	const title = $derived(
		route.name === 'project'
			? (projects.get(route.id)?.name ?? 'Project')
			: route.name === 'settings'
				? 'Settings'
				: route.name === 'home'
					? 'Home'
					: 'Not found'
	)
</script>

{#if auth.loading}
	<div class="min-h-svh"></div>
{:else if !auth.user}
	<LoginScreen />
{:else}
	<Sidebar.Provider>
		<AppSidebar />
		<Sidebar.Inset class="min-w-0">
			<header class="flex h-14 shrink-0 items-center gap-2 border-b px-4">
				<Sidebar.Trigger class="-ms-1" />
				<Separator orientation="vertical" class="me-2 h-4 data-[orientation=vertical]:h-4 data-[orientation=vertical]:self-center" />
				<h1 class="truncate text-sm font-medium">{title}</h1>
			</header>
			<div class="forge-glow flex min-h-0 flex-1 flex-col">
				{#if route.name === 'home'}
					<HomePage />
				{:else if route.name === 'project'}
					{#key route.id}
						<ProjectPage id={route.id} />
					{/key}
				{:else if route.name === 'settings'}
					<SettingsPage />
				{:else}
					<div class="m-auto text-center">
						<p class="text-lg font-medium">Page not found</p>
						<a href="/" class="mt-2 inline-block text-sm text-primary hover:underline">Back home</a>
					</div>
				{/if}
			</div>
		</Sidebar.Inset>
	</Sidebar.Provider>
{/if}
