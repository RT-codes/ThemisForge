<script lang="ts">
	import { api, ApiError, type FileEntry, type FolderListing, type Volume } from '$lib/api'
	import FilePreview from '$lib/components/FilePreview.svelte'
	import * as AlertDialog from '$lib/components/ui/alert-dialog/index.js'
	import { Button } from '$lib/components/ui/button/index.js'
	import * as Dialog from '$lib/components/ui/dialog/index.js'
	import * as DropdownMenu from '$lib/components/ui/dropdown-menu/index.js'
	import { Input } from '$lib/components/ui/input/index.js'
	import VolumeControls from '$lib/components/VolumeControls.svelte'
	import VolumeForm from '$lib/components/VolumeForm.svelte'
	import {
		FILE_SORTS,
		FILE_TYPES,
		arrange,
		crumbs,
		emptyFileView,
		formatSize,
		isDefaultFileView,
		isDirty,
		isValidFolderName,
		isValidName,
		joinPath,
		type Draft,
		type FileSort,
		type FileType,
	} from '$lib/files'
	import { dateTime, relative } from '$lib/format'
	import { pulseWhen } from '$lib/pulse'
	import { router } from '$lib/router.svelte'
	import { cn } from '$lib/utils'
	import ArrowUpDownIcon from '@lucide/svelte/icons/arrow-up-down'
	import ChevronLeftIcon from '@lucide/svelte/icons/chevron-left'
	import ChevronRightIcon from '@lucide/svelte/icons/chevron-right'
	import DownloadIcon from '@lucide/svelte/icons/download'
	import FileIcon from '@lucide/svelte/icons/file'
	import FolderCogIcon from '@lucide/svelte/icons/folder-cog'
	import FolderIcon from '@lucide/svelte/icons/folder'
	import FolderOpenIcon from '@lucide/svelte/icons/folder-open'
	import FolderPlusIcon from '@lucide/svelte/icons/folder-plus'
	import HardDriveIcon from '@lucide/svelte/icons/hard-drive'
	import LoaderCircleIcon from '@lucide/svelte/icons/loader-circle'
	import LockKeyholeIcon from '@lucide/svelte/icons/lock-keyhole'
	import ListFilterIcon from '@lucide/svelte/icons/list-filter'
	import Maximize2Icon from '@lucide/svelte/icons/maximize-2'
	import PencilIcon from '@lucide/svelte/icons/pencil'
	import PlusIcon from '@lucide/svelte/icons/plus'
	import SettingsIcon from '@lucide/svelte/icons/settings'
	import SearchIcon from '@lucide/svelte/icons/search'
	import Trash2Icon from '@lucide/svelte/icons/trash-2'
	import UploadIcon from '@lucide/svelte/icons/upload'
	import XIcon from '@lucide/svelte/icons/x'
	import { onMount, untrack } from 'svelte'
	import { fade, slide } from 'svelte/transition'

	// The files inside a project's folders: `shared` (in every cell) and any custom folders. This is where agents leave
	// what they deliver, so it can also be managed from here. Private attempt workspaces are deliberately not shown.
	let { id }: { id: number } = $props()

	let volumes = $state<Volume[]>([])
	let volumeId = $state<number | null>(null)
	let loaded = $state(false)
	let error = $state('')
	let notice = $state('')

	// ----- the tree: each folder is listed when it is first opened, and kept fresh while it stays open -----

	let tree = $state<Record<string, FolderListing>>({}) // folder path ("" is the root) -> what is in it
	let expanded = $state<string[]>([])
	let current = $state('') // the folder new files and folders go into: the last one clicked

	const volume = $derived(volumes.find((v) => v.id === volumeId) ?? null)
	const root = $derived(tree[''])
	const pieces = $derived(crumbs(current))
	// A folder that runs are using is locked: browsing and downloading stay open, every change waits. An upload, edit,
	// move or delete from here could break what an agent is in the middle of (the server refuses them too).
	const locked = $derived((root?.runs.length ?? 0) > 0)
	const lockedBy = $derived((root?.runs ?? []).map((r) => `task ${r.task_id} (${r.title})`).join(', '))
	// what a person may do here: the folder allows it, and no run is using it
	const canChange = $derived(!!root?.writable && !locked)

	const message = (e: unknown, fallback: string) => (e instanceof ApiError || e instanceof Error ? e.message : fallback)
	const isInside = (path: string, folder: string) => path === folder || path.startsWith(`${folder}/`)

	// The ETag of the listing held for each folder: asking again with it costs a bodyless 304 when nothing changed.
	// Plain, not reactive: nothing on screen depends on it.
	let etags: Record<string, string> = {}

	// Files that appear or change while their folder is open pulse in the tree (the pulse of the sidebar links), and so
	// does the preview of the open file. Counters, not flags: every new change plays the pulse again from the start.
	let pulses = $state<Record<string, number>>({}) // path -> times it changed
	let previewPulses = $state(0)

	function notePulses(dir: string, before: FolderListing | undefined, after: FolderListing) {
		if (!before) return // the first time a folder is listed, everything in it is not "new"
		const old = new Map(before.entries.map((e) => [e.name, e]))
		for (const e of after.entries) {
			const was = old.get(e.name)
			const changed = !was || (!e.is_dir && (was.size !== e.size || was.modified !== e.modified))
			if (changed) pulses[joinPath(dir, e.name)] = (pulses[joinPath(dir, e.name)] ?? 0) + 1
		}
	}

	/** lists one folder again; true if what is on screen changed */
	async function loadFolder(vid: number, dir: string): Promise<boolean> {
		try {
			const got = await api.listFiles(vid, dir, etags[dir] ?? '')
			if (vid !== volumeId || got === null) return false // another folder was chosen meanwhile, or no change
			etags[dir] = got.etag
			notePulses(dir, tree[dir], got.listing)
			tree[dir] = got.listing
			if (dir === '') error = ''
			return true
		} catch (e) {
			if (vid !== volumeId) return false
			delete etags[dir]
			if (dir === '') {
				tree = {}
				error = message(e, 'Could not load the folder')
				return false // a broken folder is not "something changing": no need to ask faster
			}
			// gone (deleted, renamed, or by a run): close it along with anything open inside it
			expanded = expanded.filter((x) => !isInside(x, dir))
			delete tree[dir]
			if (isInside(current, dir)) current = ''
			return true
		}
	}

	/** lists the root and every open folder again; true if anything changed */
	async function refresh(): Promise<boolean> {
		const vid = volumeId
		if (vid === null) return false
		const changed = await Promise.all(['', ...expanded].map((dir) => loadFolder(vid, dir)))
		return changed.some(Boolean)
	}

	// Watching the open folders: often while a run is using them or something changed lately (files appear as the
	// agent works), rarely when everything is quiet. Each check is a conditional request, so quiet is nearly free.
	// (A file watcher would need the server to hold a watch per open folder, which host folders with huge trees make
	// expensive, and would not see more than this does for the few folders that are open.)
	const ACTIVE_MS = 1500
	const QUIET_MS = 5000
	const RECENT_MS = 30_000
	let lastChange = 0

	onMount(() => {
		let timer: ReturnType<typeof setTimeout> | undefined
		let stopped = false
		const delay = () => (locked || Date.now() - lastChange < RECENT_MS ? ACTIVE_MS : QUIET_MS)
		async function watch() {
			clearTimeout(timer)
			if (!document.hidden && !busyAction && volumeId !== null && (await refresh())) lastChange = Date.now()
			if (!stopped) timer = setTimeout(watch, delay())
		}
		// coming back to the tab checks right away instead of waiting for the next turn
		const onVisible = () => !document.hidden && watch()
		document.addEventListener('visibilitychange', onVisible)

		api
			.volumes(id)
			.then((v) => {
				volumes = v
				volumeId = v[0]?.id ?? null // `shared` always comes first
				return refresh()
			})
			.then(openLinked)
			.catch((e) => (error = message(e, 'Could not load the folders')))
			.finally(() => {
				loaded = true
				if (!stopped) timer = setTimeout(watch, delay())
			})
		return () => {
			stopped = true
			clearTimeout(timer)
			document.removeEventListener('visibilitychange', onVisible)
		}
	})

	// ----- the folders themselves: new ones, and the settings of the chosen one -----

	let creating = $state(false)
	let configuring = $state(false)

	async function reloadVolumes() {
		try {
			volumes = await api.volumes(id, true)
		} catch (e) {
			error = message(e, 'Could not load the folders')
		}
	}

	async function added(v: Volume) {
		creating = false
		await reloadVolumes()
		open(volumes.find((x) => x.id === v.id) ?? v)
	}

	// the name field of the settings panel; it starts from the folder's current name each time the panel opens
	let newName = $state('')
	let renameError = $state('')
	let renaming = $state(false)
	$effect(() => {
		if (configuring) untrack(() => ((newName = volume?.name ?? ''), (renameError = ''))) // only when it opens
	})
	const renamable = $derived(!!volume && !volume.is_default)
	const nameChanged = $derived(!!volume && newName.trim().toLowerCase() !== volume.name)

	async function rename(e: SubmitEvent) {
		e.preventDefault()
		if (volumeId === null || !isValidFolderName(newName)) return
		renaming = true
		renameError = ''
		try {
			await api.updateVolume(volumeId, { name: newName })
			await Promise.all([reloadVolumes(), refresh()])
		} catch (err) {
			renameError = message(err, 'Could not rename the folder')
		} finally {
			renaming = false
		}
	}

	async function changeSettings(patch: { mode?: 'ro' | 'rw'; exclusive_write?: boolean }) {
		if (volumeId === null) return
		try {
			await api.updateVolume(volumeId, patch)
			error = ''
		} catch (e) {
			error = message(e, 'Could not change the folder')
		}
		await Promise.all([reloadVolumes(), refresh()]) // what is allowed here changed
	}

	const open = (v: Volume) => guarded(() => show(v))

	// "config" is how the config folder is shown: its stored name is not one a person could give a folder
	const label = (v: Volume) => (v.kind === 'config' ? 'config' : v.name)

	// A link from the agent pages, /files#config/agents/scout/agent.md, opens that file in the config folder
	async function openLinked() {
		const m = router.hash.match(/^config(?:\/(.+))?$/)
		const config = volumes.find((v) => v.kind === 'config')
		if (!m || !config) return
		show(config)
		await refresh()
		const parts = (m[1] ?? '').split('/').filter(Boolean)
		for (let i = 1; i <= parts.length; i++) {
			const dir = parts.slice(0, i).join('/')
			const entry = tree[parts.slice(0, i - 1).join('/')]?.entries.find((e) => e.name === parts[i - 1])
			if (!entry) return
			if (entry.is_dir) {
				expanded = [...expanded, dir]
				current = dir
				await loadFolder(config.id, dir)
			} else selectedPath = dir
		}
	}

	function show(v: Volume) {
		volumeId = v.id
		tree = {}
		etags = {}
		pulses = {}
		expanded = []
		current = selectedPath = ''
		notice = ''
		refresh()
	}

	async function toggle(dir: string) {
		current = dir
		if (expanded.includes(dir)) {
			// closing a folder hides the file that is open (and being edited) inside it
			const close = () => {
				expanded = expanded.filter((x) => !isInside(x, dir))
				// forgotten, so opening it again is a fresh listing and not a pile of "changes" since it was closed
				for (const key of Object.keys(tree)) {
					if (key === '' || !isInside(key, dir)) continue
					delete tree[key]
					delete etags[key]
				}
			}
			if (selectedPath && isInside(selectedPath, dir)) guarded(close)
			else close()
			return
		}
		expanded = [...expanded, dir]
		await loadFolder(volumeId!, dir)
	}

	// ----- search, order and type -----

	// the order and filters are one setting for the page; the gallery follows the same files that are on screen
	let view = $state(emptyFileView())

	/** the files on screen from top to bottom: open folders are walked in place, closed ones hold nothing visible */
	function flatten(dir: string): { path: string; entry: FileEntry }[] {
		return arrange(tree[dir]?.entries ?? [], view).flatMap((entry) => {
			const path = joinPath(dir, entry.name)
			if (!entry.is_dir) return [{ path, entry }]
			return expanded.includes(path) ? flatten(path) : []
		})
	}

	// ----- selection: the chosen file is previewed beside the tree, and can be enlarged into a gallery -----

	// the unsaved edit of a text file, if any (see "editing a text file" below): the open file stays open while it exists
	let draft = $state<Draft | null>(null)
	const dirty = $derived(isDirty(draft))
	let selectedPath = $state('')
	let enlarged = $state(false)
	// found again by path after every refresh, so a file that was renamed, deleted or filtered out stops being selected
	const files = $derived(flatten(''))
	const selectedIndex = $derived(files.findIndex((f) => f.path === selectedPath))
	// a file being edited stays open even if the search or filter now hides its row: the edit must not vanish on its own
	const selected = $derived(selectedIndex >= 0 ? files[selectedIndex].entry : dirty && draft ? draft.entry : null)

	// an agent may delete the file while it is enlarged
	$effect(() => {
		if (!selected) enlarged = false
	})

	// the preview pulses when the file it shows changes on disk (not when another file is chosen)
	let shown = { path: '', modified: '' }
	$effect(() => {
		const next = { path: selectedPath, modified: selected?.modified ?? '' }
		untrack(() => {
			if (next.modified && next.path === shown.path && shown.modified && next.modified !== shown.modified) previewPulses += 1
			shown = next
		})
	})

	function step(by: number) {
		const next = selectedIndex < 0 ? undefined : files[selectedIndex + by]
		if (next) guarded(() => (selectedPath = next.path))
	}

	const pick = (path: string) => path !== selectedPath && guarded(() => (selectedPath = path))
	const close = () => guarded(() => (selectedPath = ''))

	function onkeydown(e: KeyboardEvent) {
		if (!enlarged || e.target instanceof HTMLInputElement) return
		if (e.key === 'ArrowLeft') step(-1)
		else if (e.key === 'ArrowRight') step(1)
	}

	// ----- the divider between the tree and the preview: drag it, or use the arrow keys, to give one more room -----

	const PANE_MIN = 25 // percent of the width the preview may take
	const PANE_MAX = 75
	const PANE_KEY = 'themis.files.pane'
	const clampPane = (percent: number) => Math.min(PANE_MAX, Math.max(PANE_MIN, percent))

	let split = $state<HTMLElement>()
	let dragging = $state(false)
	let paneWidth = $state(45)
	try {
		paneWidth = clampPane(Number(localStorage.getItem(PANE_KEY)) || 45) // remembered on this device only
	} catch {
		// storage can be unavailable (private windows); the default is fine
	}

	function drag(e: PointerEvent) {
		if (!dragging || !split) return
		const box = split.getBoundingClientRect()
		paneWidth = clampPane(((box.right - e.clientX) / box.width) * 100)
	}

	function savePane() {
		try {
			localStorage.setItem(PANE_KEY, String(Math.round(paneWidth)))
		} catch {
			// not remembered, that is all
		}
	}

	function endDrag() {
		dragging = false
		savePane()
	}

	function nudgePane(e: KeyboardEvent) {
		if (e.key !== 'ArrowLeft' && e.key !== 'ArrowRight') return
		e.preventDefault()
		paneWidth = clampPane(paneWidth + (e.key === 'ArrowLeft' ? 3 : -3)) // the handle moves the way the arrow points
		savePane()
	}

	// ----- editing a text file: one draft at a time, and nothing that would lose it goes through unasked -----

	let saves = $state(0) // counts saves, so the preview is loaded again and shows what was written
	// something the person wanted to do that would throw the edit away, waiting for their answer
	let pending = $state<(() => void) | null>(null)
	let pendingError = $state('')
	let pendingBusy = $state(false)

	/** runs `action` now, or after the person has decided what to do with their unsaved changes */
	function guarded(action: () => void) {
		if (dirty) {
			pendingError = ''
			pending = action
			return
		}
		draft = null // an edit with nothing changed just ends
		action()
	}

	/** writes the draft; unless `force`, it is refused (412) if the file changed on disk since the edit began */
	async function saveDraft(force = false) {
		const d = draft
		if (!d || volumeId === null) return
		await api.uploadFile(volumeId, d.path, new File([d.text], d.entry.name), true, force ? '' : d.entry.modified)
		draft = null
		saves += 1
		await refresh() // the size and time of the file changed
	}

	async function saveAndGo() {
		const go = pending
		pendingBusy = true
		pendingError = ''
		try {
			await saveDraft()
			pending = null
			go?.()
		} catch (e) {
			pendingError = message(e, 'Could not save the file')
		} finally {
			pendingBusy = false
		}
	}

	function discardAndGo() {
		const go = pending
		draft = null
		pending = null
		go?.()
	}

	// moving to another page of the app, or closing the tab, is held while there are unsaved changes
	$effect(() => {
		router.guard = (go) => {
			if (!dirty) return false
			guarded(go)
			return true
		}
		return () => (router.guard = null)
	})

	// ----- changes -----

	let busyAction = $state(false)
	async function act(work: () => Promise<void>, fallback: string) {
		busyAction = true
		error = notice = ''
		try {
			await work()
		} catch (e) {
			error = message(e, fallback)
		} finally {
			busyAction = false
			await refresh()
		}
	}

	let picker = $state<HTMLInputElement>()
	async function upload(files: FileList | null) {
		if (!files?.length || volumeId === null) return
		const vid = volumeId
		const dir = current
		const skipped: string[] = []
		await act(async () => {
			for (const file of files) {
				try {
					await api.uploadFile(vid, joinPath(dir, file.name), file)
				} catch (e) {
					if (e instanceof ApiError && e.status === 409 && !e.message.includes('writing')) skipped.push(file.name)
					else throw e
				}
			}
			if (skipped.length) notice = `Not uploaded, a file with that name already exists: ${skipped.join(', ')}`
		}, 'Could not upload')
		if (picker) picker.value = ''
	}

	// one small dialog serves both "new folder" and "rename"
	let naming = $state<{ kind: 'folder' } | { kind: 'rename'; path: string; entry: FileEntry } | null>(null)
	let nameInput = $state('')
	function askName(target: typeof naming) {
		naming = target
		nameInput = target?.kind === 'rename' ? target.entry.name : ''
	}
	async function submitName(e: SubmitEvent) {
		e.preventDefault()
		const target = naming
		const name = nameInput.trim()
		if (!target || volumeId === null || !isValidName(name)) return
		const vid = volumeId
		const dir = current
		naming = null
		await act(async () => {
			if (target.kind === 'folder') {
				await api.createFolder(vid, joinPath(dir, name))
				if (dir !== '' && !expanded.includes(dir)) expanded = [...expanded, dir] // so the new folder is seen
				return
			}
			const parent = target.path.split('/').slice(0, -1).join('/')
			await api.moveFile(vid, target.path, joinPath(parent, name))
			if (isInside(current, target.path)) current = ''
		}, 'Could not save the change')
	}

	// renaming or deleting what is being edited counts as leaving the edit
	const touchesDraft = (path: string) => draft !== null && isInside(draft.path, path)

	let doomed = $state<{ path: string; entry: FileEntry } | null>(null)
	async function remove() {
		const target = doomed
		doomed = null
		if (!target || volumeId === null) return
		const vid = volumeId
		await act(async () => {
			await api.deleteFile(vid, target.path)
			if (isInside(current, target.path)) current = ''
		}, 'Could not delete')
	}
</script>

<!-- One level of the tree. A folder row opens in place; what is inside hangs off it by a branch line. -->
{#snippet level(dir: string)}
	{#each arrange(tree[dir]?.entries ?? [], view) as entry (entry.name)}
		{@const path = joinPath(dir, entry.name)}
		{@const isOpen = entry.is_dir && expanded.includes(path)}
		<li class="file-leaf">
			<div use:pulseWhen={pulses[path] ?? 0} class="group flex h-8 items-center gap-2 overflow-hidden rounded-md px-2 transition-colors hover:bg-accent/40 {path === selectedPath ? 'bg-accent/60' : ''}">
				<button class="flex min-w-0 flex-1 items-center gap-2 text-start" aria-expanded={entry.is_dir ? isOpen : undefined} onclick={() => (entry.is_dir ? toggle(path) : pick(path))}>
					{#if entry.is_dir}
						<ChevronRightIcon class="size-4 shrink-0 text-muted-foreground transition-transform duration-200 {isOpen ? 'rotate-90' : ''}" />
						{#if isOpen}<FolderOpenIcon class="size-4 shrink-0 text-primary" />{:else}<FolderIcon class="size-4 shrink-0 text-primary" />{/if}
					{:else}
						<FileIcon class="size-4 shrink-0 text-muted-foreground" />
					{/if}
					<span class={cn('truncate text-sm', entry.is_dir && path === current && 'text-primary')}>{entry.name}</span>
				</button>
				<span class="hidden w-20 text-end text-xs text-muted-foreground sm:block">{entry.is_dir ? '' : formatSize(entry.size)}</span>
				<span class="hidden w-28 text-end text-xs text-muted-foreground sm:block" title={dateTime(entry.modified)}>{relative(entry.modified)}</span>
				<span class="flex shrink-0 items-center">
					{#if !entry.is_dir}
						<Button variant="ghost" size="icon-sm" aria-label="Download {entry.name}" class="text-muted-foreground" href={api.fileUrl(volumeId!, path, true)} download={entry.name}>
							<DownloadIcon />
						</Button>
					{/if}
					<!-- changes are only offered where the folder allows them; while runs use it, a lock stands in their place -->
					{#if root?.writable && locked}
						<span class="flex h-7 items-center gap-1 px-2 text-muted-foreground" title="In use by {lockedBy}: it cannot be changed right now">
							<LockKeyholeIcon class="size-3.5" /><LoaderCircleIcon class="size-3 animate-spin" />
						</span>
					{:else if root?.writable}
						<Button variant="ghost" size="icon-sm" aria-label="Rename {entry.name}" class="text-muted-foreground" disabled={!canChange || busyAction} onclick={() => (touchesDraft(path) ? guarded(() => askName({ kind: 'rename', path, entry })) : askName({ kind: 'rename', path, entry }))}>
							<PencilIcon />
						</Button>
						<Button variant="ghost" size="icon-sm" aria-label="Delete {entry.name}" class="text-muted-foreground hover:text-destructive" disabled={!canChange || busyAction} onclick={() => (touchesDraft(path) ? guarded(() => (doomed = { path, entry })) : (doomed = { path, entry }))}>
							<Trash2Icon />
						</Button>
					{/if}
				</span>
			</div>
			{#if isOpen}
				<!-- the lines are drawn 0.625rem left of each row: 1.625rem of margin puts them under the folder's chevron -->
				<ul class="ms-[1.625rem] space-y-0.5 pt-0.5" transition:slide={{ duration: 160 }}>
					{#if !tree[path]}
						<li class="file-leaf"><p class="flex h-8 items-center px-2 text-xs text-muted-foreground">Loading...</p></li>
					{:else if tree[path].entries.length === 0}
						<li class="file-leaf"><p class="flex h-8 items-center px-2 text-xs text-muted-foreground">Empty</p></li>
					{:else}
						{@render level(path)}
					{/if}
				</ul>
			{/if}
		</li>
	{/each}
{/snippet}

<!-- Side by side the page is exactly as tall as the window below the top bar (3.5rem), so the tree scrolls inside its
     card and the preview is as tall as the screen. Without a limit both would grow with a long folder, and a picture
     centred in the preview would end up far below the fold. Stacked on a narrow screen it just scrolls as a page. -->
<div class="flex min-h-0 flex-1 flex-col px-6 pt-8 pb-6 lg:h-[calc(100svh-3.5rem)] lg:flex-none">
	<h2 class="text-2xl font-semibold tracking-tight">Files</h2>
	<p class="text-sm text-muted-foreground">
		What agents leave in this project's folders. <span class="font-mono">shared</span> is in every cell; the others are mounted by the agents that ask for them. <span class="font-mono">config</span> holds the agents, skills and tools themselves.
	</p>

	{#if !loaded}
		<p class="mt-6 text-sm text-muted-foreground">Loading...</p>
	{:else if !volume}
		<p class="mt-6 text-sm text-destructive" role="alert">{error || 'This project has no folders'}</p>
	{:else}
		<div class="mt-5 flex flex-wrap items-center gap-2" role="tablist" aria-label="Folders">
			{#each volumes as v (v.id)}
				<div class="flex items-center">
					<Button
						variant={v.id === volumeId ? 'secondary' : 'ghost'}
						size="sm"
						role="tab"
						aria-selected={v.id === volumeId}
						class={v.id === volumeId ? 'rounded-e-none' : ''}
						onclick={() => open(v)}
					>
						{#if v.kind === 'host'}<HardDriveIcon />{:else if v.kind === 'config'}<FolderCogIcon />{:else}<FolderIcon />{/if}
						<span class="font-mono">{label(v)}</span>
						{#if v.id === volumeId && locked}<LockKeyholeIcon class="size-3.5 text-muted-foreground" />{/if}
						{#if v.mode === 'ro' || (v.kind === 'host' && !v.can_write)}<span class="text-xs text-muted-foreground">read only</span>{/if}
					</Button>
					{#if v.id === volumeId && v.kind !== 'config'}
						<Button variant="secondary" size="icon-sm" class="h-8 rounded-s-none text-muted-foreground hover:text-foreground" aria-label="Settings of {v.name}" title="Folder settings" onclick={() => (configuring = true)}>
							<SettingsIcon />
						</Button>
					{/if}
				</div>
			{/each}
			<Button variant="outline" size="sm" onclick={() => (creating = true)}><PlusIcon /> New shared folder</Button>
		</div>

		<div bind:this={split} class="mt-4 flex min-h-0 flex-1 flex-col gap-4 lg:flex-row lg:gap-0">
			<div class="flex max-h-[70svh] min-h-0 min-w-0 flex-1 flex-col rounded-xl border bg-card lg:max-h-none">
				{#if root?.writable}
					<div class="flex flex-wrap items-center gap-2 border-b px-4 py-2.5">
						<span class="text-xs text-muted-foreground">New items go in</span>
						<nav aria-label="Folder for new items" class="flex min-w-0 flex-1 flex-wrap items-center gap-1 font-mono text-sm">
							<button class="rounded px-1 hover:bg-accent" onclick={() => (current = '')}>{label(volume)}</button>
							{#each pieces as piece (piece.path)}
								<span class="text-muted-foreground/60">/</span>
								<button class="rounded px-1 hover:bg-accent" onclick={() => (current = piece.path)}>{piece.name}</button>
							{/each}
						</nav>
						<input bind:this={picker} type="file" multiple class="hidden" onchange={(e) => upload(e.currentTarget.files)} />
						<Button size="sm" variant="outline" disabled={!canChange || busyAction} onclick={() => askName({ kind: 'folder' })}><FolderPlusIcon /> New folder</Button>
						<Button size="sm" disabled={!canChange || busyAction} onclick={() => picker?.click()}><UploadIcon /> Upload</Button>
					</div>
				{/if}

				<div class="flex flex-wrap items-center gap-2 border-b px-4 py-2">
					<div class="relative">
						<SearchIcon class="pointer-events-none absolute start-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
						<Input bind:value={view.search} placeholder="Search files" aria-label="Search files" class="h-8 w-48 ps-8 pe-8" />
						{#if view.search}
							<button type="button" aria-label="Clear the search" class="absolute end-1.5 top-1/2 flex size-5 -translate-y-1/2 items-center justify-center rounded text-muted-foreground transition-colors hover:text-foreground" onclick={() => (view.search = '')}>
								<XIcon class="size-3.5" />
							</button>
						{/if}
					</div>
					<DropdownMenu.Root>
						<DropdownMenu.Trigger>
							{#snippet child({ props })}
								<Button {...props} variant="outline" size="sm" class={cn('h-8 gap-1.5', view.sort !== 'name' && 'border-primary/50 text-primary')} aria-label="Order the files">
									<ArrowUpDownIcon />
									{FILE_SORTS.find((x) => x.id === view.sort)?.label}
								</Button>
							{/snippet}
						</DropdownMenu.Trigger>
						<DropdownMenu.Content align="start" class="w-48">
							<DropdownMenu.RadioGroup value={view.sort} onValueChange={(v) => (view.sort = v as FileSort)}>
								{#each FILE_SORTS as x (x.id)}<DropdownMenu.RadioItem value={x.id} closeOnSelect>{x.label}</DropdownMenu.RadioItem>{/each}
							</DropdownMenu.RadioGroup>
						</DropdownMenu.Content>
					</DropdownMenu.Root>
					<DropdownMenu.Root>
						<DropdownMenu.Trigger>
							{#snippet child({ props })}
								<Button {...props} variant="outline" size="sm" class={cn('h-8 gap-1.5', view.type !== 'all' && 'border-primary/50 text-primary')} aria-label="Filter by type">
									<ListFilterIcon />
									{FILE_TYPES.find((x) => x.id === view.type)?.label}
								</Button>
							{/snippet}
						</DropdownMenu.Trigger>
						<DropdownMenu.Content align="start" class="w-52">
							<DropdownMenu.RadioGroup value={view.type} onValueChange={(v) => (view.type = v as FileType)}>
								{#each FILE_TYPES as x (x.id)}<DropdownMenu.RadioItem value={x.id} closeOnSelect>{x.label}</DropdownMenu.RadioItem>{/each}
							</DropdownMenu.RadioGroup>
						</DropdownMenu.Content>
					</DropdownMenu.Root>
					{#if !isDefaultFileView(view)}
						<Button variant="ghost" size="sm" class="h-8 text-muted-foreground" onclick={() => (view = emptyFileView())}>Reset</Button>
					{/if}
				</div>

				{#if volume.problem}
					<p class="px-4 pt-3 text-sm text-destructive" role="alert">{volume.problem}</p>
				{:else if locked && root}
					<p class="mx-4 mt-3 flex items-center gap-2 rounded-md border border-primary/30 bg-primary/10 px-3 py-2 text-sm text-primary" role="status">
						<LockKeyholeIcon class="size-4 shrink-0" />
						<LoaderCircleIcon class="size-3.5 shrink-0 animate-spin" />
						<span>In use by {lockedBy}. You can look and download, but changes wait until it finishes.</span>
					</p>
				{:else if root && !root.writable}
					<p class="px-4 pt-3 text-xs text-muted-foreground">This folder is read only. You can browse and download, not change.</p>
				{/if}
				{#if volume.kind === 'config'}
					<p class="mx-4 mt-3 rounded-md border bg-muted/40 px-3 py-2 text-xs text-muted-foreground">
						Where this project's agents, skills and tools are kept. A file here is checked before it is saved, and agents never see this folder.
					</p>
				{/if}
				{#if error}<p class="px-4 pt-3 text-sm text-destructive" role="alert">{error}</p>{/if}
				{#if notice}<p class="px-4 pt-3 text-sm text-yellow-300">{notice}</p>{/if}

				<div class="slim-scrollbar min-h-0 flex-1 overflow-y-auto p-2">
					{#if root && root.entries.length === 0}
						<p class="px-4 py-10 text-center text-sm text-muted-foreground">Nothing here yet.</p>
					{:else if root}
						<!-- the folder itself is the top of the tree, so files at its root hang off a line too; with no chevron,
						     its icon sits where a chevron would, which is exactly where the branch line runs -->

						<button class="flex h-8 w-full items-center gap-2 rounded-md px-2 text-start transition-colors hover:bg-accent/40" onclick={() => (current = '')}>
							{#if volume.kind === 'host'}<HardDriveIcon class="size-4 shrink-0 text-primary" />{:else if volume.kind === 'config'}<FolderCogIcon class="size-4 shrink-0 text-primary" />{:else}<FolderOpenIcon class="size-4 shrink-0 text-primary" />{/if}
							<span class={cn('truncate font-mono text-sm', current === '' && 'text-primary')}>{label(volume)}</span>
							{#if locked}
								<span class="ms-auto flex items-center gap-1 text-xs text-muted-foreground" title="In use by {lockedBy}: it cannot be changed right now">
									<LockKeyholeIcon class="size-3.5" /><LoaderCircleIcon class="size-3 animate-spin" /> in use
								</span>
							{/if}
						</button>
						<ul class="ms-[1.625rem] space-y-0.5 pt-0.5">
							{@render level('')}
						</ul>
					{/if}
				</div>
			</div>

			{#if selected && volumeId !== null}
				<!-- the grip sits in the gap between the two panels (only side by side, not stacked). A focusable separator is
				     the standard "window splitter" pattern: it takes the keyboard too, which the lint rules do not know. -->
				<!-- svelte-ignore a11y_no_noninteractive_tabindex, a11y_no_noninteractive_element_interactions -->
				<div
					role="separator"
					aria-orientation="vertical"
					aria-label="Resize the preview"
					aria-valuenow={Math.round(paneWidth)}
					aria-valuemin={PANE_MIN}
					aria-valuemax={PANE_MAX}
					tabindex="0"
					class="group hidden w-4 shrink-0 cursor-col-resize touch-none items-center justify-center select-none focus-visible:outline-none lg:flex"
					onpointerdown={(e) => {
						dragging = true
						e.currentTarget.setPointerCapture(e.pointerId)
					}}
					onpointermove={drag}
					onpointerup={endDrag}
					onpointercancel={endDrag}
					onkeydown={nudgePane}
					ondblclick={() => ((paneWidth = 45), savePane())}
					transition:fade={{ duration: 200 }}
				>
					<span class="h-10 w-1 rounded-full bg-border transition-colors duration-200 group-hover:bg-primary/60 group-focus-visible:bg-primary {dragging ? 'bg-primary' : ''}"></span>
				</div>
				<aside use:pulseWhen={previewPulses} class="flex h-96 min-w-0 flex-col overflow-hidden rounded-xl border bg-card lg:h-auto lg:min-h-0 lg:w-(--pane)" style="--pane: {paneWidth}%; --pulse-ms: 1200ms" transition:fade={{ duration: 200 }} aria-label="Preview">
					<div class="flex items-center gap-2 border-b px-4 py-2.5">
						<div class="min-w-0 flex-1">
							<p class="truncate text-sm font-medium">{selected.name}</p>
							<p class="truncate text-xs text-muted-foreground">{formatSize(selected.size)}, changed {relative(selected.modified)}</p>
						</div>
						<Button variant="ghost" size="icon-sm" class="text-muted-foreground" aria-label="Download {selected.name}" href={api.fileUrl(volumeId, selectedPath, true)} download={selected.name}><DownloadIcon /></Button>
						<Button variant="ghost" size="icon-sm" class="text-muted-foreground transition-transform duration-200 hover:scale-110" aria-label="Enlarge the preview" title="Enlarge" onclick={() => (enlarged = true)}><Maximize2Icon /></Button>
						<Button variant="ghost" size="icon-sm" class="text-muted-foreground" aria-label="Close the preview" onclick={close}><XIcon /></Button>
					</div>
					<div class="relative m-4 min-h-0 flex-1">
						{#key `${selectedPath}#${saves}`}
							<FilePreview {volumeId} path={selectedPath} entry={selected} canEdit={canChange} locked={locked && !!root?.writable} bind:draft onsave={saveDraft} onleave={() => guarded(() => {})} />
						{/key}
					</div>
				</aside>
			{/if}
		</div>
	{/if}
</div>

<Dialog.Root open={naming !== null} onOpenChange={(o) => !o && (naming = null)}>
	<Dialog.Content class="sm:max-w-sm">
		<form onsubmit={submitName} class="grid gap-4">
			<Dialog.Header>
				<Dialog.Title>{naming?.kind === 'rename' ? 'Rename' : 'New folder'}</Dialog.Title>
				{#if naming?.kind === 'folder'}
					<Dialog.Description>It is made in <span class="font-mono">{[volume ? label(volume) : '', ...pieces.map((p) => p.name)].join('/')}</span>.</Dialog.Description>
				{/if}
			</Dialog.Header>
			<Input bind:value={nameInput} required maxlength={255} aria-label="Name" placeholder="Name" />
			<Dialog.Footer>
				<Button type="button" variant="ghost" onclick={() => (naming = null)}>Cancel</Button>
				<Button type="submit" disabled={!isValidName(nameInput)}>{naming?.kind === 'rename' ? 'Rename' : 'Create'}</Button>
			</Dialog.Footer>
		</form>
	</Dialog.Content>
</Dialog.Root>

<AlertDialog.Root open={doomed !== null} onOpenChange={(o) => !o && (doomed = null)}>
	<AlertDialog.Content>
		<AlertDialog.Header>
			<AlertDialog.Title>Delete {doomed?.entry.is_dir ? 'this folder' : 'this file'}?</AlertDialog.Title>
			<AlertDialog.Description>
				"{doomed?.entry.name}"{doomed?.entry.is_dir ? ' and everything in it' : ''} will be deleted for good
				{#if volume?.kind === 'host'}from {volume.host_path}{/if}. There is no undo.
			</AlertDialog.Description>
		</AlertDialog.Header>
		<AlertDialog.Footer>
			<AlertDialog.Cancel>Keep it</AlertDialog.Cancel>
			<AlertDialog.Action onclick={remove}>Delete</AlertDialog.Action>
		</AlertDialog.Footer>
	</AlertDialog.Content>
</AlertDialog.Root>

<Dialog.Root bind:open={creating}>
	<Dialog.Content class="sm:max-w-lg">
		<Dialog.Header>
			<Dialog.Title>New shared folder</Dialog.Title>
			<Dialog.Description>Agents can mount it in their cells, so runs can hand files to each other.</Dialog.Description>
		</Dialog.Header>
		<VolumeForm projectId={id} oncancel={() => (creating = false)} onadded={added} />
	</Dialog.Content>
</Dialog.Root>

<Dialog.Root bind:open={configuring}>
	<Dialog.Content class="sm:max-w-md">
		<Dialog.Header>
			<Dialog.Title>Settings of <span class="font-mono">{volume?.name}</span></Dialog.Title>
			<Dialog.Description>
				{#if volume?.kind === 'host'}{volume.host_path}{:else}Managed by Themis. Cells see it at <span class="font-mono">/workspace/{volume?.name}</span>.{/if}
			</Dialog.Description>
		</Dialog.Header>
		{#if volume}
			{#if volume.problem}<p class="text-sm text-destructive" role="alert">{volume.problem}</p>{/if}
			<form onsubmit={rename} class="grid gap-1.5">
				<label for="folder-rename" class="text-sm">Name</label>
				<div class="flex gap-2">
					<Input id="folder-rename" bind:value={newName} maxlength={40} class="font-mono" disabled={!renamable || renaming} />
					{#if renamable}
						<Button type="submit" variant="outline" disabled={renaming || !nameChanged || !isValidFolderName(newName)}>Rename</Button>
					{/if}
				</div>
				{#if renameError}
					<p class="text-xs text-destructive" role="alert">{renameError}</p>
				{:else if !renamable}
					<p class="text-xs text-muted-foreground">The shared folder keeps its name: every cell expects it.</p>
				{:else}
					<p class="text-xs text-muted-foreground">
						Cells will see it as <span class="font-mono">/workspace/{newName.trim().toLowerCase() || 'name'}</span>. Agents, workflows and runs keep the folder, but
						instructions, skills or scripts that mention the old name have to be changed by hand.
					</p>
				{/if}
			</form>
			<div class="flex flex-wrap items-center gap-3">
				<span class="text-sm">Cells may</span>
				<VolumeControls {volume} onchange={changeSettings} />
			</div>
			<p class="text-xs text-muted-foreground">Removing a folder from the project is done on its overview, under Shared folders. Its files are never deleted.</p>
		{/if}
	</Dialog.Content>
</Dialog.Root>

<svelte:window {onkeydown} onbeforeunload={(e) => dirty && e.preventDefault()} />

<AlertDialog.Root open={pending !== null} onOpenChange={(o) => !o && !pendingBusy && (pending = null)}>
	<AlertDialog.Content>
		<AlertDialog.Header>
			<AlertDialog.Title>You have unsaved changes</AlertDialog.Title>
			<AlertDialog.Description>
				"{draft?.entry.name}" was changed and not saved. Save the changes, or discard them and go on.
			</AlertDialog.Description>
		</AlertDialog.Header>
		{#if pendingError}<p class="text-sm text-destructive" role="alert">{pendingError}</p>{/if}
		<AlertDialog.Footer>
			<AlertDialog.Cancel disabled={pendingBusy}>Keep editing</AlertDialog.Cancel>
			<Button variant="outline" disabled={pendingBusy} onclick={discardAndGo}>Discard changes</Button>
			<Button disabled={pendingBusy} onclick={saveAndGo}>{pendingBusy ? 'Saving...' : 'Save changes'}</Button>
		</AlertDialog.Footer>
	</AlertDialog.Content>
</AlertDialog.Root>

<Dialog.Root bind:open={enlarged}>
	<Dialog.Content class="flex h-[85vh] flex-col gap-3 duration-300 ease-out sm:max-w-5xl">
		<Dialog.Header>
			<Dialog.Title class="truncate pe-8">{selected?.name}</Dialog.Title>
			<Dialog.Description>
				{selected ? `${formatSize(selected.size)}, changed ${relative(selected.modified)}` : ''}
				{#if files.length > 1 && selectedIndex >= 0}, {selectedIndex + 1} of {files.length}{/if}
			</Dialog.Description>
		</Dialog.Header>
		<div class="relative min-h-0 flex-1">
			{#if selected && volumeId !== null}
				{#key `${selectedPath}#${saves}`}
					<FilePreview {volumeId} path={selectedPath} entry={selected} canEdit={canChange} locked={locked && !!root?.writable} bind:draft onsave={saveDraft} onleave={() => guarded(() => {})} />
				{/key}
			{/if}
			{#if files.length > 1}
				<Button variant="secondary" size="icon-sm" class="absolute start-1 top-1/2 -translate-y-1/2 opacity-70 backdrop-blur transition-all duration-200 hover:scale-110 hover:opacity-100" aria-label="Previous file" disabled={selectedIndex <= 0} onclick={() => step(-1)}><ChevronLeftIcon /></Button>
				<Button variant="secondary" size="icon-sm" class="absolute end-1 top-1/2 -translate-y-1/2 opacity-70 backdrop-blur transition-all duration-200 hover:scale-110 hover:opacity-100" aria-label="Next file" disabled={selectedIndex < 0 || selectedIndex >= files.length - 1} onclick={() => step(1)}><ChevronRightIcon /></Button>
			{/if}
		</div>
	</Dialog.Content>
</Dialog.Root>
