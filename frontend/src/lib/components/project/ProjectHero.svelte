<script lang="ts">
	import type { Project } from '$lib/api'
	import DynamicIcon from '$lib/components/DynamicIcon.svelte'
	import IconTile from '$lib/components/IconTile.svelte'
	import SectionBanner from '$lib/components/SectionBanner.svelte'
	import FolderKanbanIcon from '@lucide/svelte/icons/folder-kanban'
	import type { Snippet } from 'svelte'

	// The header both project pages open with, so the overview and the settings read as one place: the project's icon
	// in a framed tile, what the page is, and the page's own actions at the top right. It is not a card: it sits
	// straight on the page.
	// `eyebrow` is the small line above the title, for a page that is not the project itself.
	let {
		project,
		title,
		eyebrow = '',
		lead = '',
		detail = '',
		children,
		actions,
	}: {
		project: Project
		title: string
		eyebrow?: string
		lead?: string
		detail?: string
		/** below the text: chips, a halt notice */
		children?: Snippet
		actions?: Snippet
	} = $props()
</script>

<header>
	<SectionBanner {actions} class="min-h-32 items-start rounded-xl border-b-0 px-0 py-2">
		<div class="flex min-w-0 items-start gap-4">
			<IconTile size="lg" tone="amber">
				<DynamicIcon name={project.icon} fallback={FolderKanbanIcon} />
			</IconTile>
			<div class="min-w-0">
				{#if eyebrow}<p class="text-xs font-medium tracking-wide text-muted-foreground uppercase">{eyebrow}</p>{/if}
				<h2 class="text-3xl leading-tight font-semibold tracking-tight">{title}</h2>
				{#if lead}<p class="mt-1 text-sm">{lead}</p>{/if}
				{#if detail}<p class="mt-1 text-sm whitespace-pre-line text-muted-foreground">{detail}</p>{/if}
				{#if children}<div class="mt-3">{@render children()}</div>{/if}
			</div>
		</div>
	</SectionBanner>
</header>
