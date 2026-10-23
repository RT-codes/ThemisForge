<script lang="ts">
	import { ApiError } from '$lib/api/core'
	import { workflowsApi, type Approval } from '$lib/api/workflows'
	import { approvalHref, headline } from '$lib/approvals'
	import { approvals } from '$lib/approvals.svelte'
	import ResultView from '$lib/components/ResultView.svelte'
	import { Button } from '$lib/components/ui/button/index.js'
	import * as Sheet from '$lib/components/ui/sheet/index.js'
	import { Textarea } from '$lib/components/ui/textarea/index.js'
	import { relative } from '$lib/format'
	import { cn } from '$lib/utils'
	import ChevronDownIcon from '@lucide/svelte/icons/chevron-down'
	import CircleCheckIcon from '@lucide/svelte/icons/circle-check'
	import ExternalLinkIcon from '@lucide/svelte/icons/external-link'
	import ShieldCheckIcon from '@lucide/svelte/icons/shield-check'
	import { tick } from 'svelte'

	// Every run that is parked at an Approval node, for the signed-in person. Opened from the header button, or from the
	// toast that announces a new one (which opens it on that approval). One approval is unfolded at a time.
	const NONE = 0 // folded by the person: not the same as never having chosen
	let unfolded = $state<number | null>(null)
	let notes = $state<Record<number, string>>({})
	let busy = $state<number | null>(null)
	let errors = $state<Record<number, string>>({})
	let now = $state(Date.now())

	// the one asked for, else the one waiting longest; the person's own folding wins once they touch it
	const shown = $derived(unfolded === NONE || (unfolded !== null && approvals.list.some((a) => a.id === unfolded)) ? unfolded : (approvals.list[0]?.id ?? null))

	$effect(() => {
		if (!approvals.open) return
		now = Date.now()
		const asked = approvals.focus
		if (asked !== null) {
			unfolded = asked
			approvals.focus = null
			tick().then(() => document.getElementById(`approval-${asked}`)?.scrollIntoView({ block: 'nearest', behavior: 'smooth' }))
		}
		const timer = setInterval(() => (now = Date.now()), 30_000)
		return () => clearInterval(timer)
	})

	async function decide(a: Approval, approved: boolean) {
		busy = a.id
		errors[a.id] = ''
		try {
			await workflowsApi.decideApproval(a.id, approved, notes[a.id] ?? '')
			delete notes[a.id]
		} catch (e) {
			errors[a.id] = e instanceof ApiError || e instanceof Error ? e.message : 'Could not send the answer'
		} finally {
			busy = null
			await approvals.refresh() // answered (by this or another window), or gone: the list says which
		}
	}
</script>

<Sheet.Root bind:open={approvals.open}>
	<Sheet.Content side="right" class="w-full gap-0 sm:max-w-lg">
		<Sheet.Header class="border-b">
			<Sheet.Title class="flex items-center gap-2">
				<ShieldCheckIcon class="size-4 text-tone-amber" /> Approvals
				{#if approvals.list.length}
					<span class="rounded-full bg-tone-amber/15 px-2 py-0.5 text-xs font-medium text-tone-amber tabular-nums">{approvals.list.length}</span>
				{/if}
			</Sheet.Title>
			<Sheet.Description>Runs wait here until you approve or reject them. Nothing goes on past an approval without your answer.</Sheet.Description>
		</Sheet.Header>
		<div class="slim-scrollbar min-h-0 flex-1 space-y-2 overflow-y-auto p-4">
			{#if approvals.list.length === 0}
				<p class="flex items-center gap-2 text-sm text-muted-foreground"><CircleCheckIcon class="size-4 shrink-0 text-tone-green" /> Nothing is waiting for approval.</p>
			{/if}
			{#each approvals.list as a (a.id)}
				{@const open = shown === a.id}
				<section id="approval-{a.id}" class={cn('rounded-lg border bg-card', open && 'border-tone-amber/40')}>
					<button
						type="button"
						class="flex w-full items-center gap-3 p-3 text-start"
						aria-expanded={open}
						aria-controls="approval-body-{a.id}"
						onclick={() => (unfolded = open ? NONE : a.id)}
					>
						<span class="min-w-0 flex-1">
							<span class="block truncate text-sm font-medium">{headline(a)}</span>
							<span class="block truncate text-xs text-muted-foreground">{a.project_name} · {a.workflow_name} · asked {relative(a.waiting_since, now)}</span>
						</span>
						<ChevronDownIcon class={cn('size-4 shrink-0 text-muted-foreground transition-transform', open && 'rotate-180')} />
					</button>
					{#if open}
						<div id="approval-body-{a.id}" class="space-y-3 border-t p-3">
							{#if a.prompt.trim().includes('\n')}
								<p class="text-sm whitespace-pre-wrap">{a.prompt.trim()}</p>
							{/if}
							<div>
								<p class="mb-1.5 text-xs font-medium tracking-wide text-muted-foreground uppercase">From "{a.previous_label || 'the step before'}"</p>
								{#if a.previous.trim()}
									<ResultView text={a.previous} />
								{:else}
									<p class="text-sm text-muted-foreground">The step before it produced no result to look at.</p>
								{/if}
							</div>
							<label class="block text-sm">
								<span class="mb-1 block text-xs font-medium tracking-wide text-muted-foreground uppercase">Note (optional)</span>
								<Textarea rows={2} placeholder="Kept with the run. When you reject, it is the reason." bind:value={notes[a.id]} />
							</label>
							{#if errors[a.id]}<p class="text-sm text-destructive" role="alert">{errors[a.id]}</p>{/if}
							<div class="flex flex-wrap items-center gap-2">
								<Button size="sm" disabled={busy === a.id} onclick={() => decide(a, true)}>Approve</Button>
								<Button size="sm" variant="outline" class="text-destructive hover:text-destructive" disabled={busy === a.id} onclick={() => decide(a, false)}>Reject</Button>
								<a href={approvalHref(a)} class="ms-auto inline-flex items-center gap-1 text-xs text-muted-foreground underline-offset-2 hover:text-foreground hover:underline" onclick={() => (approvals.open = false)}>
									Open the run <ExternalLinkIcon class="size-3" />
								</a>
							</div>
						</div>
					{/if}
				</section>
			{/each}
		</div>
	</Sheet.Content>
</Sheet.Root>
