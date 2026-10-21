<script lang="ts">
	import type { KeyInfo } from '$lib/api/agents'
	import { ApiError } from '$lib/api/core'
	import { toolsApi, type McpInput, type RegistryInput, type RegistryPage, type RegistrySort, type RegistryTool } from '$lib/api/tools'
	import ToolIcon from '$lib/components/ToolIcon.svelte'
	import { Button } from '$lib/components/ui/button/index.js'
	import { Input } from '$lib/components/ui/input/index.js'
	import { Label } from '$lib/components/ui/label/index.js'
	import * as Select from '$lib/components/ui/select/index.js'
	import { Switch } from '$lib/components/ui/switch/index.js'
	import { relative } from '$lib/format'
	import { formatCount, missingInputs, splitInputs, startingValues } from '$lib/tools'
	import { cn } from '$lib/utils'
	import ArrowLeftIcon from '@lucide/svelte/icons/arrow-left'
	import GlobeIcon from '@lucide/svelte/icons/globe'
	import LoaderCircleIcon from '@lucide/svelte/icons/loader-circle'
	import SearchIcon from '@lucide/svelte/icons/search'
	import StarIcon from '@lucide/svelte/icons/star'
	import TerminalIcon from '@lucide/svelte/icons/terminal'
	import TriangleAlertIcon from '@lucide/svelte/icons/triangle-alert'
	import { onMount } from 'svelte'

	// Browses the official MCP registry (administrators only), from a copy Themis keeps locally so that searching,
	// categories and sorting are instant. Everything the registry lists is shown; what this project cannot run is
	// greyed out and says why when picked. A tool that can run asks for what it needs, then hands its fields to the tool
	// form, which saves it like any other tool.
	let {
		projectId,
		keys,
		onpick,
		oncancel,
	}: {
		projectId: number | null // null: from Settings, judged by the default image
		keys: KeyInfo[]
		onpick: (fields: McpInput) => void
		oncancel: () => void
	} = $props()

	const FEATURED = 'featured'
	const SORTS: { id: RegistrySort; label: string; hint: string }[] = [
		{ id: 'recommended', label: 'Recommended', hint: 'Runnable here, from a verified publisher, filled in, recently updated and (for npm) downloaded come first. The registry has no popularity figure.' },
		{ id: 'downloads', label: 'Most downloaded', hint: 'npm downloads in the last month. Only npm packages have a count, and they are counted gradually (see the bottom of this window); tools without one come last.' },
		{ id: 'updated', label: 'Recently updated', hint: 'When the publisher last updated the listing.' },
		{ id: 'name', label: 'Name, A to Z', hint: '' },
	]

	let query = $state('')
	let category = $state(FEATURED) // FEATURED, '' for all tools, or a category id
	let sort = $state<RegistrySort>('recommended')
	let supportedOnly = $state(false)

	let featured = $state<RegistryTool[]>([])
	let tools = $state<RegistryTool[]>([])
	let page = $state<RegistryPage | null>(null)
	let loading = $state(true)
	let more = $state(false)
	let error = $state('')

	let selected = $state<RegistryTool | null>(null)
	let values = $state<Record<string, string>>({})
	let working = $state(false)
	let formError = $state('')

	const status = $derived(page?.status)
	const building = $derived(status?.state === 'building' || (status?.state === 'empty' && !error))
	const showingFeatured = $derived(category === FEATURED && !query.trim())
	const shown = $derived(showingFeatured ? featured : tools)
	const total = $derived(showingFeatured ? featured.length : (page?.total ?? 0))
	const sortHint = $derived(SORTS.find((s) => s.id === sort)?.hint ?? '')
	const split = $derived(selected ? splitInputs(selected.inputs) : { needed: [], optional: [] })
	const missing = $derived(selected ? missingInputs(selected.inputs, values) : [])
	const categories = $derived(page?.categories ?? [])
	const allCount = $derived(categories.reduce((n, c) => n + c.count, 0))

	const message = (e: unknown, fallback: string) => (e instanceof ApiError || e instanceof Error ? e.message : fallback)

	// An answer that arrives after a newer question was asked is dropped.
	let ticket = 0
	let timer: ReturnType<typeof setTimeout> | undefined

	async function fetchPage(offset: number) {
		const mine = ++ticket
		try {
			const result = await toolsApi.registryTools(projectId, {
				q: query.trim(),
				category: category === FEATURED ? '' : category,
				sort,
				supportedOnly,
				offset,
			})
			if (mine !== ticket) return
			page = result
			tools = offset ? [...tools, ...result.tools] : result.tools
			error = ''
		} catch (e) {
			if (mine === ticket) error = message(e, 'Could not read the MCP registry')
		} finally {
			if (mine === ticket) {
				loading = false
				more = false
			}
		}
	}

	function search() {
		clearTimeout(timer)
		loading = true
		timer = setTimeout(() => fetchPage(0), 150)
	}

	onMount(() => {
		// featured tools are looked up one by one and work before the catalog exists; the catalog starts building
		void toolsApi.registryFeatured(projectId).then(
			(f) => (featured = f),
			(e) => (error = message(e, 'Could not reach the MCP registry')),
		)
		void fetchPage(0)
		return () => {
			clearTimeout(timer)
			clearTimeout(poll)
		}
	})

	// While the catalog is being built or updated, look again every few seconds.
	let poll: ReturnType<typeof setTimeout> | undefined
	$effect(() => {
		clearTimeout(poll)
		if (status?.state === 'building' || status?.state === 'updating' || status?.counting) {
			poll = setTimeout(() => void fetchPage(0), 3000)
		}
	})

	function choose_category(id: string) {
		category = id
		search()
	}

	function typed() {
		if (query.trim() && category === FEATURED) category = ''
		search()
	}

	async function pick(tool: RegistryTool) {
		selected = tool
		values = startingValues(tool.inputs)
		formError = ''
		if (tool.supported && tool.inputs.length === 0) {
			// the list leaves out what a tool needs to have filled in: ask for the whole entry
			try {
				const full = await toolsApi.registryEntry(projectId, tool.name)
				if (selected?.name === tool.name) {
					selected = { ...tool, ...full }
					values = startingValues(full.inputs)
				}
			} catch (e) {
				formError = message(e, 'Could not read this tool')
			}
		}
	}

	async function add() {
		if (!selected || missing.length) return
		working = true
		formError = ''
		try {
			onpick(await toolsApi.registryPrefill(projectId, selected.name, values))
		} catch (e) {
			formError = message(e, 'Could not set up this tool')
		} finally {
			working = false
		}
	}

	async function refresh() {
		try {
			await toolsApi.registryRefresh(projectId)
			await fetchPage(0)
		} catch (e) {
			error = message(e, 'Could not update the catalog')
		}
	}

	const keyName = (id: string) => keys.find((k) => String(k.id) === id)?.name
</script>

{#snippet field(input: RegistryInput)}
	<div class="grid gap-1.5">
		<Label for={`reg-${input.id}`}>{input.label}{#if input.required}<span class="text-destructive"> *</span>{/if}</Label>
		{#if input.secret}
			<Select.Root type="single" value={values[input.id] ?? ''} onValueChange={(v) => (values[input.id] = v)}>
				<Select.Trigger id={`reg-${input.id}`} class="w-full">{keyName(values[input.id] ?? '') ?? 'Choose a key'}</Select.Trigger>
				<Select.Content>
					{#each keys as k (k.id)}<Select.Item value={String(k.id)} label={k.name}>{k.name}</Select.Item>{/each}
				</Select.Content>
			</Select.Root>
			{#if keys.length === 0}<p class="text-xs text-muted-foreground">Add keys under Settings, Keys first.</p>{/if}
		{:else if input.choices.length}
			<Select.Root type="single" value={values[input.id] ?? ''} onValueChange={(v) => (values[input.id] = v)}>
				<Select.Trigger id={`reg-${input.id}`} class="w-full">{values[input.id] || 'Choose one'}</Select.Trigger>
				<Select.Content>
					{#each input.choices as c (c)}<Select.Item value={c} label={c}>{c}</Select.Item>{/each}
				</Select.Content>
			</Select.Root>
		{:else}
			<Input id={`reg-${input.id}`} bind:value={values[input.id]} placeholder={input.default} class="font-mono" />
		{/if}
		{#if input.description}<p class="text-xs text-muted-foreground">{input.description}</p>{/if}
	</div>
{/snippet}

{#snippet card(tool: RegistryTool)}
	<button
		type="button"
		class={cn('flex h-full w-full items-start gap-3 rounded-xl border bg-card px-3.5 py-3 text-start transition-colors hover:border-primary/40 hover:bg-accent/40', !tool.supported && 'opacity-55')}
		onclick={() => pick(tool)}
	>
		<ToolIcon src={tool.icon} name={tool.name} title={tool.title} />
		<span class="min-w-0 flex-1">
			<span class="flex items-center gap-1.5">
				<span class="truncate text-sm font-semibold">{tool.title}</span>
				{#if tool.note}<StarIcon class="size-3 shrink-0 text-amber-500" aria-label="Featured" />{/if}
			</span>
			<span class="mt-0.5 line-clamp-2 text-xs text-muted-foreground">{tool.note || tool.description || 'No description.'}</span>
			<span class="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-muted-foreground">
				{#if tool.source === 'remote'}<span class="inline-flex items-center gap-1"><GlobeIcon class="size-3" /> Hosted</span>
				{:else if tool.source === 'package'}<span class="inline-flex items-center gap-1"><TerminalIcon class="size-3" /> Runs in the cell</span>{/if}
				{#if tool.downloads}<span>{formatCount(tool.downloads)} downloads/month</span>{/if}
				{#if tool.updated}<span>Updated {relative(tool.updated)}</span>{/if}
			</span>
			{#if !tool.supported}<span class="mt-1.5 block text-xs text-muted-foreground">Not yet: {tool.reason_text}</span>{/if}
		</span>
	</button>
{/snippet}

{#if selected}
	<div class="slim-scrollbar grid h-full min-h-0 content-start gap-4 overflow-y-auto pe-1">
		<button type="button" class="flex items-center gap-1 justify-self-start text-sm text-muted-foreground hover:text-foreground" onclick={() => (selected = null)}>
			<ArrowLeftIcon class="size-4" /> Back to the list
		</button>
		<div class="flex items-start gap-3">
			<ToolIcon src={selected.icon} name={selected.name} title={selected.title} class="size-14 text-sm" />
			<div class="min-w-0">
				<h4 class="text-lg font-semibold leading-tight">{selected.title}</h4>
				<p class="font-mono text-xs text-muted-foreground">{selected.name} {selected.version}</p>
				{#if selected.repository}<a href={selected.repository} target="_blank" rel="noreferrer" class="text-xs text-primary underline-offset-2 hover:underline">{selected.repository}</a>{/if}
			</div>
		</div>
		{#if selected.description}<p class="text-sm">{selected.description}</p>{/if}

		{#if !selected.supported}
			<div class="flex gap-2 rounded-md border border-dashed bg-muted/40 px-3 py-2 text-sm" role="note">
				<TriangleAlertIcon class="mt-0.5 size-4 shrink-0 text-muted-foreground" />
				<p>Themis cannot add this one yet. {selected.reason_text}</p>
			</div>
		{:else}
			<div class="rounded-md border bg-muted/40 px-3 py-2 text-sm">
				<p class="text-xs text-muted-foreground">{selected.source === 'package' ? 'Started inside the cell of each run:' : 'Connected to at:'}</p>
				<p class="break-all font-mono text-xs">{selected.runs}</p>
				<p class="mt-2 text-xs text-muted-foreground">
					{selected.source === 'package'
						? "This is code published by a third party. It runs with the agent's access to its folders and with any key you give it."
						: 'Everything the agent sends to this tool leaves your machine for that address.'}
				</p>
			</div>
			{#each split.needed as input (input.id)}{@render field(input)}{/each}
			{#if split.optional.length}
				<details class="grid gap-3 rounded-md border px-3 py-2">
					<summary class="cursor-pointer text-sm text-muted-foreground">Optional settings ({split.optional.length})</summary>
					<div class="mt-3 grid gap-3">
						{#each split.optional as input (input.id)}{@render field(input)}{/each}
					</div>
				</details>
			{/if}
		{/if}

		{#if formError}<p class="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive" role="alert">{formError}</p>{/if}
		<div class="flex items-center justify-end gap-2">
			{#if selected.supported && missing.length}<span class="me-auto text-xs text-muted-foreground">Fill in: {missing.join(', ')}</span>{/if}
			<Button variant="ghost" onclick={oncancel}>Cancel</Button>
			{#if selected.supported}
				<Button disabled={working || missing.length > 0} onclick={add}>
					{#if working}<LoaderCircleIcon class="animate-spin" />{/if} Continue
				</Button>
			{/if}
		</div>
	</div>
{:else}
	<div class="flex h-full min-h-0 flex-col gap-3">
		<div class="flex flex-wrap items-center gap-2">
			<div class="relative min-w-56 flex-1">
				<SearchIcon class="pointer-events-none absolute start-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
				<Input bind:value={query} oninput={typed} placeholder="Search tools, such as notion, slack or postgres" class="ps-9" aria-label="Search the MCP registry" />
			</div>
			<Select.Root type="single" bind:value={sort} onValueChange={() => search()}>
				<Select.Trigger class="w-48" aria-label="Sort by">{SORTS.find((s) => s.id === sort)?.label}</Select.Trigger>
				<Select.Content>
					{#each SORTS as s (s.id)}<Select.Item value={s.id} label={s.label}>{s.label}</Select.Item>{/each}
				</Select.Content>
			</Select.Root>
			<label class="flex items-center gap-2 text-sm text-muted-foreground">
				<Switch checked={supportedOnly} onCheckedChange={(v) => ((supportedOnly = v), search())} aria-label="Only tools that can run here" /> Runnable only
			</label>
		</div>
		{#if sortHint && !showingFeatured}<p class="-mt-1 text-xs text-muted-foreground">{sortHint}</p>{/if}

		{#if building}
			<div class="flex items-start gap-2 rounded-md border bg-muted/40 px-3 py-2 text-sm" role="status">
				<LoaderCircleIcon class="mt-0.5 size-4 shrink-0 animate-spin text-muted-foreground" />
				<p>
					Reading the registry for the first time: {status?.count?.toLocaleString() ?? 0} tools so far. This takes a few minutes and happens once; after that only
					what changed is read. Featured tools work meanwhile.
				</p>
			</div>
		{:else if status?.state === 'error' || error}
			<div class="flex items-start gap-2 rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive" role="alert">
				<p class="flex-1">{error || status?.error}</p>
				<Button size="sm" variant="outline" onclick={refresh}>Try again</Button>
			</div>
		{/if}

		<div class="flex min-h-0 flex-1 gap-4">
			<nav class="slim-scrollbar hidden w-52 shrink-0 overflow-y-auto overflow-x-hidden sm:block" aria-label="Categories">
				<ul class="grid gap-0.5 text-sm">
					<li>
						<button type="button" class={cn('flex w-full items-center gap-2 rounded-md px-2.5 py-1.5 text-start hover:bg-accent/60', category === FEATURED && !query.trim() && 'bg-accent font-medium')} onclick={() => choose_category(FEATURED)}>
							<StarIcon class="size-3.5 text-amber-500" /> <span class="flex-1">Featured</span>
						</button>
					</li>
					<li>
						<button type="button" class={cn('flex w-full items-center gap-2 rounded-md px-2.5 py-1.5 text-start hover:bg-accent/60', category === '' && 'bg-accent font-medium')} onclick={() => choose_category('')}>
							<span class="flex-1">All tools</span>
							{#if page && page.total >= 0 && allCount}<span class="text-xs text-muted-foreground">{allCount.toLocaleString()}</span>{/if}
						</button>
					</li>
					{#each categories as c (c.id)}
						<li>
							<button type="button" class={cn('flex w-full items-center gap-2 rounded-md px-2.5 py-1.5 text-start hover:bg-accent/60', category === c.id && 'bg-accent font-medium')} onclick={() => choose_category(c.id)}>
								<span class="flex-1 truncate">{c.label}</span>
								<span class="text-xs text-muted-foreground">{c.count.toLocaleString()}</span>
							</button>
						</li>
					{/each}
				</ul>
			</nav>

			<div class="slim-scrollbar min-h-0 flex-1 overflow-y-auto pe-1">
				{#if loading && !shown.length}
					<p class="py-10 text-center text-sm text-muted-foreground">Loading...</p>
				{:else if shown.length === 0}
					<p class="py-10 text-center text-sm text-muted-foreground">
						{building ? 'Nothing to search yet. Featured tools are listed under Featured.' : 'Nothing matches that.'}
					</p>
				{:else}
					<p class="mb-2 text-xs text-muted-foreground">{showingFeatured ? 'Featured tools' : `${total.toLocaleString()} tools`}</p>
					<ul class="grid gap-2 lg:grid-cols-2">
						{#each shown as tool (tool.name)}<li>{@render card(tool)}</li>{/each}
					</ul>
					{#if !showingFeatured && tools.length < total}
						<div class="flex justify-center py-4">
							<Button variant="outline" size="sm" disabled={more} onclick={() => ((more = true), fetchPage(tools.length))}>
								{#if more}<LoaderCircleIcon class="animate-spin" />{/if} Show more ({(total - tools.length).toLocaleString()} left)
							</Button>
						</div>
					{/if}
				{/if}
			</div>
		</div>

		<div class="flex items-center justify-between gap-2 border-t pt-2">
			<p class="text-xs text-muted-foreground">
				{#if status?.synced_at}Catalog of {status.count.toLocaleString()} tools, read {relative(status.synced_at)}.{#if status.counting}{' '}Counting npm downloads...{/if}{/if}
			</p>
			<div class="flex gap-2">
				{#if status?.state === 'ready'}<Button variant="ghost" size="sm" onclick={refresh}>Update now</Button>{/if}
				<Button variant="ghost" size="sm" onclick={oncancel}>Close</Button>
			</div>
		</div>
	</div>
{/if}
