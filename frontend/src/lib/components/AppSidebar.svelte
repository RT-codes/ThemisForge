<script lang="ts">
	import SidebarPlus from '$lib/components/SidebarPlus.svelte'
	import { auth } from '$lib/auth.svelte'
	import * as Avatar from '$lib/components/ui/avatar/index.js'
	import * as DropdownMenu from '$lib/components/ui/dropdown-menu/index.js'
	import * as Sidebar from '$lib/components/ui/sidebar/index.js'
	import ChevronsUpDownIcon from '@lucide/svelte/icons/chevrons-up-down'
	import HouseIcon from '@lucide/svelte/icons/house'
	import BotIcon from '@lucide/svelte/icons/bot'
	import BookOpenIcon from '@lucide/svelte/icons/book-open'
	import FolderKanbanIcon from '@lucide/svelte/icons/folder-kanban'
	import LayoutDashboardIcon from '@lucide/svelte/icons/layout-dashboard'
	import ListChecksIcon from '@lucide/svelte/icons/list-checks'
	import LogOutIcon from '@lucide/svelte/icons/log-out'
	import SettingsIcon from '@lucide/svelte/icons/settings'
	import WorkflowIcon from '@lucide/svelte/icons/workflow'
	import UsersIcon from '@lucide/svelte/icons/users'
	import { inbox } from '$lib/inbox.svelte'
	import { projects } from '$lib/projects.svelte'
	import { router } from '$lib/router.svelte'
	import Logo from './Logo.svelte'
	import ProjectDialog from './project/ProjectDialog.svelte'

	let createOpen = $state(false)
	const route = $derived(router.route)

	const user = $derived(auth.user)
	const initials = $derived(
		(user?.name ?? '?')
			.split(/\s+/)
			.map((p) => p[0])
			.slice(0, 2)
			.join('')
			.toUpperCase()
	)

	// a clicked link gets a short border-and-shine pulse (see .nav-pulse in app.css);
	// the plus beside a link pulses that link too
	function pulse(e: MouseEvent) {
		const target = e.target as Element | null
		const link =
			target?.closest('a[data-sidebar="menu-button"], a[data-sidebar="menu-sub-button"]') ??
			(target?.closest('a[data-pulse-sibling]') &&
				target.closest('[data-sidebar="menu-sub-item"]')?.querySelector('a[data-sidebar="menu-sub-button"]'))
		if (!link) return
		link.classList.remove('nav-pulse')
		void (link as HTMLElement).offsetWidth // restart the animation when clicked again
		link.classList.add('nav-pulse')
	}
</script>

<svelte:window onclick={pulse} />

<Sidebar.Root>
	<Sidebar.Header>
		<div class="flex items-center gap-2.5 px-2 py-1.5">
			<Logo />
			<span class="text-base font-semibold tracking-tight">ThemisForge</span>
		</div>
	</Sidebar.Header>

	<Sidebar.Separator class="mx-4 data-horizontal:w-auto" />

	<Sidebar.Content>
		<Sidebar.Group>
			<Sidebar.GroupContent>
				<Sidebar.Menu>
					<Sidebar.MenuItem>
						<Sidebar.MenuButton isActive={route.name === 'home'}>
							{#snippet child({ props })}
								<a href="/" {...props}><HouseIcon /><span>Home</span></a>
							{/snippet}
						</Sidebar.MenuButton>
					</Sidebar.MenuItem>
					<Sidebar.MenuItem>
						<Sidebar.MenuButton isActive={route.name === 'docs'}>
							{#snippet child({ props })}
								<a href="/docs" {...props}><BookOpenIcon /><span>Docs</span></a>
							{/snippet}
						</Sidebar.MenuButton>
					</Sidebar.MenuItem>
				</Sidebar.Menu>
			</Sidebar.GroupContent>
		</Sidebar.Group>

		<Sidebar.Separator class="mx-4 data-horizontal:w-auto" />

		<Sidebar.Group>
			<Sidebar.GroupLabel>Projects</Sidebar.GroupLabel>
			<SidebarPlus label="New project" class="end-3 top-3.5" onclick={() => (createOpen = true)} />
			<Sidebar.GroupContent>
				<Sidebar.Menu>
					{#each projects.list as p (p.id)}
						{@const open = (route.name === 'project' || route.name === 'workflow' || route.name === 'agents') && route.id === p.id}
						<Sidebar.MenuItem>
							<Sidebar.MenuButton>
								{#snippet child({ props })}
									<a href="/projects/{p.id}" {...props}><FolderKanbanIcon /><span>{p.name}</span></a>
								{/snippet}
							</Sidebar.MenuButton>
							{#if (p.task_counts.running ?? 0) > 0}
								<Sidebar.MenuBadge>{p.task_counts.running}</Sidebar.MenuBadge>
							{/if}
							{#if open}
								<Sidebar.MenuSub class="tree-branch">
									<Sidebar.MenuSubItem class="tree-leaf">
										<Sidebar.MenuSubButton isActive={route.name === 'project' && route.page === 'overview'} class="me-2.5">
											{#snippet child({ props })}
												<a href="/projects/{p.id}" {...props}><LayoutDashboardIcon /><span>Overview</span></a>
											{/snippet}
										</Sidebar.MenuSubButton>
									</Sidebar.MenuSubItem>
									<Sidebar.MenuSubItem class="tree-leaf">
										<Sidebar.MenuSubButton isActive={route.name === 'project' && route.page === 'tasks'} class="me-2.5">
											{#snippet child({ props })}
												<a href="/projects/{p.id}/tasks" {...props}><ListChecksIcon /><span>Tasks</span></a>
											{/snippet}
										</Sidebar.MenuSubButton>
									</Sidebar.MenuSubItem>
									<Sidebar.MenuSubItem class="tree-leaf">
										<Sidebar.MenuSubButton isActive={route.name === 'agents'} class="me-2.5">
											{#snippet child({ props })}
												<a href="/projects/{p.id}/agents" {...props}><BotIcon /><span>Agents</span></a>
											{/snippet}
										</Sidebar.MenuSubButton>
										<SidebarPlus label="New agent" href="/projects/{p.id}/agents/new" class="-end-[1.2rem] top-1/2 -translate-y-1/2" />
									</Sidebar.MenuSubItem>
									<Sidebar.MenuSubItem class="tree-leaf">
										<Sidebar.MenuSubButton isActive={route.name === 'workflow'} class="me-2.5">
											{#snippet child({ props })}
												<a href="/projects/{p.id}/workflows" {...props}><WorkflowIcon /><span>Workflow editor</span></a>
											{/snippet}
										</Sidebar.MenuSubButton>
										<SidebarPlus label="New workflow" href="/projects/{p.id}/workflows/new" class="-end-[1.2rem] top-1/2 -translate-y-1/2" />
									</Sidebar.MenuSubItem>
								</Sidebar.MenuSub>
							{/if}
						</Sidebar.MenuItem>
					{:else}
						{#if projects.loaded}
							<p class="px-2 py-1.5 text-xs text-sidebar-foreground/60">No projects yet</p>
						{/if}
					{/each}
				</Sidebar.Menu>
			</Sidebar.GroupContent>
		</Sidebar.Group>
	</Sidebar.Content>

	<Sidebar.Footer>
		<Sidebar.Menu>
			{#if user?.is_admin}
				<Sidebar.MenuItem>
					<Sidebar.MenuButton isActive={route.name === 'access'}>
						{#snippet child({ props })}
							<a href="/access" {...props}><UsersIcon /><span>Access</span></a>
						{/snippet}
					</Sidebar.MenuButton>
					{#if inbox.pendingAccess > 0}
						<Sidebar.MenuBadge>{inbox.pendingAccess}</Sidebar.MenuBadge>
					{/if}
				</Sidebar.MenuItem>
			{/if}
			<Sidebar.MenuItem>
				<Sidebar.MenuButton isActive={route.name === 'settings'}>
					{#snippet child({ props })}
						<a href="/settings" {...props}><SettingsIcon /><span>Settings</span></a>
					{/snippet}
				</Sidebar.MenuButton>
			</Sidebar.MenuItem>
			<Sidebar.MenuItem>
				<DropdownMenu.Root>
					<DropdownMenu.Trigger>
						{#snippet child({ props })}
							<Sidebar.MenuButton size="lg" class="data-[state=open]:bg-sidebar-accent" {...props}>
								<Avatar.Root class="size-8 rounded-lg">
									<Avatar.Fallback class="rounded-lg bg-primary/15 font-medium text-primary">
										{initials}
									</Avatar.Fallback>
								</Avatar.Root>
								<div class="grid flex-1 text-start text-sm leading-tight">
									<span class="truncate font-medium">{user?.name}</span>
									<span class="truncate text-xs text-muted-foreground">{user?.email}</span>
								</div>
								<ChevronsUpDownIcon class="ms-auto size-4" />
							</Sidebar.MenuButton>
						{/snippet}
					</DropdownMenu.Trigger>
					<DropdownMenu.Content side="top" align="start" class="w-(--bits-dropdown-menu-anchor-width) min-w-56">
						<DropdownMenu.Item onSelect={() => auth.logout()}>
							<LogOutIcon />
							Log out
						</DropdownMenu.Item>
					</DropdownMenu.Content>
				</DropdownMenu.Root>
			</Sidebar.MenuItem>
		</Sidebar.Menu>
	</Sidebar.Footer>
</Sidebar.Root>

<ProjectDialog bind:open={createOpen} onsaved={async (p) => (await projects.refresh(), router.navigate(`/projects/${p.id}`))} />
