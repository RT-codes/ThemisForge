<script lang="ts">
	import { api, type RunStatus, type WorkflowSummary } from '$lib/api'
	import { Button } from '$lib/components/ui/button/index.js'
	import * as Dialog from '$lib/components/ui/dialog/index.js'
	import { Input } from '$lib/components/ui/input/index.js'
	import { relative } from '$lib/format'
	import { cn } from '$lib/utils'
	import PlusIcon from '@lucide/svelte/icons/plus'
	import SearchIcon from '@lucide/svelte/icons/search'
	import WorkflowIcon from '@lucide/svelte/icons/workflow'
	import { fly } from 'svelte/transition'

	let {
		open = $bindable(false),
		projectId,
		currentId,
		onpick,
		onnew,
	}: { open?: boolean; projectId: number; currentId: number | null; onpick: (id: number) => void; onnew: () => void } = $props()

	let flows = $state<WorkflowSummary[]>([])
	let loaded = $state(false)
	let error = $state('')
	let query = $state('')
	const now = $derived(open ? Date.now() : 0)

	const runTone: Record<RunStatus, string> = {
		running: 'bg-primary/15 text-primary',
		succeeded: 'bg-emerald-500/15 text-emerald-400',
		failed: 'bg-destructive/15 text-destructive',
		cancelled: 'bg-muted text-muted-foreground',
	}
	const runLabel: Record<RunStatus, string> = { running: 'Running', succeeded: 'Succeeded', failed: 'Failed', cancelled: 'Cancelled' }

	// the list is fetched every time the dialog opens, so it is never stale
	$effect(() => {
		if (!open) return
		query = ''
		loaded = false
		api.workflows(projectId)
			.then((list) => {
				flows = [...list].sort((a, b) => b.updated_at.localeCompare(a.updated_at))
				error = ''
			})
			.catch((e) => (error = e instanceof Error ? e.message : 'Could not load the workflows'))
			.finally(() => (loaded = true))
	})

	const shown = $derived(flows.filter((w) => `${w.name} ${w.description}`.toLowerCase().includes(query.trim().toLowerCase())))

	function pick(id: number) {
		open = false
		if (id !== currentId) onpick(id)
	}
</script>

<Dialog.Root bind:open>
	<Dialog.Content class="gap-4 sm:max-w-lg">
		<Dialog.Header>
			<Dialog.Title>Load a workflow</Dialog.Title>
			<Dialog.Description>
				{#if loaded && flows.length}This project has {flows.length} {flows.length === 1 ? 'workflow' : 'workflows'}. Pick one to open it.{:else}Pick one of this project's workflows to open it.{/if}
			</Dialog.Description>
		</Dialog.Header>

		{#if flows.length > 5}
			<div class="relative">
				<SearchIcon class="pointer-events-none absolute start-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
				<Input bind:value={query} placeholder="Search workflows" class="ps-8" aria-label="Search workflows" />
			</div>
		{/if}

		<div class="-mx-2 max-h-[50vh] min-h-24 overflow-y-auto px-2">
			{#if error}
				<p class="py-6 text-center text-sm text-destructive" role="alert">{error}</p>
			{:else if !loaded}
				<p class="py-6 text-center text-sm text-muted-foreground">Loading...</p>
			{:else if flows.length === 0}
				<div class="rounded-lg border border-dashed py-8 text-center">
					<p class="text-sm font-medium">No saved workflows yet</p>
					<p class="mt-1 text-xs text-muted-foreground">A workflow is saved as soon as you change something in it.</p>
				</div>
			{:else if shown.length === 0}
				<p class="py-6 text-center text-sm text-muted-foreground">Nothing matches "{query}".</p>
			{:else}
				<ul class="grid gap-1">
					{#each shown as w, i (w.id)}
						<li in:fly={{ y: 6, duration: 180, delay: Math.min(i, 8) * 25 }}>
							<button
								type="button"
								onclick={() => pick(w.id)}
								class={cn(
									'flex w-full items-center gap-3 rounded-lg border border-transparent px-3 py-2.5 text-start transition-colors hover:border-border hover:bg-accent focus-visible:border-ring focus-visible:outline-none',
									w.id === currentId && 'bg-accent/50'
								)}
							>
								<span class="flex size-8 shrink-0 items-center justify-center rounded-md bg-primary/15 text-primary"><WorkflowIcon class="size-4" /></span>
								<span class="min-w-0 flex-1">
									<span class="block truncate text-sm font-medium">{w.name}</span>
									<span class="block truncate text-xs text-muted-foreground">
										{w.node_count} {w.node_count === 1 ? 'node' : 'nodes'} · edited {relative(w.updated_at, now)}
									</span>
								</span>
								{#if w.id === currentId}
									<span class="shrink-0 rounded-full border px-2 py-0.5 text-[11px] text-muted-foreground">Open now</span>
								{:else if w.last_run}
									<span class={cn('shrink-0 rounded-full px-2 py-0.5 text-[11px] font-medium', runTone[w.last_run.status])}>{runLabel[w.last_run.status]}</span>
								{/if}
							</button>
						</li>
					{/each}
				</ul>
			{/if}
		</div>

		<div class="flex items-center justify-between gap-3 border-t pt-4">
			<p class="text-xs text-muted-foreground">Your current workflow is saved before you switch.</p>
			<Button
				variant="outline"
				size="sm"
				onclick={() => {
					open = false
					onnew()
				}}><PlusIcon /> New workflow</Button
			>
		</div>
	</Dialog.Content>
</Dialog.Root>
