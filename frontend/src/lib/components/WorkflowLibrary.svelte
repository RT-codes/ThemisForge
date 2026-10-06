<script lang="ts">
	import { api, ApiError, type RunStatus, type WorkflowSummary } from '$lib/api'
	import * as AlertDialog from '$lib/components/ui/alert-dialog/index.js'
	import { Button } from '$lib/components/ui/button/index.js'
	import { relative } from '$lib/format'
	import { router } from '$lib/router.svelte'
	import { cn } from '$lib/utils'
	import PlusIcon from '@lucide/svelte/icons/plus'
	import Trash2Icon from '@lucide/svelte/icons/trash-2'
	import WorkflowIcon from '@lucide/svelte/icons/workflow'
	import { onMount, tick } from 'svelte'
	import { slide } from 'svelte/transition'

	let { projectId, now }: { projectId: number; now: number } = $props()

	let flows = $state<WorkflowSummary[]>([])
	let loaded = $state(false)
	let error = $state('')
	let doomed = $state<WorkflowSummary | null>(null)
	let confirmOpen = $state(false)
	let section = $state<HTMLElement>()

	const runLabel: Record<RunStatus, string> = { running: 'Running', succeeded: 'Succeeded', failed: 'Failed', cancelled: 'Cancelled' }
	const runTone: Record<RunStatus, string> = {
		running: 'bg-primary/15 text-primary',
		succeeded: 'bg-emerald-500/15 text-emerald-400',
		failed: 'bg-destructive/15 text-destructive',
		cancelled: 'bg-muted text-muted-foreground',
	}

	async function load() {
		try {
			flows = await api.workflows(projectId)
			error = ''
		} catch (e) {
			error = e instanceof Error ? e.message : 'Could not load the workflows'
		} finally {
			loaded = true
		}
	}

	onMount(() => {
		load().then(async () => {
			await tick()
			if (router.hash === 'workflows') section?.scrollIntoView({ behavior: 'smooth' }) // arrived from the sidebar
		})
		const timer = setInterval(() => !document.hidden && load(), 10_000)
		return () => clearInterval(timer)
	})

	// a new workflow opens in the editor right away, and is only saved once something in it changes
	const create = () => router.navigate(`/projects/${projectId}/workflows/new`)

	async function remove() {
		const target = doomed
		confirmOpen = false // close at once: the dialog must never sit there while (or after) the delete happens
		if (!target) return
		try {
			await api.deleteWorkflow(target.id)
			await load()
		} catch (e) {
			error = e instanceof ApiError || e instanceof Error ? e.message : 'Could not delete the workflow'
		}
	}
</script>

<section bind:this={section} id="workflows" class="mt-6 scroll-mt-6 rounded-xl border bg-card">
	<div class="flex items-center gap-3 p-5 pb-3">
		<div class="min-w-0 flex-1">
			<h3 class="text-sm font-medium">Workflows</h3>
			<p class="text-xs text-muted-foreground">Flows of tasks, agents and checks. A task can play one, and a workflow can run tasks.</p>
		</div>
		<Button size="sm" onclick={create}><PlusIcon /> New workflow</Button>
	</div>

	{#if error}<p class="px-5 pb-3 text-sm text-destructive" role="alert">{error}</p>{/if}

	{#if !loaded}
		<p class="px-5 pb-5 text-sm text-muted-foreground">Loading...</p>
	{:else if flows.length === 0}
		<div class="mx-5 mb-5 rounded-lg border border-dashed py-8 text-center">
			<p class="text-sm font-medium">No workflows yet</p>
			<p class="mt-1 text-xs text-muted-foreground">Create one to chain tasks and agents together.</p>
		</div>
	{:else}
		<ul class="divide-y border-t">
			{#each flows as w (w.id)}
				<li class="group flex items-center gap-3 px-5 py-3 transition-colors hover:bg-accent/40" transition:slide={{ duration: 200 }}>
					<a href="/projects/{projectId}/workflows/{w.id}" class="flex min-w-0 flex-1 items-center gap-3">
						<span class="flex size-8 shrink-0 items-center justify-center rounded-md bg-primary/15 text-primary"><WorkflowIcon class="size-4" /></span>
						<span class="min-w-0 flex-1">
							<span class="block truncate text-sm font-medium">{w.name}</span>
							<span class="block truncate text-xs text-muted-foreground">
								{w.node_count} {w.node_count === 1 ? 'node' : 'nodes'} · edited {relative(w.updated_at, now)}{w.description ? ` · ${w.description}` : ''}
							</span>
						</span>
					</a>
					{#if w.last_run}
						<a
							href="/projects/{projectId}/workflows/{w.id}/runs/{w.last_run.id}"
							title="Open the last run"
							class={cn('shrink-0 rounded-full px-2.5 py-0.5 text-xs font-medium transition-opacity hover:opacity-80', runTone[w.last_run.status])}
						>
							{runLabel[w.last_run.status]} · {relative(w.last_run.started_at, now)}
						</a>
					{:else}
						<span class="shrink-0 text-xs text-muted-foreground">Never run</span>
					{/if}
					<Button
						variant="ghost"
						size="icon-sm"
						aria-label={`Delete ${w.name}`}
						class="shrink-0 opacity-0 transition-opacity group-hover:opacity-100 focus-visible:opacity-100"
						onclick={() => ((doomed = w), (confirmOpen = true))}
					>
						<Trash2Icon />
					</Button>
				</li>
			{/each}
		</ul>
	{/if}
</section>

<AlertDialog.Root bind:open={confirmOpen}>
	<AlertDialog.Content>
		<AlertDialog.Header>
			<AlertDialog.Title>Delete this workflow?</AlertDialog.Title>
			<AlertDialog.Description>
				"{doomed?.name}" and its run history will be removed permanently. Tasks that play it stay, but will have nothing to play.
			</AlertDialog.Description>
		</AlertDialog.Header>
		<AlertDialog.Footer>
			<AlertDialog.Cancel>Keep it</AlertDialog.Cancel>
			<AlertDialog.Action onclick={remove}>Delete</AlertDialog.Action>
		</AlertDialog.Footer>
	</AlertDialog.Content>
</AlertDialog.Root>
