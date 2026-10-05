<script lang="ts">
	import { auth } from '$lib/auth.svelte'
	import * as Avatar from '$lib/components/ui/avatar/index.js'
	import * as DropdownMenu from '$lib/components/ui/dropdown-menu/index.js'
	import * as Sidebar from '$lib/components/ui/sidebar/index.js'
	import ChevronsUpDownIcon from '@lucide/svelte/icons/chevrons-up-down'
	import HouseIcon from '@lucide/svelte/icons/house'
	import FolderKanbanIcon from '@lucide/svelte/icons/folder-kanban'
	import LogOutIcon from '@lucide/svelte/icons/log-out'
	import PlusIcon from '@lucide/svelte/icons/plus'
	import SettingsIcon from '@lucide/svelte/icons/settings'
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
</script>

<Sidebar.Root>
	<Sidebar.Header>
		<div class="flex items-center gap-2.5 px-2 py-1.5">
			<Logo />
			<span class="text-base font-semibold tracking-tight">ThemisForge</span>
		</div>
	</Sidebar.Header>

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
				</Sidebar.Menu>
			</Sidebar.GroupContent>
		</Sidebar.Group>

		<Sidebar.Group>
			<Sidebar.GroupLabel>Projects</Sidebar.GroupLabel>
			<Sidebar.GroupAction title="New project" onclick={() => (createOpen = true)}>
				<PlusIcon /><span class="sr-only">New project</span>
			</Sidebar.GroupAction>
			<Sidebar.GroupContent>
				<Sidebar.Menu>
					{#each projects.list as p (p.id)}
						<Sidebar.MenuItem>
							<Sidebar.MenuButton isActive={route.name === 'project' && route.id === p.id}>
								{#snippet child({ props })}
									<a href="/projects/{p.id}" {...props}><FolderKanbanIcon /><span>{p.name}</span></a>
								{/snippet}
							</Sidebar.MenuButton>
							{#if (p.task_counts.running ?? 0) > 0}
								<Sidebar.MenuBadge>{p.task_counts.running}</Sidebar.MenuBadge>
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
					<Sidebar.MenuButton isActive={route.name === 'settings'}>
						{#snippet child({ props })}
							<a href="/settings" {...props}><SettingsIcon /><span>Settings</span></a>
						{/snippet}
					</Sidebar.MenuButton>
				</Sidebar.MenuItem>
			{/if}
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
