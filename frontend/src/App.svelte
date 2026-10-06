<script lang="ts">
	import { auth } from '$lib/auth.svelte'
	import ChevronRightIcon from '@lucide/svelte/icons/chevron-right'
	import AppSidebar from '$lib/components/AppSidebar.svelte'
	import InviteScreen from '$lib/components/InviteScreen.svelte'
	import LoginScreen from '$lib/components/LoginScreen.svelte'
	import * as Sidebar from '$lib/components/ui/sidebar/index.js'
	import { Separator } from '$lib/components/ui/separator/index.js'
	import AccessPage from '$lib/pages/AccessPage.svelte'
	import HomePage from '$lib/pages/HomePage.svelte'
	import ProjectOverview from '$lib/pages/ProjectOverview.svelte'
	import WorkflowResume from '$lib/pages/WorkflowResume.svelte'
	import ProjectPage from '$lib/pages/ProjectPage.svelte'
	import SettingsPage from '$lib/pages/SettingsPage.svelte'
	import { inbox } from '$lib/inbox.svelte'
	import { projects } from '$lib/projects.svelte'
	import { router } from '$lib/router.svelte'
	import { onMount } from 'svelte'
	import { fade } from 'svelte/transition'

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
	// a new page fades in; switching between tabs of the same project counts as a new page too
	const pageKey = $derived(
		route.name === 'project' ? `project:${route.id}:${route.page}` : route.name === 'workflow' ? `workflow:${route.id}` : route.name
	)
	type Crumb = { label: string; href?: string }
	// the top bar says where you are; every part but the last leads back up
	const crumbs = $derived.by<Crumb[]>(() => {
		if (route.name === 'workflow' || route.name === 'project') {
			const project: Crumb = { label: projects.get(route.id)?.name ?? 'Project', href: `/projects/${route.id}` }
			const page = route.name === 'workflow' ? 'Workflow editor' : route.page === 'tasks' ? 'Tasks' : 'Overview'
			return [project, { label: page }]
		}
		const single: Record<string, string> = { settings: 'Settings', access: 'Access', docs: 'Docs', home: 'Home' }
		return [{ label: single[route.name] ?? 'Not found' }]
	})
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
				<nav aria-label="Breadcrumb" class="flex min-w-0 items-center gap-1.5 text-sm">
					{#each crumbs as crumb, i (i)}
						{#if i > 0}<ChevronRightIcon class="size-3.5 shrink-0 text-muted-foreground/60" aria-hidden="true" />{/if}
						{#if crumb.href && i < crumbs.length - 1}
							<a href={crumb.href} class="truncate text-muted-foreground transition-colors hover:text-foreground">{crumb.label}</a>
						{:else}
							<h1 class="truncate font-medium" aria-current="page">{crumb.label}</h1>
						{/if}
					{/each}
				</nav>
			</header>
			<div class="forge-glow flex min-h-0 flex-1 flex-col">
				{#key pageKey}
				<div class="flex min-h-0 flex-1 flex-col" in:fade={{ duration: 350 }}>
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
						{#if route.resume}
							<WorkflowResume projectId={route.id} />
						{:else}
							{#await loadWorkflow() then editor}
								<editor.default projectId={route.id} workflowId={route.workflowId} run={route.run} />
							{/await}
						{/if}
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
				{/key}
			</div>
		</Sidebar.Inset>
	</Sidebar.Provider>
{/if}
