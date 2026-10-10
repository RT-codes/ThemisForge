<script lang="ts">
	import type { Agent, CellDefaults, HarnessInfo, KeyInfo, McpServer, Project, Skill, Volume } from '$lib/api'
	import { Button } from '$lib/components/ui/button/index.js'
	import AgentConnections from '$lib/components/AgentConnections.svelte'
	import { describeCell, effectiveCell } from '$lib/cell'
	import { relative } from '$lib/format'
	import { onCodeCopyClick, renderMarkdown } from '$lib/markdown'
	import { cn } from '$lib/utils'
	import AlertTriangleIcon from '@lucide/svelte/icons/triangle-alert'
	import BotIcon from '@lucide/svelte/icons/bot'
	import BoxIcon from '@lucide/svelte/icons/box'
	import FolderIcon from '@lucide/svelte/icons/folder'
	import FolderOpenIcon from '@lucide/svelte/icons/folder-open'
	import GlobeIcon from '@lucide/svelte/icons/globe'
	import KeyRoundIcon from '@lucide/svelte/icons/key-round'
	import PencilIcon from '@lucide/svelte/icons/pencil'
	import SparklesIcon from '@lucide/svelte/icons/sparkles'
	import TerminalIcon from '@lucide/svelte/icons/terminal'

	// What an agent is, at a glance. It only reads: the Edit button opens the editor, so looking never changes anything.
	let {
		agent,
		harnesses,
		skills,
		servers,
		keys,
		volumes,
		project,
		defaults,
		onedit,
	}: {
		agent: Agent
		harnesses: HarnessInfo[]
		skills: Skill[]
		servers: McpServer[]
		keys: KeyInfo[]
		volumes: Volume[]
		project: Project | null
		defaults: CellDefaults | null
		onedit: () => void
	} = $props()

	const harness = $derived(harnesses.find((h) => h.id === agent.harness))
	const efforts = { '': 'Default effort', low: 'Low effort', medium: 'Medium effort', high: 'High effort' } as const
	const mySkills = $derived(agent.skills.map((name) => ({ name, skill: skills.find((s) => s.name === name) })))
	const myServers = $derived(agent.mcp_servers.map((id) => servers.find((s) => s.id === id)).filter((s): s is McpServer => !!s))
	const myKeys = $derived(agent.secrets.map((id) => keys.find((k) => k.id === id)).filter((k): k is KeyInfo => !!k))
	const myFolders = $derived(agent.mounts.map((m) => ({ mode: m.mode, volume: volumes.find((v) => v.id === m.volume_id) })).filter((f) => f.volume))
	const cell = $derived(defaults ? effectiveCell(defaults, project?.cell_profile, agent.cell_profile) : null)
	// rich text from a file a person (or an agent) wrote: see markdown.ts for what untrusted mode takes out
	const instructions = $derived(agent.instructions.trim() ? renderMarkdown(agent.instructions, { untrusted: true }).html : '')
	const toneOf = (s: McpServer) => (s.config_error ? 'bg-yellow-400' : s.last_test === null ? 'bg-muted-foreground/40' : s.last_test.ok ? 'bg-emerald-400' : 'bg-destructive')
	const toneText = (s: McpServer) => (s.config_error ? 'Its file has a problem' : s.last_test === null ? 'Not tried yet' : `Tried ${relative(s.last_test.at)}: ${s.last_test.ok ? 'worked' : 'failed'}`)
</script>

<div class="grid gap-3">
	<section class="rounded-lg border bg-card p-4">
		<div class="flex flex-wrap items-start gap-3">
			<span class="flex size-9 shrink-0 items-center justify-center rounded-lg bg-primary/15 text-primary"><BotIcon class="size-5" /></span>
			<div class="min-w-0 flex-1">
				<h3 class="truncate text-lg font-semibold tracking-tight">{agent.name}</h3>
				<p class="text-sm text-muted-foreground">{agent.role || 'No role yet'}</p>
				<div class="mt-2 flex flex-wrap gap-1.5 text-xs">
					<span class="rounded-md bg-muted px-1.5 py-0.5">{harness?.label ?? agent.harness}</span>
					<span class="rounded-md bg-muted px-1.5 py-0.5 font-mono">{agent.model || 'Default model'}</span>
					<span class="rounded-md bg-muted px-1.5 py-0.5">{efforts[agent.reasoning_effort]}</span>
				</div>
			</div>
			<div class="flex shrink-0 items-center gap-2">
				<Button variant="outline" size="sm" href="/projects/{agent.project_id}/files#config/{agent.path}" title="The agent's file in the config folder"><FolderOpenIcon /> Open file</Button>
				<Button size="sm" onclick={onedit}><PencilIcon /> Edit</Button>
			</div>
		</div>
		{#if agent.description}<p class="mt-3 text-sm whitespace-pre-line text-muted-foreground">{agent.description}</p>{/if}
		{#if agent.config_error}
			<p class="mt-4 flex items-start gap-2 rounded-lg border border-yellow-500/30 bg-yellow-500/5 px-3 py-2 text-sm text-yellow-300" role="alert">
				<AlertTriangleIcon class="mt-0.5 size-4 shrink-0" />
				<span>
					This agent's file has a problem, so it will not run until it is fixed: {agent.config_error}. What is shown here is the last version that worked. Open the file to fix it, or save the agent from the editor.
				</span>
			</p>
		{/if}
	</section>

	<section class="rounded-lg border bg-card p-4">
		<h4 class="text-sm font-semibold tracking-tight">Instructions</h4>
		<p class="text-xs text-muted-foreground">Always put in front of whatever task this agent is given.</p>
		{#if instructions}
			<!-- trusted: renderMarkdown ran in untrusted mode, so nothing in the text can be markup of its own -->
			<!-- svelte-ignore a11y_click_events_have_key_events, a11y_no_static_element_interactions -->
			<div class="docs-prose prose prose-sm prose-invert slim-scrollbar mt-2.5 max-h-96 max-w-none overflow-auto rounded-md border bg-background/40 p-3 text-sm" onclick={onCodeCopyClick}>
				{@html instructions}
			</div>
		{:else}
			<p class="mt-3 rounded-lg border border-dashed px-3 py-5 text-center text-sm text-muted-foreground">No instructions yet. Edit the agent to tell it how to work.</p>
		{/if}
	</section>

	<div class="grid gap-3 xl:grid-cols-2">
		{#if harness?.supports_skills}
			<section class="rounded-lg border bg-card p-4">
				<h4 class="text-sm font-semibold tracking-tight">Skills</h4>
				{#if mySkills.length}
					<ul class="mt-2.5 grid gap-1.5">
						{#each mySkills as { name, skill } (name)}
							<li class="flex items-start gap-2.5 rounded-md border px-2.5 py-1.5">
								<SparklesIcon class={cn('mt-0.5 size-4 shrink-0', skill ? 'text-primary' : 'text-yellow-300')} />
								<span class="min-w-0">
									<span class="block truncate font-mono text-sm">{name}</span>
									<span class={cn('block text-xs', skill ? 'text-muted-foreground' : 'text-yellow-300')}>{skill ? skill.description || 'No description' : 'No longer exists in this project'}</span>
								</span>
							</li>
						{/each}
					</ul>
				{:else}
					<p class="mt-2 text-sm text-muted-foreground">None. Guides it reads when a task calls for them.</p>
				{/if}
			</section>
		{/if}

		{#if harness?.supports_mcp}
			<section class="rounded-lg border bg-card p-4">
				<h4 class="text-sm font-semibold tracking-tight">Tools</h4>
				{#if myServers.length}
					<ul class="mt-2.5 grid gap-1.5">
						{#each myServers as s (s.id)}
							<li class="flex items-start gap-2.5 rounded-md border px-2.5 py-1.5">
								{#if s.kind === 'http'}<GlobeIcon class="mt-0.5 size-4 shrink-0 text-primary" />{:else}<TerminalIcon class="mt-0.5 size-4 shrink-0 text-primary" />{/if}
								<span class="min-w-0 flex-1">
									<span class="block truncate font-mono text-sm">{s.name}</span>
									<span class="block truncate text-xs text-muted-foreground">{s.description || (s.kind === 'http' ? s.url : s.command)}</span>
								</span>
								<span class={cn('mt-1.5 size-2.5 shrink-0 rounded-full', toneOf(s))} title={toneText(s)}></span>
							</li>
						{/each}
					</ul>
				{:else}
					<p class="mt-2 text-sm text-muted-foreground">None. Extra tools it can use while it works (MCP servers).</p>
				{/if}
			</section>
		{/if}

		<section class="rounded-lg border bg-card p-4">
			<h4 class="text-sm font-semibold tracking-tight">Folders it can reach</h4>
			<ul class="mt-2.5 grid gap-1.5">
				<li class="flex items-center gap-2.5 rounded-md border px-2.5 py-1.5">
					<FolderIcon class="size-4 shrink-0 text-muted-foreground" />
					<span class="min-w-0 flex-1 truncate font-mono text-sm">/workspace/shared</span>
					<span class="text-xs text-muted-foreground">always there</span>
				</li>
				{#each myFolders as f (f.volume!.id)}
					<li class="flex items-center gap-2.5 rounded-md border px-2.5 py-1.5">
						<FolderIcon class="size-4 shrink-0 text-primary" />
						<span class="min-w-0 flex-1 truncate font-mono text-sm">/workspace/{f.volume!.name}</span>
						<span class="text-xs text-muted-foreground">{f.mode === 'ro' ? 'read only' : 'read and write'}</span>
					</li>
				{/each}
			</ul>
		</section>

		<section class="rounded-lg border bg-card p-4">
			<h4 class="text-sm font-semibold tracking-tight">Cell</h4>
			<div class="mt-2.5 grid gap-1.5 text-sm">
				<p class="flex items-center gap-2.5 rounded-md border px-2.5 py-1.5">
					<BoxIcon class="size-4 shrink-0 text-muted-foreground" />
					<span class="min-w-0 flex-1">{agent.cell_profile ? 'Its own cell' : 'The project\'s cell'}{cell ? `: ${describeCell(cell)}` : ''}</span>
				</p>
				{#if cell}<p class="truncate px-1 font-mono text-xs text-muted-foreground" title={cell.image}>{cell.image}</p>{/if}
			</div>
		</section>

		{#if harness?.supports_keys && agent.connections.length}
			<section class="rounded-lg border bg-card p-4">
				<h4 class="text-sm font-semibold tracking-tight">Connections</h4>
				<div class="mt-2.5"><AgentConnections projectId={agent.project_id} selected={agent.connections} readonly /></div>
			</section>
		{/if}

		{#if harness?.supports_keys && myKeys.length}
			<section class="rounded-lg border bg-card p-4">
				<h4 class="text-sm font-semibold tracking-tight">Keys</h4>
				<ul class="mt-2.5 grid gap-1.5">
					{#each myKeys as k (k.id)}
						<li class="flex items-center gap-2.5 rounded-md border px-2.5 py-1.5">
							<KeyRoundIcon class="size-4 shrink-0 text-muted-foreground" />
							<span class="min-w-0 flex-1 truncate text-sm">{k.name}</span>
							<span class="font-mono text-xs text-muted-foreground">${k.env_name}</span>
						</li>
					{/each}
				</ul>
			</section>
		{/if}
	</div>
</div>
