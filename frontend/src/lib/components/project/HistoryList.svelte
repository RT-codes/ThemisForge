<script lang="ts">
	import { projectsApi, type ProjectEvent, type Workspace } from '$lib/api/projects'
	import type { Task } from '$lib/api/tasks'
	import { Button } from '$lib/components/ui/button/index.js'
	import * as Select from '$lib/components/ui/select/index.js'
	import { dateTime, relative } from '$lib/format'
	import { KIND_GROUPS, describeEvent, historyQuery, type HistoryScope } from '$lib/history'
	import { cn } from '$lib/utils'
	import type { Snippet } from 'svelte'
	import ArrowRightIcon from '@lucide/svelte/icons/arrow-right'
	import CircleAlertIcon from '@lucide/svelte/icons/circle-alert'
	import GitBranchPlusIcon from '@lucide/svelte/icons/git-branch-plus'
	import HistoryIcon from '@lucide/svelte/icons/history'
	import LayersIcon from '@lucide/svelte/icons/layers'
	import ListPlusIcon from '@lucide/svelte/icons/list-plus'
	import OctagonXIcon from '@lucide/svelte/icons/octagon-x'
	import PencilIcon from '@lucide/svelte/icons/pencil'
	import PlayIcon from '@lucide/svelte/icons/play'
	import PlusIcon from '@lucide/svelte/icons/plus'
	import Trash2Icon from '@lucide/svelte/icons/trash-2'

	// What was done in the project, newest first: the whole project, or only what concerns one workspace, board or task.
	// Events keep their own copy of the names they mention, so they still read right after something was deleted.
	let {
		projectId,
		scope = {},
		workspaces = [],
		now,
		revision,
		compact = false,
		timeline = false,
		actions,
		tasks = [],
		ontask,
	}: {
		projectId: number
		scope?: HistoryScope
		/** the boards that exist now, so a line can link to its board */
		workspaces?: Workspace[]
		now: number
		/** changes when the project's tasks were reloaded, so the list refreshes itself */
		revision: number
		/** fewer lines and no filter, for a place where the list is a glance rather than the page */
		compact?: boolean
		/** a dot on a rail before each line and the icon in a box, for where the list is a feature of the page */
		timeline?: boolean
		/** buttons that sit beside the filter, e.g. the page's show-more toggle; with them the row shows even when compact */
		actions?: Snippet
		/** the tasks that exist now; a line about one of them offers to open it */
		tasks?: Task[]
		ontask?: (task: Task) => void
	} = $props()

	const PAGE = 30
	let events = $state<ProjectEvent[] | null>(null)
	let more = $state(false)
	let loadingMore = $state(false)
	let error = $state('')
	let group = $state('all')

	const kinds = $derived(KIND_GROUPS.find((g) => g.id === group)?.kinds ?? [])
	const taskById = $derived(new Map(tasks.map((t) => [t.id, t])))
	const boards = $derived(new Map(workspaces.flatMap((w) => w.boards).map((b) => [b.id, b])))

	$effect(() => {
		revision // reload when tasks change, so a change made a moment ago is listed
		const query = historyQuery(scope, kinds, null, compact ? 8 : PAGE)
		projectsApi
			.projectHistory(projectId, query)
			.then((e) => ((events = e), (more = !compact && e.length === PAGE), (error = '')))
			.catch((e) => (error = e instanceof Error ? e.message : 'Could not load the history'))
	})

	async function loadMore() {
		if (!events?.length) return
		loadingMore = true
		try {
			const next = await projectsApi.projectHistory(projectId, historyQuery(scope, kinds, events[events.length - 1].id, PAGE))
			events = [...events, ...next]
			more = next.length === PAGE
		} catch (e) {
			error = e instanceof Error ? e.message : 'Could not load more'
		} finally {
			loadingMore = false
		}
	}

	// The newest line is at the top, so its dot glows most and the glow dies away down the list.
	function dotGlow(index: number, count: number) {
		const g = count > 1 ? 1 - index / (count - 1) : 1
		const blur = Math.round(3 + 11 * g)
		const spread = (2.5 * g).toFixed(1)
		const strength = Math.round(15 + 70 * g)
		return `box-shadow: 0 0 ${blur}px ${spread}px color-mix(in oklab, var(--glow) ${strength}%, transparent)`
	}

	const icons: Record<string, typeof HistoryIcon> = {
		task_created: ListPlusIcon,
		task_status: ArrowRightIcon,
		task_moved: ArrowRightIcon,
		task_spawned: GitBranchPlusIcon,
		task_deleted: Trash2Icon,
		automation_stopped: CircleAlertIcon,
		halted: OctagonXIcon,
		resumed: PlayIcon,
		workspace_created: PlusIcon,
		board_created: PlusIcon,
		status_added: PlusIcon,
		workspace_renamed: PencilIcon,
		board_renamed: PencilIcon,
		status_renamed: PencilIcon,
		workspace_deleted: Trash2Icon,
		board_deleted: Trash2Icon,
		status_removed: Trash2Icon,
	}
</script>

{#if error}
	<p class="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive" role="alert">{error}</p>
{:else if events === null}
	<p class="py-6 text-sm text-muted-foreground">Loading...</p>
{:else}
	{#if !compact || actions}
		<div class="mb-3 flex flex-wrap items-center gap-2">
			{#if !compact}
				<Select.Root type="single" bind:value={group}>
					<Select.Trigger class="w-52" aria-label="Which events to show">{KIND_GROUPS.find((g) => g.id === group)?.label}</Select.Trigger>
					<Select.Content>
						{#each KIND_GROUPS as g (g.id)}<Select.Item value={g.id} label={g.label}>{g.label}</Select.Item>{/each}
					</Select.Content>
				</Select.Root>
			{/if}
			{#if actions}{@render actions()}{/if}
		</div>
	{/if}
	{#if events.length === 0}
		<div class="rounded-xl border border-dashed px-4 py-12 text-center">
			<p class="text-sm font-medium">Nothing here yet</p>
			<p class="mt-1 text-xs text-muted-foreground">Things done here, such as creating, moving or deleting tasks and boards, are listed.</p>
		</div>
	{:else}
		<ul class={cn('grid gap-1', timeline ? 'relative before:absolute before:inset-y-3 before:left-[4.5px] before:w-px before:bg-border' : 'max-w-3xl')}>
			{#each events as e, i (e.id)}
				{@const Icon = icons[e.kind] ?? (e.kind.startsWith('workspace') ? LayersIcon : HistoryIcon)}
				{@const board = e.board_id === null ? undefined : boards.get(e.board_id)}
				<!-- the whole line goes to its board, unless the board is gone or it is the one this list is already on -->
				{@const linked = board !== undefined && !e.kind.endsWith('deleted') && scope.boardId !== board.id}
				<li class={cn(timeline && 'flex items-center gap-3')}>
				{#if timeline}<span class="relative size-2.5 shrink-0 rounded-full bg-(--glow)" style={dotGlow(i, events.length)}></span>{/if}
				<div
					class={cn(
						'relative flex min-w-0 flex-1 items-center gap-3 rounded-lg border bg-card/40 px-3 py-2 text-sm transition-colors',
						linked && 'hover:border-primary/40 hover:bg-accent/50 focus-within:border-primary/40 focus-within:bg-accent/50'
					)}
				>
					<!-- stretched over the whole line, so the line is the link; the button below sits above it -->
					{#if linked}
						<a href="/projects/{projectId}/boards/{board.id}" class="absolute inset-0 rounded-lg focus-visible:outline-none" title={describeEvent(e)} aria-label="Open board {board.name}"></a>
					{/if}
					{#if timeline}
						<span class="flex size-8 shrink-0 items-center justify-center rounded-md border bg-background/50"><Icon class="size-4 text-muted-foreground" /></span>
					{:else}
						<Icon class="size-4 shrink-0 text-muted-foreground" />
					{/if}
					<span class="min-w-0 flex-1 truncate" title={describeEvent(e)}>{describeEvent(e)}</span>
					{#if !compact}
						{#if ontask && e.task_id !== null && taskById.has(e.task_id)}
							<button type="button" class="relative z-10 shrink-0 text-xs text-primary hover:underline" onclick={() => ontask(taskById.get(e.task_id!)!)}>Open task</button>
						{/if}
					{/if}
					<span class="shrink-0 text-xs text-muted-foreground" title={dateTime(e.created_at)}>{e.actor ? `${e.actor} · ` : ''}{relative(e.created_at, now)}</span>
				</div>
				</li>
			{/each}
		</ul>
		{#if more}
			<Button class="mt-3" variant="outline" size="sm" disabled={loadingMore} onclick={loadMore}>Load more</Button>
		{/if}
	{/if}
{/if}
