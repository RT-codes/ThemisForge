<script lang="ts">
	import { auth } from '$lib/auth.svelte'
	import AppSidebar from '$lib/components/AppSidebar.svelte'
	import InviteScreen from '$lib/components/InviteScreen.svelte'
	import LoginScreen from '$lib/components/LoginScreen.svelte'
	import * as Sidebar from '$lib/components/ui/sidebar/index.js'
	import { Separator } from '$lib/components/ui/separator/index.js'
	import AccessPage from '$lib/pages/AccessPage.svelte'
	import HomePage from '$lib/pages/HomePage.svelte'
	import ProjectOverview from '$lib/pages/ProjectOverview.svelte'
	import ProjectPage from '$lib/pages/ProjectPage.svelte'
	import SettingsPage from '$lib/pages/SettingsPage.svelte'
	import { inbox } from '$lib/inbox.svelte'
	import { projects } from '$lib/projects.svelte'
	import { router } from '$lib/router.svelte'
	import { onMount } from 'svelte'

	// the editor pulls in the flow library, so it loads on first visit
	const loadWorkflow = () => import('$lib/pages/WorkflowEditorPage.svelte')

	// the docs are only loaded when someone opens them
	const loadDocs = () => import('$lib/pages/DocsPage.svelte')

	onMount(() => auth.init())

	// the sidebar's project list (and its running badges) follow the signed-in user
	$effect(() => {
		if (!auth.user) return
		const tick = () => {
			projects.refresh().catch(() => {})
			if (auth.user?.is_admin) inbox.refresh()
		}
		tick()
		const timer = setInterval(() => !document.hidden && tick(), 10_000)
		return () => clearInterval(timer)
	})

	const route = $derived(router.route)
	const title = $derived(
		route.name === 'workflow'
			? (projects.get(route.id)?.name ?? 'Project') + ' / Workflow'
			: route.name === 'project'
			? (projects.get(route.id)?.name ?? 'Project') + (route.page === 'tasks' ? ' / Tasks' : '')
			: route.name === 'settings'
				? 'Settings'
				: route.name === 'access'
					? 'Access'
					: route.name === 'docs'
						? 'Docs'
						: route.name === 'home'
							? 'Home'
							: 'Not found'
	)
</script>

{#if auth.loading}
	<div class="min-h-svh"></div>
{:else if !auth.user}
	{#if route.name === 'invite'}
		<InviteScreen token={route.token} />
	{:else if route.name === 'docs'}
		<div class="flex min-h-svh flex-col">
			{#await loadDocs() then docs}
				<docs.default slug={route.slug} standalone />
			{/await}
		</div>
	{:else}
		<LoginScreen />
	{/if}
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
						{#if route.page === 'tasks'}
							<ProjectPage id={route.id} />
						{:else}
							<ProjectOverview id={route.id} />
						{/if}
					{/key}
				{:else if route.name === 'workflow'}
					{#key route.id}
						{#await loadWorkflow() then editor}
							<editor.default projectId={route.id} workflowId={route.workflowId} run={route.run} />
						{/await}
					{/key}
				{:else if route.name === 'settings'}
					<SettingsPage />
				{:else if route.name === 'access'}
					<AccessPage />
				{:else if route.name === 'docs'}
					{#await loadDocs() then docs}
						<docs.default slug={route.slug} />
					{/await}
				{:else if route.name === 'invite'}
					<div class="m-auto max-w-sm text-center">
						<p class="text-lg font-medium">You are already signed in</p>
						<p class="mt-1 text-sm text-muted-foreground">Invite links are for people without an account. Log out first to use this one.</p>
					</div>
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
