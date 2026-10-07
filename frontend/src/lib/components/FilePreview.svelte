<script lang="ts">
	import { api, ApiError, type FileEntry } from '$lib/api'
	import ImagePreview from '$lib/components/ImagePreview.svelte'
	import { Button } from '$lib/components/ui/button/index.js'
	import { isDirty, isMarkdown, parentPath, previewKind, resolveRelative, type Draft } from '$lib/files'
	import { onCodeCopyClick, renderMarkdown } from '$lib/markdown'
	import DownloadIcon from '@lucide/svelte/icons/download'
	import LoaderCircleIcon from '@lucide/svelte/icons/loader-circle'
	import LockKeyholeIcon from '@lucide/svelte/icons/lock-keyhole'
	import PencilIcon from '@lucide/svelte/icons/pencil'
	import { fade } from 'svelte/transition'

	// What a file looks like inside Themis: a picture, text (markdown as rich text, with a switch to the raw text, and an
	// editor for quick changes), with a spinner while it loads, or a download for the rest. The parent keys it by file, so
	// every new file starts clean and fades in. It fills the nearest positioned ancestor (absolute, not a percentage height):
	// that stays correct however the panel around it is sized or dragged.
	//
	// The unsaved edit (`draft`) belongs to the page, not to this component: the same file can be open in the side panel
	// and in the enlarged view, and either can be closed without losing it. Saving and leaving are the page's too, because
	// it also has to guard every other way of moving away from an edit.
	let {
		volumeId,
		path,
		entry,
		canEdit = false,
		locked = false,
		draft = $bindable(null),
		onsave,
		onleave,
	}: {
		volumeId: number
		path: string
		entry: FileEntry
		canEdit?: boolean
		locked?: boolean // the folder is writable but runs are using it, so editing waits
		draft?: Draft | null
		// throws a readable error when the file cannot be saved; unless `force`, a file that changed since the edit began
		// is refused with a 412
		onsave?: (force: boolean) => Promise<void>
		onleave?: () => void // asks to stop editing (the page checks for unsaved changes first)
	} = $props()

	const kind = $derived(previewKind(entry.name, entry.size))
	const markdown = $derived(isMarkdown(entry.name))
	let text = $state('')
	let error = $state('')
	let loading = $state(true)
	let raw = $state(false) // markdown shown as written instead of as rich text
	let saving = $state(false)
	let saveError = $state('')
	let conflict = $state(false) // the file changed on disk while it was being edited

	const editing = $derived(draft?.path === path)
	const dirty = $derived(editing && isDirty(draft))

	// Rich text from a file an agent wrote: raw HTML is shown as text and links and pictures are restricted (see
	// markdown.ts), which is what makes it safe to insert as HTML. A picture next to the file is loaded from its folder.
	const rich = $derived(
		kind === 'text' && markdown && !loading && !error
			? renderMarkdown(text, {
					untrusted: true,
					image: (src) => {
						const target = resolveRelative(parentPath(path), src)
						return target === null ? null : api.fileUrl(volumeId, target)
					},
				}).html
			: ''
	)

	$effect(() => {
		if (kind === null) {
			loading = false
			return
		}
		if (kind === 'image') return // the picture reports when it has loaded
		// The text is read again whenever the file changes on disk (an agent is working on it), without the spinner. Never
		// while it is being edited: the editor holds the person's version, and it is read again once they are done.
		void entry.modified
		if (editing) return
		let stale = false
		api
			.readFileText(volumeId, path)
			.then((t) => !stale && (text = t))
			.catch((e) => !stale && (error = e instanceof ApiError || e instanceof Error ? e.message : 'Could not read the file'))
			.finally(() => !stale && (loading = false))
		return () => (stale = true)
	})

	function edit() {
		saveError = ''
		conflict = false
		draft = { path, entry, original: text, text }
	}

	async function save(force = false) {
		if (!onsave || saving || !dirty) return
		saving = true
		saveError = ''
		conflict = false
		try {
			await onsave(force)
		} catch (e) {
			conflict = e instanceof ApiError && e.status === 412
			saveError = e instanceof Error ? e.message : 'Could not save the file'
		} finally {
			saving = false
		}
	}

	function onEditorKeydown(e: KeyboardEvent) {
		if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 's') {
			e.preventDefault()
			save()
		}
	}
</script>

<div class="absolute inset-0 flex min-h-0 flex-col" in:fade={{ duration: 250 }}>
	{#if kind === 'image'}
		<ImagePreview {volumeId} {path} {entry} {loading} onload={() => (loading = false)} onerror={() => ((error = 'Could not load the image'), (loading = false))} />
	{:else if kind === 'text' && !loading && !error}
		<div class="mb-2 flex shrink-0 flex-wrap items-center gap-2">
			{#if markdown && !editing}
				<div class="inline-flex rounded-md border p-0.5" role="group" aria-label="How to show the file">
					<Button variant={raw ? 'ghost' : 'secondary'} size="sm" class="h-6 px-2 text-xs" aria-pressed={!raw} onclick={() => (raw = false)}>Rendered</Button>
					<Button variant={raw ? 'secondary' : 'ghost'} size="sm" class="h-6 px-2 text-xs" aria-pressed={raw} onclick={() => (raw = true)}>Raw</Button>
				</div>
			{/if}
			<div class="ms-auto flex items-center gap-2" transition:fade={{ duration: 150 }}>
				{#if editing}
					{#if saveError}<span class="text-xs text-destructive" role="alert">{saveError}</span>
					{:else if dirty}<span class="text-xs text-yellow-300">Unsaved changes</span>{/if}
					<Button variant="ghost" size="sm" class="h-7" disabled={saving} onclick={() => onleave?.()}>Cancel</Button>
					{#if conflict}
						<Button variant="outline" size="sm" class="h-7" disabled={saving} onclick={() => save(true)}>Save anyway</Button>
					{:else}
						<Button size="sm" class="h-7" disabled={!dirty || saving} onclick={() => save()}>{saving ? 'Saving...' : 'Save'}</Button>
					{/if}
				{:else if canEdit}
					<Button variant="outline" size="sm" class="h-7" onclick={edit}><PencilIcon /> Edit</Button>
				{:else if locked}
					<span class="flex items-center gap-1.5 text-xs text-muted-foreground" title="A run is using this folder, so it cannot be edited right now">
						<LockKeyholeIcon class="size-3.5" /> In use
					</span>
				{/if}
			</div>
		</div>

		{#if editing && draft}
			<textarea
				bind:value={draft.text}
				onkeydown={onEditorKeydown}
				spellcheck="false"
				aria-label="Edit {entry.name}"
				class="slim-scrollbar min-h-0 flex-1 resize-none rounded-md border bg-background/40 p-3 font-mono text-xs outline-none focus-visible:border-primary/60"
			></textarea>
		{:else if markdown && !raw}
			<!-- trusted: renderMarkdown ran in untrusted mode, so nothing in the file can be markup of its own -->
			<!-- svelte-ignore a11y_click_events_have_key_events, a11y_no_static_element_interactions -->
			<div class="docs-prose prose prose-invert slim-scrollbar max-w-none min-h-0 flex-1 overflow-auto rounded-md border bg-background/40 p-4 text-sm" onclick={onCodeCopyClick}>
				{@html rich}
			</div>
		{:else}
			<pre class="slim-scrollbar min-h-0 flex-1 overflow-auto rounded-md border bg-background/40 p-3 text-xs whitespace-pre-wrap">{text}</pre>
		{/if}
	{:else if kind === null}
		<div class="m-auto flex flex-col items-center gap-3 text-center">
			<p class="text-sm text-muted-foreground">This kind of file cannot be shown here.</p>
			<Button variant="outline" href={api.fileUrl(volumeId, path, true)} download={entry.name}><DownloadIcon /> Download</Button>
		</div>
	{/if}

	{#if error}
		<p class="m-auto text-sm text-destructive" role="alert">{error}</p>
	{/if}

	{#if loading}
		<div class="absolute inset-0 flex flex-col items-center justify-center gap-3 text-sm text-muted-foreground" out:fade={{ duration: 200 }} role="status">
			<LoaderCircleIcon class="size-6 animate-spin text-primary" />
			<span>Themis is loading your file...</span>
		</div>
	{/if}
</div>
