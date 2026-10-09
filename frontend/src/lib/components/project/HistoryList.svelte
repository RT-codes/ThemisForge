<script lang="ts">
	import { api, type ProjectEvent, type Task, type Workspace } from '$lib/api'
	import { Button } from '$lib/components/ui/button/index.js'
	import * as Select from '$lib/components/ui/select/index.js'
	import { dateTime, relative } from '$lib/format'
	import { KIND_GROUPS, describeEvent, historyQuery, type HistoryScope } from '$lib/history'
	import ArrowRightIcon from '@lucide/svelte/icons/arrow-right'
	import GitBranchPlusIcon from '@lucide/svelte/icons/git-branch-plus'
	import HistoryIcon from '@lucide/svelte/icons/history'
	import LayersIcon from '@lucide/svelte/icons/layers'
	import ListPlusIcon from '@lucide/svelte/icons/list-plus'
	import PencilIcon from '@lucide/svelte/icons/pencil'
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
		api
			.projectHistory(projectId, query)
			.then((e) => ((events = e), (more = !compact && e.length === PAGE), (error = '')))
			.catch((e) => (error = e instanceof Error ? e.message : 'Could not load the history'))
	})

	async function loadMore() {
		if (!events?.length) return
		loadingMore = true
		try {
			const next = await api.projectHistory(projectId, historyQuery(scope, kinds, events[events.length - 1].id, PAGE))
			events = [...events, ...next]
			more = next.length === PAGE
		} catch (e) {
			error = e instanceof Error ? e.message : 'Could not load more'
		} finally {
			loadingMore = false
		}
	}

	const icons: Record<string, typeof HistoryIcon> = {
		task_created: ListPlusIcon,
		task_status: ArrowRightIcon,
		task_moved: ArrowRightIcon,
		task_spawned: GitBranchPlusIcon,
		task_deleted: Trash2Icon,
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
	{#if !compact}
		<div class="mb-3 flex items-center gap-2">
			<Select.Root type="single" bind:value={group}>
				<Select.Trigger class="w-52" aria-label="Which events to show">{KIND_GROUPS.find((g) => g.id === group)?.label}</Select.Trigger>
				<Select.Content>
					{#each KIND_GROUPS as g (g.id)}<Select.Item value={g.id} label={g.label}>{g.label}</Select.Item>{/each}
				</Select.Content>
			</Select.Root>
		</div>
	{/if}
	{#if events.length === 0}
		<div class="rounded-xl border border-dashed px-4 py-12 text-center">
			<p class="text-sm font-medium">Nothing here yet</p>
			<p class="mt-1 text-xs text-muted-foreground">Things done here, such as creating, moving or deleting tasks and boards, are listed.</p>
		</div>
	{:else}
		<ul class="grid max-w-3xl gap-1">
			{#each events as e (e.id)}
				{@const Icon = icons[e.kind] ?? (e.kind.startsWith('workspace') ? LayersIcon : HistoryIcon)}
				{@const board = e.board_id === null ? undefined : boards.get(e.board_id)}
				<li class="flex items-center gap-3 rounded-lg border bg-card/40 px-3 py-2 text-sm">
					<Icon class="size-4 shrink-0 text-muted-foreground" />
					<span class="min-w-0 flex-1 truncate" title={describeEvent(e)}>{describeEvent(e)}</span>
					{#if !compact}
						{#if ontask && e.task_id !== null && taskById.has(e.task_id)}
							<button type="button" class="shrink-0 text-xs text-primary hover:underline" onclick={() => ontask(taskById.get(e.task_id!)!)}>Open task</button>
						{/if}
						{#if board && !e.kind.endsWith('deleted')}
							<a href="/projects/{projectId}/boards/{board.id}" class="shrink-0 text-xs text-primary hover:underline">Open board</a>
						{/if}
					{/if}
					<span class="shrink-0 text-xs text-muted-foreground" title={dateTime(e.created_at)}>{e.actor ? `${e.actor} · ` : ''}{relative(e.created_at, now)}</span>
				</li>
			{/each}
		</ul>
		{#if more}
			<Button class="mt-3" variant="outline" size="sm" disabled={loadingMore} onclick={loadMore}>Load more</Button>
		{/if}
	{/if}
{/if}
