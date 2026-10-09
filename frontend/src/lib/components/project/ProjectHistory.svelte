<script lang="ts">
	import { api, type ProjectEvent } from '$lib/api'
	import { statusLabel } from '$lib/boards'
	import { dateTime, relative } from '$lib/format'
	import ArrowRightIcon from '@lucide/svelte/icons/arrow-right'
	import GitBranchPlusIcon from '@lucide/svelte/icons/git-branch-plus'
	import HistoryIcon from '@lucide/svelte/icons/history'
	import Trash2Icon from '@lucide/svelte/icons/trash-2'

	let { projectId, now, revision }: { projectId: number; now: number; revision: number } = $props()

	let events = $state<ProjectEvent[] | null>(null)
	let error = $state('')

	$effect(() => {
		revision // reload when tasks change, so a task deleted a moment ago is listed
		api
			.projectHistory(projectId)
			.then((e) => ((events = e), (error = '')))
			.catch((e) => (error = e instanceof Error ? e.message : 'Could not load the history'))
	})

	/** the board name stored in a part of an event ({board_id, board, status}), or "" */
	const boardName = (part: unknown) => (part && typeof part === 'object' && 'board' in part ? String((part as { board: unknown }).board) : '')
	const icons = { task_deleted: Trash2Icon, task_moved: ArrowRightIcon, task_spawned: GitBranchPlusIcon } as Record<string, typeof Trash2Icon>

	/** a line of text for the event; unknown kinds (from a newer version) still show their title */
	function describe(e: ProjectEvent): string {
		if (e.kind === 'task_moved') return `Moved the task "${e.title}" from ${boardName(e.data.from)} to ${boardName(e.data.to)}`
		if (e.kind === 'task_spawned') {
			const origin = e.data.origin as { title?: string } | undefined
			return `Created the task "${e.title}" on ${boardName(e.data.to)} as a follow-up of "${origin?.title ?? 'another task'}"`
		}
		if (e.kind === 'task_deleted') {
			const was = typeof e.data.status === 'string' ? ` (was in ${statusLabel(e.data.status)})` : ''
			return `Deleted the task "${e.title}"${was}`
		}
		return e.title
	}
</script>

{#if error}
	<p class="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive" role="alert">{error}</p>
{:else if events === null}
	<p class="py-6 text-sm text-muted-foreground">Loading...</p>
{:else if events.length === 0}
	<div class="rounded-xl border border-dashed px-4 py-12 text-center">
		<p class="text-sm font-medium">Nothing here yet</p>
		<p class="mt-1 text-xs text-muted-foreground">Things done to this project, such as deleting or moving a task, are listed here.</p>
	</div>
{:else}
	<ul class="grid max-w-3xl gap-1">
		{#each events as e (e.id)}
			{@const Icon = icons[e.kind] ?? HistoryIcon}
			<li class="flex items-center gap-3 rounded-lg border bg-card/40 px-3 py-2 text-sm">
				<Icon class="size-4 shrink-0 text-muted-foreground" />
				<span class="min-w-0 flex-1 truncate" title={e.title}>{describe(e)}</span>
				<span class="shrink-0 text-xs text-muted-foreground" title={dateTime(e.created_at)}>{e.actor ? `${e.actor} · ` : ''}{relative(e.created_at, now)}</span>
			</li>
		{/each}
	</ul>
{/if}
