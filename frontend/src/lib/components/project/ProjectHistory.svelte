<script lang="ts">
	import { api, type ProjectEvent } from '$lib/api'
	import { statusLabel } from '$lib/boards'
	import { dateTime, relative } from '$lib/format'
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

	/** a line of text for the event; unknown kinds (from a newer version) still show their title */
	function describe(e: ProjectEvent): string {
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
		<p class="mt-1 text-xs text-muted-foreground">Things done to this project, such as deleting a task, are listed here.</p>
	</div>
{:else}
	<ul class="grid max-w-3xl gap-1">
		{#each events as e (e.id)}
			<li class="flex items-center gap-3 rounded-lg border bg-card/40 px-3 py-2 text-sm">
				<Trash2Icon class="size-4 shrink-0 text-muted-foreground" />
				<span class="min-w-0 flex-1 truncate" title={e.title}>{describe(e)}</span>
				<span class="shrink-0 text-xs text-muted-foreground" title={dateTime(e.created_at)}>{e.actor ? `${e.actor} · ` : ''}{relative(e.created_at, now)}</span>
			</li>
		{/each}
	</ul>
{/if}
