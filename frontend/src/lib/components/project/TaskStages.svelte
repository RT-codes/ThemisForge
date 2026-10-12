<script lang="ts">
	import { api, type TaskStage, type WorkflowRunDetail } from '$lib/api'
	import { duration } from '$lib/format'
	import { onCodeCopyClick, renderMarkdown } from '$lib/markdown'
	import { STAGE_LABEL, STAGE_TONE } from '$lib/stageTrack'
	import { agentSteps } from '$lib/workflow'
	import LogPanel from '$lib/components/LogPanel.svelte'
	import { cn } from '$lib/utils'
	import ChevronRightIcon from '@lucide/svelte/icons/chevron-right'
	import RunTrack from './RunTrack.svelte'
	import StageIcon from './StageIcon.svelte'

	// The workflows a task plays, in order, each with where it is. A stage that has started unfolds into its track.
	let {
		stages,
		projectId,
		onopenworkflow,
	}: {
		stages: TaskStage[]
		projectId: number
		/** leaves for the editor of a workflow at one of its nodes (the panel asks about unsaved changes first) */
		onopenworkflow?: (workflowId: number, nodeId?: string) => void
	} = $props()

	// What the agents of a stage are told (their instructions, as the workflow has them now), loaded when first asked for.
	// This is where a run is steered from, so it is one click away from the ticket instead of inside the editor.
	let stepsOpen = $state<Record<number, boolean>>({})
	let steps = $state<Record<number, ReturnType<typeof agentSteps> | 'loading' | 'error'>>({})
	async function toggleSteps(i: number) {
		stepsOpen[i] = !stepsOpen[i]
		const id = stages[i].workflow_id
		if (!stepsOpen[i] || (steps[id] && steps[id] !== 'error')) return
		steps[id] = 'loading'
		try {
			const [workflow, agents] = await Promise.all([api.workflow(id), api.agents(projectId)])
			steps[id] = agentSteps(workflow.graph, agents)
		} catch {
			steps[id] = 'error'
		}
	}
	/** a plain click goes through the panel (it asks about unsaved changes first); ctrl or cmd opens a tab */
	function edit(e: MouseEvent, workflowId: number, nodeId: string) {
		if (!onopenworkflow || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return
		e.preventDefault()
		onopenworkflow(workflowId, nodeId)
	}

	// what the person chose to open or close; a stage nobody touched is open while it is running
	let chosen = $state<Record<number, boolean>>({})
	// the run each open stage is showing, for its duration (RunTrack fetches and refreshes it)
	let details = $state<Record<number, WorkflowRunDetail | null>>({})

	const isOpen = (i: number) => chosen[i] ?? stages[i].status === 'running'

	// what the steps of a stage reported (a summary, a pull request link), so the output is here and not only in the run
	let openOutputs = $state<Record<number, boolean>>({})
	const outputsOf = (run: WorkflowRunDetail | null | undefined) =>
		(run?.nodes ?? []).filter((n) => (n.kind === 'agent' || n.kind === 'task') && (n.result.trim() || n.error))
	// the step that is working now: its log is shown live, so what the agent thinks and runs is on the ticket
	const workingOf = (run: WorkflowRunDetail | null | undefined) =>
		(run?.nodes ?? []).filter((n) => (n.kind === 'agent' || n.kind === 'task') && n.status === 'running')
	// agent text is not ours: rendered as untrusted markdown, which cannot produce markup or script of its own
	const html = (text: string) => renderMarkdown(text, { untrusted: true }).html
	// a loaded run is fresher than the task, which only changes when the board next refreshes
	const statusOf = (s: TaskStage) => (s.run_id && details[s.run_id]?.status) || s.status
</script>

<div class="grid grid-cols-[minmax(0,1fr)] gap-1 px-4 pb-4">
	<h4 class="text-xs font-medium tracking-wide text-muted-foreground uppercase">Stages</h4>
	<ol class="grid grid-cols-[minmax(0,1fr)] gap-1">
		{#each stages as s, i (i)}
			{@const status = statusOf(s)}
			{@const detail = s.run_id ? details[s.run_id] : null}
			<li class={cn('rounded-lg border bg-card text-sm', status === 'running' && 'border-primary/40')}>
				{#snippet head()}
					<StageIcon {status} class="size-4" />
					<span class={cn('min-w-0 flex-1 truncate', status === 'pending' && 'text-muted-foreground')}>{s.workflow_name}</span>
					<span class={cn('shrink-0 text-xs', STAGE_TONE[status])}>
						{STAGE_LABEL[status]}{detail?.finished_at ? ` · ${duration(detail.started_at, detail.finished_at)}` : ''}
					</span>
				{/snippet}
				<!-- a stage that has not started has nothing to unfold, so it is not a button -->
				{#if s.run_id}
					<button
						type="button"
						aria-expanded={isOpen(i)}
						class="flex w-full cursor-pointer items-center gap-2 px-3 py-2 text-start"
						onclick={() => (chosen[i] = !isOpen(i))}
					>
						{@render head()}
						<ChevronRightIcon class={cn('size-4 shrink-0 text-muted-foreground transition-transform', isOpen(i) && 'rotate-90')} />
					</button>
				{:else}
					<div class="flex w-full items-center gap-2 px-3 py-2">{@render head()}</div>
				{/if}

				{#if s.run_id}
					<!-- always mounted so the run is known (and its duration shown) while the stage is folded; hidden then -->
					<div class={cn('border-t px-3 py-2', !isOpen(i) && 'hidden')}>
						<RunTrack runId={s.run_id} bind:detail={details[s.run_id]} />
						{#each workingOf(detail) as n (n.id)}
							<div class="mt-2 border-t pt-2">
								<p class="mb-1 flex items-center gap-1.5 text-xs font-medium"><span class="size-1.5 animate-pulse rounded-full bg-primary"></span>{n.label} is working</p>
								<LogPanel text={n.log} empty="Waiting for the first output..." title={`${n.label} - log`} subtitle={`Step of ${s.workflow_name}, live`} class="h-56" />
							</div>
						{/each}
						{#if outputsOf(detail).length}
							<ul class="mt-2 grid gap-1.5 border-t pt-2" aria-label="What the steps reported">
								{#each outputsOf(detail) as n (n.id)}
									{@const failed = n.status === 'failed' || (!n.result.trim() && !!n.error)}
									<li class="text-xs">
										<button
											type="button"
											aria-expanded={!!openOutputs[n.id]}
											class="flex w-full cursor-pointer items-baseline gap-2 text-start"
											onclick={() => (openOutputs[n.id] = !openOutputs[n.id])}
										>
											<span class={cn('min-w-0 truncate font-medium', failed && 'text-destructive')}>{n.label}</span>
											{#if n.started_at && n.finished_at}<span class="shrink-0 text-muted-foreground">{duration(n.started_at, n.finished_at)}</span>{/if}
											<ChevronRightIcon class={cn('ms-auto size-3.5 shrink-0 self-center text-muted-foreground transition-transform', openOutputs[n.id] && 'rotate-90')} />
										</button>
										<!-- trusted: renderMarkdown ran in untrusted mode -->
										<!-- svelte-ignore a11y_click_events_have_key_events, a11y_no_static_element_interactions -->
										<div
											class={cn(
												'docs-prose prose prose-sm prose-invert slim-scrollbar mt-0.5 max-w-none text-xs break-words text-muted-foreground',
												openOutputs[n.id] ? 'max-h-72 overflow-auto' : 'line-clamp-2'
											)}
											onclick={onCodeCopyClick}
										>
											{@html html(n.result.trim() || n.error)}
										</div>
									</li>
								{/each}
							</ul>
						{/if}
						<a
							href="/projects/{projectId}/workflows/{s.workflow_id}/runs/{s.run_id}"
							class="mt-1 inline-block text-xs text-muted-foreground hover:text-primary hover:underline"
						>
							Run details
						</a>
					</div>
				{/if}

				<div class="border-t">
					<button
						type="button"
						aria-expanded={!!stepsOpen[i]}
						class="flex w-full cursor-pointer items-center gap-1.5 px-3 py-1.5 text-start text-xs text-muted-foreground transition-colors hover:text-foreground"
						onclick={() => toggleSteps(i)}
					>
						<ChevronRightIcon class={cn('size-3.5 shrink-0 transition-transform', stepsOpen[i] && 'rotate-90')} />
						Step instructions
					</button>
					{#if stepsOpen[i]}
						{@const found = steps[s.workflow_id]}
						<div class="px-3 pb-2.5">
							{#if found === undefined || found === 'loading'}
								<p class="text-xs text-muted-foreground">Loading...</p>
							{:else if found === 'error'}
								<p class="text-xs text-destructive">Could not load this workflow's steps.</p>
							{:else if found.length === 0}
								<p class="text-xs text-muted-foreground">This workflow has no agent steps.</p>
							{:else}
								<ul class="grid gap-2">
									{#each found as step (step.nodeId)}
										<li class="rounded-md border bg-background/40 p-2 text-xs">
											<div class="flex items-center gap-2">
												<span class="min-w-0 truncate font-medium">{step.label}</span>
												<span class="shrink-0 text-muted-foreground">{step.agent}</span>
												<a
													href="/projects/{projectId}/workflows/{s.workflow_id}#node={step.nodeId}"
													class="ms-auto shrink-0 text-primary hover:underline"
													onclick={(e) => edit(e, s.workflow_id, step.nodeId)}
												>
													Edit step
												</a>
											</div>
											<p class="slim-scrollbar mt-1 max-h-36 overflow-auto break-words whitespace-pre-wrap text-muted-foreground">{step.instructions || 'No instructions yet.'}</p>
										</li>
									{/each}
								</ul>
							{/if}
						</div>
					{/if}
				</div>
			</li>
		{/each}
	</ol>
</div>
