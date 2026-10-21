<script lang="ts">
	import type { Board, Workspace } from '$lib/api/projects'
	import type { Task, TaskStatus } from '$lib/api/tasks'
	import { columnsOf, destinationLabel, lineage, statusLabel, statusTone } from '$lib/boards'
	import StatusIcon from '$lib/components/StatusIcon.svelte'
	import { Button } from '$lib/components/ui/button/index.js'
	import * as DropdownMenu from '$lib/components/ui/dropdown-menu/index.js'
	import * as Select from '$lib/components/ui/select/index.js'
	import * as Tabs from '$lib/components/ui/tabs/index.js'
	import { cn } from '$lib/utils'
	import ArrowRightIcon from '@lucide/svelte/icons/arrow-right'
	import ChevronDownIcon from '@lucide/svelte/icons/chevron-down'
	import GitBranchPlusIcon from '@lucide/svelte/icons/git-branch-plus'

	// The panel's taskbar, one row: where the task is (a menu to send it to another board, or to follow it up there), its
	// status, and the switch between its details and its history. Under it, which task it follows and which followed it.
	// It also serves a task that is not made yet: then there is only the board and the status to start it in.
	let {
		task,
		board,
		tasks,
		workspaces,
		status,
		busy,
		showTabs,
		onstatus,
		onsend,
		onfollowup,
		onopen,
	}: {
		/** null while a new task is being written */
		task: Task | null
		/** the board it is on (or will be made on) */
		board: Board
		tasks: Task[]
		workspaces: Workspace[]
		status: TaskStatus
		busy: boolean
		/** the Details and History switch needs the panel's Tabs around it, which an existing task has */
		showTabs: boolean
		onstatus: (status: TaskStatus) => void
		onsend: () => void
		onfollowup: () => void
		onopen: (task: Task) => void
	} = $props()

	const columns = $derived(columnsOf(board))
	const current = $derived(columns.find((c) => c.id === status))
	// only the scheduler starts tasks, and one that is running cannot be moved by hand
	const running = $derived(status === 'running')
	const boardCount = $derived(workspaces.flatMap((w) => w.boards).length)
	const links = $derived(task ? lineage(tasks, task) : { origin: null, followUps: [] })
	const boardOf = (t: Task) => workspaces.flatMap((w) => w.boards).find((b) => b.id === t.board_id)
</script>

<div class="mx-4 mb-3 grid gap-2">
	<div class="flex flex-wrap items-center gap-2 rounded-lg border bg-card/40 p-1.5">
		{#if task}
			<DropdownMenu.Root>
				<DropdownMenu.Trigger>
					{#snippet child({ props })}
						<Button {...props} variant="ghost" size="sm" class="h-8 min-w-0 max-w-48 gap-1.5 px-2" title="On board: {destinationLabel(workspaces, board)}">
							<span class="truncate">{destinationLabel(workspaces, board)}</span>
							<ChevronDownIcon class="size-3.5 shrink-0 text-muted-foreground" />
						</Button>
					{/snippet}
				</DropdownMenu.Trigger>
				<DropdownMenu.Content align="start" class="w-56">
					<DropdownMenu.Label class="text-xs font-normal text-muted-foreground">On this board</DropdownMenu.Label>
					<DropdownMenu.Item disabled={busy || running || boardCount < 2} onSelect={onsend}>
						<ArrowRightIcon /> Send to another board...
					</DropdownMenu.Item>
					<DropdownMenu.Item disabled={busy} onSelect={onfollowup}><GitBranchPlusIcon /> Create a follow-up...</DropdownMenu.Item>
					{#if running}
						<p class="px-2 py-1.5 text-xs text-muted-foreground">Cancel the run before sending it.</p>
					{/if}
				</DropdownMenu.Content>
			</DropdownMenu.Root>
		{:else}
			<span class="max-w-48 truncate px-2 text-sm text-muted-foreground" title="On board">{destinationLabel(workspaces, board)}</span>
		{/if}

		<Select.Root type="single" value={status} onValueChange={(v) => v && v !== status && onstatus(v as TaskStatus)} disabled={running || busy}>
			<Select.Trigger
				class="h-8 w-auto min-w-36 gap-2"
				aria-label="Status"
				title={running ? 'A cell is working on this task. Cancel it to change the status.' : current?.hint}
			>
				<span class="flex min-w-0 items-center gap-2">
					<span class={cn('shrink-0', !current?.color && statusTone(status).text)} style:color={current?.color ?? undefined}>
						<StatusIcon {status} icon={current?.icon ?? ''} class="size-4" />
					</span>
					<span class="truncate">{statusLabel(status, board)}</span>
				</span>
			</Select.Trigger>
			<Select.Content>
				{#each columns.filter((c) => c.id !== 'running') as c (c.id)}
					<Select.Item value={c.id} label={c.label}>
						<span class={cn('shrink-0', !c.color && statusTone(c.id).text)} style:color={c.color ?? undefined}>
							<StatusIcon status={c.id} icon={c.icon} class="size-4" />
						</span>
						{c.label}
					</Select.Item>
				{/each}
			</Select.Content>
		</Select.Root>

		{#if showTabs}
			<Tabs.List class="ms-auto">
				<Tabs.Trigger value="details">Details</Tabs.Trigger>
				<Tabs.Trigger value="history">History</Tabs.Trigger>
			</Tabs.List>
		{/if}
	</div>

	{#if links.origin || links.followUps.length}
		<ul class="grid gap-1 px-1 text-xs">
			{#if links.origin}
				<li class="flex items-baseline gap-1.5">
					<span class="text-muted-foreground">Follows</span>
					<button type="button" class="truncate font-medium text-primary hover:underline" onclick={() => onopen(links.origin!)}>{links.origin.title}</button>
					{#if boardOf(links.origin)}<span class="shrink-0 text-muted-foreground">on {destinationLabel(workspaces, boardOf(links.origin)!)}</span>{/if}
				</li>
			{/if}
			{#each links.followUps as f (f.id)}
				<li class="flex items-baseline gap-1.5">
					<span class="text-muted-foreground">Followed by</span>
					<button type="button" class="truncate font-medium text-primary hover:underline" onclick={() => onopen(f)}>{f.title}</button>
					{#if boardOf(f)}<span class="shrink-0 text-muted-foreground">on {destinationLabel(workspaces, boardOf(f)!)}</span>{/if}
				</li>
			{/each}
		</ul>
	{/if}
</div>
