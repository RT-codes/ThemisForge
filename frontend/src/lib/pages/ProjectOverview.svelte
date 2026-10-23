<script lang="ts">
	import { agentsApi } from '$lib/api/agents'
	import { connectionsApi } from '$lib/api/connections'
	import { ApiError } from '$lib/api/core'
	import { projectsApi, type Project } from '$lib/api/projects'
	import { tasksApi, type ScheduledRun, type Task } from '$lib/api/tasks'
	import { toolsApi } from '$lib/api/tools'
	import { attentionTasks } from '$lib/attention'
	import { headline } from '$lib/approvals'
	import { approvals } from '$lib/approvals.svelte'
	import ShieldCheckIcon from '@lucide/svelte/icons/shield-check'
	import { destinationLabel, findBoard } from '$lib/boards'
	import HaltBanner from '$lib/components/project/HaltBanner.svelte'
	import HaltControl from '$lib/components/project/HaltControl.svelte'
	import HistoryList from '$lib/components/project/HistoryList.svelte'
	import SectionBanner from '$lib/components/SectionBanner.svelte'
	import WorkspaceDialog from '$lib/components/project/WorkspaceDialog.svelte'
	import WorkspaceCards from '$lib/components/WorkspaceCards.svelte'
	import GroupHeading from '$lib/components/GroupHeading.svelte'
	import IconTile, { wash } from '$lib/components/IconTile.svelte'
	import ProjectHero from '$lib/components/project/ProjectHero.svelte'
	import ArrowRightIcon from '@lucide/svelte/icons/arrow-right'
	import BotIcon from '@lucide/svelte/icons/bot'
	import CalendarClockIcon from '@lucide/svelte/icons/calendar-clock'
	import ChartNoAxesColumnIcon from '@lucide/svelte/icons/chart-no-axes-column'
	import CircleCheckIcon from '@lucide/svelte/icons/circle-check'
	import ClockIcon from '@lucide/svelte/icons/clock'
	import GaugeIcon from '@lucide/svelte/icons/gauge'
	import HistoryIcon from '@lucide/svelte/icons/history'
	import LayersIcon from '@lucide/svelte/icons/layers'
	import ListChecksIcon from '@lucide/svelte/icons/list-checks'
	import PlayIcon from '@lucide/svelte/icons/play'
	import PlusIcon from '@lucide/svelte/icons/plus'
	import TriangleAlertIcon from '@lucide/svelte/icons/triangle-alert'
	import { Button } from '$lib/components/ui/button/index.js'
	import { router } from '$lib/router.svelte'
	import { taskResultHref } from '$lib/routes'
	import { structure } from '$lib/structure.svelte'
	import { projects } from '$lib/projects.svelte'
	import { relative } from '$lib/format'
	import { countScheduled } from '$lib/schedule'
	import { setupIssues, type SetupIssue } from '$lib/setup'
	import SlidersHorizontalIcon from '@lucide/svelte/icons/sliders-horizontal'
	import { onMount } from 'svelte'
	import { fade } from 'svelte/transition'

	let { id }: { id: number } = $props()

	let project = $state<Project | null>(null)
	let runs = $state<ScheduledRun[]>([])
	let now = $state(Date.now())
	let loadError = $state('')
	let tasks = $state<Task[] | null>(null)
	let attentionError = $state('')
	let allAttention = $state(false)
	let workspaceOpen = $state(false)
	let issues = $state<SetupIssue[]>([])
	let agentCount = $state<number | null>(null)
	let revision = $state(0)
	let allActivity = $state(false)
	const workspaces = $derived(structure.get(id) ?? [])
	// runs of this project parked at an Approval node: a person's decision comes before any task's result
	const pendingApprovals = $derived(approvals.list.filter((a) => a.project_id === id))
	const attention = $derived(attentionTasks(tasks ?? [], allAttention ? tasks?.length : 5))

	async function loadAttention() {
		try {
			tasks = await tasksApi.tasks(id)
			attentionError = ''
		} catch (e) {
			attentionError = e instanceof ApiError ? e.message : 'Could not load tasks needing attention'
		}
	}

	async function load() {
		try {
			const [loaded, upcoming] = await Promise.all([projectsApi.project(id), tasksApi.schedule(id, 168), structure.refresh(id), loadAttention()])
			project = loaded
			runs = upcoming
			revision++
			loadError = ''
		} catch (e) {
			loadError = e instanceof ApiError ? e.message : 'Could not load the project'
		}
	}

	// What the project still needs before its agents can work: read from the same lists the settings page shows.
	// Slower than the rest of the page, because it is not what changes minute to minute.
	async function loadSetup() {
		try {
			const [agents, tools, bound, catalog] = await Promise.all([
				agentsApi.agents(id),
				toolsApi.mcpServers(id),
				connectionsApi.projectConnections(id),
				connectionsApi.connections(),
			])
			agentCount = agents.length
			issues = setupIssues({
				projectId: id,
				agents,
				tools,
				connected: bound.map((b) => b.provider),
				providerName: (p) => catalog.providers.find((x) => x.id === p)?.name ?? p,
			})
		} catch {
			// a hint, not the page: with no answer it shows nothing rather than something wrong
		}
	}

	onMount(() => {
		load()
		loadSetup()
		const timer = setInterval(() => {
			if (document.hidden) return
			now = Date.now()
			load()
		}, 10_000)
		const slow = setInterval(() => !document.hidden && loadSetup(), 60_000)
		return () => (clearInterval(timer), clearInterval(slow))
	})

	// the next run of each scheduled task, soonest first
	const upcoming = $derived.by(() => {
		const seen = new Set<number>()
		return [...runs]
			.sort((a, b) => a.at.localeCompare(b.at))
			.filter((r) => !seen.has(r.task_id) && seen.add(r.task_id))
	})

	// the sidebar store refreshes on its own, so the counts stay live without extra requests
	const counts = $derived(projects.get(id)?.task_counts ?? {})
	const scheduled = $derived(countScheduled(runs, now))
	// each count has its own colour and icon, so the row can be read at a glance before the numbers are
	const stats = $derived([
		{ label: 'Ready', hint: 'Tasks ready to run', value: counts.ready ?? 0, icon: CircleCheckIcon, tone: 'green' as const },
		{ label: 'Running', hint: 'Tasks in progress', value: counts.running ?? 0, icon: PlayIcon, tone: 'violet' as const },
		{ label: 'Scheduled today', hint: 'Runs due today', value: scheduled.today, icon: CalendarClockIcon, tone: 'amber' as const },
		{ label: 'Next 7 days', hint: 'Runs in the coming week', value: scheduled.week, icon: ChartNoAxesColumnIcon, tone: 'rose' as const },
	])
</script>

{#snippet heroActions()}
	<div class="flex flex-wrap items-center justify-end gap-2">
		<Button size="lg" onclick={() => (workspaceOpen = true)}><PlusIcon /> New workspace</Button>
		<Button variant="outline" size="lg" onclick={() => router.navigate(`/projects/${id}/settings`)}>
			<SlidersHorizontalIcon /> Settings
		</Button>
		<!-- last, apart from the creating actions: the one that stops things -->
		<HaltControl labelled scope="project" id={id} name={project!.name} haltedAt={project!.halted_at} running={counts.running ?? 0} onchange={load} />
	</div>
{/snippet}

{#snippet attentionToggle()}
	<Button variant="outline" size="sm" onclick={() => (allAttention = !allAttention)}>
		{allAttention ? 'Show less' : 'Show everything'} <ArrowRightIcon />
	</Button>
{/snippet}

{#snippet activityToggle()}
	<Button variant="outline" size="sm" onclick={() => (allActivity = !allActivity)}>
		{allActivity ? 'Show less' : 'Show all activity'} <ArrowRightIcon />
	</Button>
{/snippet}

{#if project}
	<div class="px-6 pt-6 pb-8" in:fade={{ duration: 350 }}>
		<ProjectHero {project} title={project.name} lead={project.purpose} detail={project.description} actions={heroActions}>
			{#if project.halted_at}<div class="mb-3"><HaltBanner scope="project" name={project.name} /></div>{/if}
			<div class="flex flex-wrap gap-2 text-xs">
				<span class="inline-flex items-center gap-1.5 rounded-full border bg-background/50 px-3 py-1">
					<LayersIcon class="size-3.5 text-muted-foreground" />{workspaces.length} {workspaces.length === 1 ? 'workspace' : 'workspaces'}
				</span>
				{#if agentCount !== null}
					<a href="/projects/{id}/agents" class="inline-flex items-center gap-1.5 rounded-full border bg-background/50 px-3 py-1 transition-colors hover:bg-accent/50">
						<BotIcon class="size-3.5 text-muted-foreground" />{agentCount} {agentCount === 1 ? 'agent' : 'agents'}
					</a>
				{/if}
			</div>
		</ProjectHero>

		{#if issues.length}
			<section class="mt-4 rounded-xl border border-tone-yellow/30 bg-tone-yellow/5 p-4" aria-labelledby="setup-title">
				<h3 id="setup-title" class="text-sm font-semibold tracking-tight">Needs setup ({issues.length})</h3>
				<ul class="mt-2 grid gap-0.5">
					{#each issues as issue (issue.id)}
						<li>
							<a href={issue.href} class="flex items-center justify-between gap-4 rounded-md px-2 py-1.5 text-sm transition-colors hover:bg-accent/50">
								<span class="min-w-0 truncate">{issue.text}</span>
								<span class="shrink-0 text-xs text-primary">Fix</span>
							</a>
						</li>
					{/each}
				</ul>
			</section>
		{/if}

		<section class="mt-8">
		<GroupHeading icon={GaugeIcon}>Status</GroupHeading>
		<div class="mt-3 grid gap-4">
		<div class="@container overflow-hidden glow-card rounded-xl border bg-card">
			<SectionBanner icon={ListChecksIcon} tone="amber">
				<h3 class="text-base font-semibold tracking-tight">Tasks</h3>
				<p class="text-xs text-muted-foreground">A quick pulse on work in this project</p>
			</SectionBanner>
			<!-- gap-px over the border colour draws the dividers, whatever the number of columns -->
			<div class="grid grid-cols-2 gap-px bg-border @3xl:grid-cols-4">
				{#each stats as s (s.label)}
					<div class={['flex items-center gap-3 bg-card p-5', wash(s.tone)]}>
						<IconTile tone={s.tone}><s.icon /></IconTile>
						<div class="text-3xl leading-none font-semibold tabular-nums">{s.value}</div>
						<div class="min-w-0">
							<div class="truncate text-sm font-medium">{s.label}</div>
							<div class="truncate text-xs text-muted-foreground">{s.hint}</div>
						</div>
					</div>
				{/each}
			</div>
		</div>

		<div class="grid grid-cols-1 gap-4 lg:grid-cols-12">
			<section class="overflow-hidden glow-card rounded-xl border bg-card lg:col-span-7" aria-labelledby="attention-title">
				<SectionBanner icon={TriangleAlertIcon} tone="amber" actions={!attentionError && attention.total > 5 ? attentionToggle : undefined}>
					<h3 id="attention-title" class="flex items-center gap-2 text-base font-semibold tracking-tight">
						Needs attention
						{#if !attentionError && tasks !== null}
							<span class="rounded-full bg-tone-amber/15 px-2 py-0.5 text-xs font-medium text-tone-amber tabular-nums">{attention.total + pendingApprovals.length}</span>
						{/if}
					</h3>
					<p class="text-xs text-muted-foreground">Approve waiting runs, review results and check failures across all boards.</p>
				</SectionBanner>
				<div class="p-5">
					{#if pendingApprovals.length}
						<ul class="divide-y" aria-label="Waiting for approval">
							{#each pendingApprovals as a (a.id)}
								<li>
									<button type="button" class="flex w-full flex-wrap items-center justify-between gap-x-4 gap-y-1 rounded-md px-2 py-3 text-start text-sm transition-colors hover:bg-accent/50" onclick={() => approvals.show(a.id)}>
										<div class="min-w-0 flex-1">
											<p class="truncate font-medium" title={headline(a)}>{headline(a)}</p>
											<p class="truncate text-xs text-muted-foreground">{a.workflow_name} · {a.label}</p>
										</div>
										<span class="inline-flex items-center gap-1 text-tone-amber"><ShieldCheckIcon class="size-3.5" /> Waiting for approval</span>
										<span class="shrink-0 font-medium text-primary">Review</span>
									</button>
								</li>
							{/each}
						</ul>
					{/if}
					{#if attentionError}
						<p class="text-sm text-destructive" role="alert">Could not refresh tasks needing attention: {attentionError}. Retrying automatically.</p>
					{:else if tasks === null}
						<p class="text-sm text-muted-foreground">Loading tasks needing attention...</p>
					{:else if attention.total === 0}
						{#if !pendingApprovals.length}
							<p class="flex items-center gap-2 text-sm text-muted-foreground">
								<CircleCheckIcon class="size-4 shrink-0 text-tone-green" /> No tasks need attention.
							</p>
						{/if}
					{:else}
						<ul class="divide-y">
							{#each attention.items as { task, reason } (task.id)}
								{@const board = findBoard(workspaces, task.board_id)}
								<li>
									<a href={taskResultHref(id, task.board_id, task.id)} aria-label={`View result for ${task.title}`} class="flex flex-wrap items-center justify-between gap-x-4 gap-y-1 rounded-md px-2 py-3 text-sm transition-colors hover:bg-accent/50">
										<div class="min-w-0 flex-1">
											<p class="truncate font-medium" title={task.title}>{task.title}</p>
											<p class="truncate text-xs text-muted-foreground">{board ? destinationLabel(workspaces, board) : 'Open board'}</p>
										</div>
										<span class={reason === 'Last run failed' ? 'text-destructive' : 'text-muted-foreground'}>{reason}</span>
										<span class="shrink-0 font-medium text-primary">View result</span>
									</a>
								</li>
							{/each}
						</ul>
						{#if attention.items.length < attention.total}
							<p class="mt-2 text-xs text-muted-foreground">Showing {attention.items.length} of {attention.total} tasks.</p>
						{/if}
					{/if}
				</div>
			</section>

			<section class="overflow-hidden glow-card rounded-xl border bg-card lg:col-span-5" aria-labelledby="upcoming-title">
				<SectionBanner icon={CalendarClockIcon} tone="violet">
					<h3 id="upcoming-title" class="text-base font-semibold tracking-tight">Upcoming runs</h3>
					<p class="text-xs text-muted-foreground">What is scheduled to start in the next 7 days.</p>
				</SectionBanner>
				<div class="p-5">
					{#if upcoming.length === 0}
						<div class="flex flex-col items-center gap-1.5 py-1 text-center">
							<IconTile tone="violet"><CalendarClockIcon /></IconTile>
							<p class="text-sm font-medium">Nothing is scheduled</p>
							<p class="max-w-60 text-xs text-muted-foreground">Tasks with a schedule show up here with when they start next.</p>
						</div>
					{:else}
						<ul class="divide-y">
							{#each upcoming.slice(0, 6) as run (run.task_id)}
								<li class="flex items-baseline justify-between gap-4 py-2.5 text-sm">
									<span class="min-w-0 truncate font-medium" title={run.title}>{run.title}</span>
									<span class="shrink-0 text-xs text-muted-foreground">{relative(run.at, now)}{run.recurring ? ' · repeats' : ''}</span>
								</li>
							{/each}
						</ul>
						{#if upcoming.length > 6}<p class="mt-2 text-xs text-muted-foreground">And {upcoming.length - 6} more scheduled tasks.</p>{/if}
					{/if}
				</div>
			</section>
		</div>

		</div>
		</section>

		<section class="mt-8">
			<GroupHeading icon={LayersIcon}>Workspaces</GroupHeading>
			<div class="mt-3"><WorkspaceCards projectId={id} {workspaces} {tasks} /></div>
		</section>

		<section class="mt-8">
		<GroupHeading icon={HistoryIcon}>Timeline</GroupHeading>
		<div class="mt-3 overflow-hidden glow-card rounded-xl border bg-card">
			<SectionBanner icon={ClockIcon} tone="amber">
				<h3 class="text-base font-semibold tracking-tight">Recent activity</h3>
				<p class="text-xs text-muted-foreground">What was done across all workspaces and boards. Each board and workspace has its own history too.</p>
			</SectionBanner>
			<div class="p-5">
				{#key allActivity}
					<HistoryList projectId={id} {workspaces} {now} {revision} compact={!allActivity} timeline actions={activityToggle} />
				{/key}
			</div>
		</div>
		</section>
	</div>
	<WorkspaceDialog
		bind:open={workspaceOpen}
		projectId={id}
		onsaved={(w) => router.navigate(`/projects/${id}/workspaces/${w.id}`)}
	/>
{:else if loadError}
	<p class="m-auto text-sm text-destructive">{loadError}</p>
{/if}
