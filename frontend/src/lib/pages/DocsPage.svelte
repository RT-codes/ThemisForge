<script lang="ts">
	import { findPage, groups, pages, render, search } from '$lib/docs'
	import { Button } from '$lib/components/ui/button/index.js'
	import { Input } from '$lib/components/ui/input/index.js'
	import Logo from '$lib/components/Logo.svelte'
	import { router } from '$lib/router.svelte'
	import { cn } from '$lib/utils'
	import ArrowLeftIcon from '@lucide/svelte/icons/arrow-left'
	import ArrowRightIcon from '@lucide/svelte/icons/arrow-right'
	import SearchIcon from '@lucide/svelte/icons/search'
	import { tick } from 'svelte'

	let { slug, standalone = false }: { slug: string; standalone?: boolean } = $props()

	const page = $derived(findPage(slug))
	const doc = $derived(page ? render(page) : null)
	const index = $derived(pages.findIndex((p) => p.slug === slug))
	const prev = $derived(index > 0 ? pages[index - 1] : null)
	const next = $derived(index >= 0 && index < pages.length - 1 ? pages[index + 1] : null)

	let query = $state('')
	const hits = $derived(search(query))
	let activeId = $state<string | null>(null)
	let article = $state<HTMLElement | null>(null)

	// after a page change or a link with #heading: scroll to it, or to the top
	let shownSlug: string | null = null
	$effect(() => {
		const hash = router.hash
		// smooth only when moving around within a page, a new page just appears
		const behavior: ScrollBehavior = slug === shownSlug && !reducedMotion() ? 'smooth' : 'instant'
		shownSlug = slug
		tick().then(() => {
			const target = hash ? document.getElementById(hash) : null
			if (target) target.scrollIntoView({ behavior })
			else window.scrollTo({ top: 0, behavior })
		})
	})

	const reducedMotion = () => window.matchMedia('(prefers-reduced-motion: reduce)').matches

	// "On this page" links: scroll smoothly instead of jumping
	function jump(e: MouseEvent, id: string) {
		if (e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return
		e.preventDefault()
		router.navigate(`/docs/${slug}#${id}`)
		document.getElementById(id)?.scrollIntoView({ behavior: reducedMotion() ? 'instant' : 'smooth' })
		activeId = id
	}

	// highlight the section being read in "On this page"
	$effect(() => {
		const headings = doc?.headings ?? []
		void slug
		activeId = headings[0]?.id ?? null
		if (!article || !headings.length) return
		const seen = new Set<string>()
		const observer = new IntersectionObserver(
			(entries) => {
				for (const e of entries) e.isIntersecting ? seen.add(e.target.id) : seen.delete(e.target.id)
				const first = headings.find((h) => seen.has(h.id))
				if (first) activeId = first.id
			},
			{ rootMargin: '-72px 0px -65% 0px' }
		)
		tick().then(() => {
			for (const h of headings) {
				const el = document.getElementById(h.id)
				if (el) observer.observe(el)
			}
		})
		return () => observer.disconnect()
	})

	// code block copy buttons live inside the rendered markdown, so listen on the article itself
	$effect(() => {
		const el = article
		el?.addEventListener('click', onArticleClick)
		return () => el?.removeEventListener('click', onArticleClick)
	})

	function open(slugToOpen: string, id: string | null) {
		query = ''
		router.navigate(`/docs/${slugToOpen}${id ? `#${id}` : ''}`)
	}

	async function onArticleClick(e: MouseEvent) {
		const button = (e.target as Element).closest<HTMLButtonElement>('[data-copy]')
		if (!button) return
		const code = button.closest('.docs-code')?.querySelector('code')?.textContent ?? ''
		try {
			await navigator.clipboard.writeText(code)
			button.textContent = 'Copied'
		} catch {
			// not a secure context (plain http): select the code so Ctrl+C works
			const range = document.createRange()
			range.selectNodeContents(button.closest('.docs-code')!.querySelector('code')!)
			window.getSelection()?.removeAllRanges()
			window.getSelection()?.addRange(range)
			button.textContent = 'Press Ctrl+C'
		}
		setTimeout(() => (button.textContent = 'Copy'), 1800)
	}
</script>

{#snippet nav()}
	<div class="relative">
		<SearchIcon class="pointer-events-none absolute start-2.5 top-2.5 size-4 text-muted-foreground" />
		<Input bind:value={query} placeholder="Search the docs" class="ps-8" aria-label="Search the docs" />
	</div>

	{#if query.trim()}
		<div class="mt-3 grid grid-cols-[minmax(0,1fr)] gap-1" role="listbox" aria-label="Search results">
			{#each hits as hit (hit.slug + hit.id)}
				<button type="button" class="w-full min-w-0 overflow-hidden rounded-md px-2 py-1.5 text-start text-sm transition-colors hover:bg-accent" onclick={() => open(hit.slug, hit.id)}>
					<span class="block truncate font-medium">{hit.heading}</span>
					<span class="block truncate text-xs text-muted-foreground">{hit.page}</span>
					<span class="mt-0.5 line-clamp-2 text-xs text-muted-foreground/80">{hit.snippet}</span>
				</button>
			{:else}
				<p class="px-2 py-3 text-sm text-muted-foreground">Nothing found for "{query}".</p>
			{/each}
		</div>
	{:else}
		<nav class="mt-4 grid gap-5" aria-label="Documentation">
			{#each groups as group (group.name)}
				<div>
					<h3 class="mb-1 px-2 text-xs font-medium tracking-wide text-muted-foreground uppercase">{group.name}</h3>
					<ul class="grid gap-0.5">
						{#each group.pages as p (p.slug)}
							<li>
								<a
									href="/docs/{p.slug}"
									aria-current={p.slug === slug ? 'page' : undefined}
									class={cn(
										'block rounded-md px-2 py-1.5 text-sm transition-colors hover:bg-accent hover:text-foreground',
										p.slug === slug ? 'bg-accent font-medium text-foreground' : 'text-muted-foreground'
									)}>{p.title}</a
								>
							</li>
						{/each}
					</ul>
				</div>
			{/each}
		</nav>
	{/if}
{/snippet}

{#if standalone}
	<header class="sticky top-0 z-20 flex h-14 items-center gap-3 border-b bg-background/85 px-4 backdrop-blur sm:px-6">
		<a href="/docs" class="flex items-center gap-2.5">
			<Logo />
			<span class="font-semibold tracking-tight">ThemisForge</span>
			<span class="text-sm text-muted-foreground">Docs</span>
		</a>
		<Button class="ms-auto" size="sm" onclick={() => router.navigate('/')}>Sign in</Button>
	</header>
{/if}

<div class="forge-glow flex-1">
	<div class="mx-auto grid w-full max-w-7xl gap-x-10 px-4 py-8 sm:px-6 lg:grid-cols-[14.5rem_minmax(0,1fr)]">
		<aside class="mb-6 lg:mb-0">
			<details class="rounded-lg border p-3 lg:hidden">
				<summary class="cursor-pointer text-sm font-medium">Browse the docs</summary>
				<div class="mt-3">{@render nav()}</div>
			</details>
			<div class={cn('sticky hidden overflow-y-auto pe-1 lg:block', standalone ? 'top-20 max-h-[calc(100svh-6rem)]' : 'top-6 max-h-[calc(100svh-3rem)]')}>{@render nav()}</div>
		</aside>

		{#if page && doc}
			<div class="flex min-w-0 gap-10">
			<article bind:this={article} class="min-w-0 max-w-3xl flex-1" aria-label={page.title}>
				<p class="mb-2 text-xs font-medium tracking-wide text-primary uppercase">{page.group}</p>
				<div class="docs-prose prose prose-invert max-w-none">
					<!-- trusted: rendered from the markdown files in /docs at build time -->
					{@html doc.html}
				</div>

				<nav class="mt-12 grid gap-3 border-t pt-6 sm:grid-cols-2" aria-label="Previous and next page">
					{#if prev}
						<a href="/docs/{prev.slug}" class="group rounded-xl border p-4 transition-colors hover:border-primary/40">
							<span class="flex items-center gap-1.5 text-xs text-muted-foreground"><ArrowLeftIcon class="size-3.5" /> Previous</span>
							<span class="mt-1 block font-medium">{prev.title}</span>
						</a>
					{:else}<span></span>{/if}
					{#if next}
						<a href="/docs/{next.slug}" class="group rounded-xl border p-4 text-end transition-colors hover:border-primary/40">
							<span class="flex items-center justify-end gap-1.5 text-xs text-muted-foreground">Next <ArrowRightIcon class="size-3.5" /></span>
							<span class="mt-1 block font-medium">{next.title}</span>
						</a>
					{/if}
				</nav>
			</article>

			<aside class="hidden w-48 shrink-0 min-[1440px]:block">
				{#if doc.headings.length}
					<div class={cn('sticky', standalone ? 'top-20' : 'top-6')}>
						<h3 class="mb-2 text-xs font-medium tracking-wide text-muted-foreground uppercase">On this page</h3>
						<ul class="grid gap-1 border-s text-sm">
							{#each doc.headings as h (h.id)}
								<li>
									<a
										href="#{h.id}"
										onclick={(e) => jump(e, h.id)}
										class={cn(
											'-ms-px block border-s py-0.5 transition-colors',
											h.depth === 3 ? 'ps-6' : 'ps-3',
											activeId === h.id
												? 'border-primary text-foreground'
												: 'border-transparent text-muted-foreground hover:text-foreground'
										)}>{h.text}</a
									>
								</li>
							{/each}
						</ul>
					</div>
				{/if}
			</aside>
			</div>
		{:else}
			<div class="py-16 text-center">
				<p class="text-lg font-medium">Page not found</p>
				<p class="mt-1 text-sm text-muted-foreground">There is no documentation page called "{slug}".</p>
				<Button class="mt-4" onclick={() => router.navigate('/docs')}>Back to the docs</Button>
			</div>
		{/if}
	</div>
</div>
