<script lang="ts">
	import { api, ApiError, type Skill } from '$lib/api'
	import ConfigFilePane from '$lib/components/ConfigFilePane.svelte'
	import * as AlertDialog from '$lib/components/ui/alert-dialog/index.js'
	import { Button } from '$lib/components/ui/button/index.js'
	import * as Dialog from '$lib/components/ui/dialog/index.js'
	import { Input } from '$lib/components/ui/input/index.js'
	import { Switch } from '$lib/components/ui/switch/index.js'
	import { joinPath } from '$lib/files'
	import { isSkillName, skillTemplate } from '$lib/skills'
	import { cn } from '$lib/utils'
	import AlertTriangleIcon from '@lucide/svelte/icons/triangle-alert'
	import FileIcon from '@lucide/svelte/icons/file'
	import FolderOpenIcon from '@lucide/svelte/icons/folder-open'
	import PlusIcon from '@lucide/svelte/icons/plus'
	import SparklesIcon from '@lucide/svelte/icons/sparkles'
	import Trash2Icon from '@lucide/svelte/icons/trash-2'
	import { onMount } from 'svelte'
	import { fade, slide } from 'svelte/transition'

	// Every skill of the project, with a switch for the ones this agent has. A skill is a folder in the project's config
	// folder; picking one shows its files beside the list, where they can be read and edited like on the Files page.
	// Editing is live (each file is saved on its own), while the switches are part of the agent and saved with it.
	let {
		projectId,
		selected = $bindable(),
		skills = $bindable(),
		dirty = $bindable(false),
		canEdit,
		onremoved,
	}: {
		projectId: number
		selected: string[]
		skills: Skill[]
		dirty?: boolean // a file here has unsaved changes
		canEdit: boolean
		onremoved: (name: string) => void // a skill was deleted, so agents lost it
	} = $props()

	let volumeId = $state<number | null>(null)
	let focus = $state<string | null>(null) // the skill shown on the right
	let file = $state('SKILL.md') // which file of its folder
	let files = $state<string[]>([])
	let error = $state('')
	let paneDirty = $state(false)
	$effect(() => {
		dirty = paneDirty
	})

	onMount(async () => {
		try {
			volumeId = (await api.configFolder(projectId)).id
		} catch (e) {
			error = e instanceof Error ? e.message : 'Could not open the config folder'
		}
	})

	const toggled = (name: string, on: boolean) => (selected = on ? [...selected, name] : selected.filter((x) => x !== name))
	// skills the agent's file names but the project no longer has: shown so they can be taken off
	const missing = $derived(selected.filter((n) => !skills.some((s) => s.name === n)))
	const current = $derived(skills.find((s) => s.name === focus) ?? null)

	// the files in the focused skill's folder (SKILL.md first), for the tabs above the file
	async function loadFiles() {
		if (focus === null || volumeId === null) return void (files = [])
		const name = focus
		try {
			const got = await api.listFiles(volumeId, joinPath('skills', name))
			if (name !== focus) return
			const names = (got?.listing.entries ?? []).filter((e) => !e.is_dir).map((e) => e.name)
			files = ['SKILL.md', ...names.filter((n) => n !== 'SKILL.md')]
		} catch {
			files = ['SKILL.md']
		}
	}
	$effect(() => {
		void [focus, volumeId, current?.files]
		loadFiles()
	})

	async function reload() {
		try {
			skills = await api.skills(projectId)
		} catch (e) {
			error = e instanceof Error ? e.message : 'Could not load the skills'
		}
	}

	// moving away from a file with unsaved changes asks first
	let pending = $state<(() => void) | null>(null)
	function guarded(go: () => void) {
		if (paneDirty) pending = go
		else go()
	}
	const pick = (name: string) => name !== focus && guarded(() => ((focus = name), (file = 'SKILL.md')))
	const pickFile = (name: string) => name !== file && guarded(() => (file = name))

	// ----- a new skill -----

	let creating = $state(false)
	let newName = $state('')
	let createError = $state('')
	let busy = $state(false)
	function startNew() {
		newName = ''
		createError = ''
		creating = true
	}
	async function create(e: SubmitEvent) {
		e.preventDefault()
		const name = newName.trim().toLowerCase()
		if (!isSkillName(name)) {
			createError = 'A skill name uses lowercase letters, digits and dashes, and starts with a letter or digit'
			return
		}
		busy = true
		try {
			await api.saveSkill(projectId, name, skillTemplate(name))
			await reload()
			creating = false
			toggled(name, true) // made for this agent, so it has it
			guarded(() => ((focus = name), (file = 'SKILL.md')))
		} catch (err) {
			createError = err instanceof ApiError || err instanceof Error ? err.message : 'Could not create the skill'
		} finally {
			busy = false
		}
	}

	// ----- deleting one -----

	let doomed = $state<Skill | null>(null)
	async function remove() {
		const target = doomed
		doomed = null
		if (!target) return
		try {
			await api.deleteSkill(projectId, target.name)
			if (focus === target.name) focus = null
			paneDirty = false
			onremoved(target.name)
			await reload()
		} catch (e) {
			error = e instanceof ApiError || e instanceof Error ? e.message : 'Could not delete the skill'
		}
	}
</script>

<!-- fills the height the editor has (at least 26rem), so the two panels grow with the window -->
<div class="grid min-h-[26rem] flex-1 gap-3 lg:grid-cols-[minmax(0,19rem)_minmax(0,1fr)] lg:grid-rows-[minmax(0,1fr)]">
	<!-- the list is a panel like the preview beside it, as tall as it: the skills scroll inside it, and the toolbar with
	     New skill stays at its foot -->
	<div class="flex h-[26rem] min-w-0 flex-col overflow-hidden rounded-lg border bg-background/40 lg:h-auto">
		<div class="slim-scrollbar grid min-h-0 flex-1 grid-cols-1 content-start gap-1.5 overflow-y-auto p-2">
		{#each skills as skill (skill.name)}
			{@const on = selected.includes(skill.name)}
			<div
				class={cn('flex min-w-0 items-center gap-2.5 cursor-pointer overflow-hidden rounded-md border px-2.5 py-2 transition-colors hover:border-primary/40 hover:bg-accent/40', skill.name === focus && 'border-primary/40 bg-accent/60')}
				transition:slide={{ duration: 160 }}
				onclick={() => pick(skill.name)}
				role="presentation"
			>
				<button type="button" class="flex min-w-0 flex-1 cursor-pointer items-center gap-2.5 text-start" aria-pressed={skill.name === focus}>
					<span class={cn('flex size-7 shrink-0 items-center justify-center rounded-md transition-colors', on ? 'bg-primary/15 text-primary' : 'bg-muted text-muted-foreground')}>
						<SparklesIcon class="size-4" />
					</span>
					<span class="min-w-0 flex-1">
						<span class="block truncate font-mono text-sm font-medium">{skill.name}</span>
						<span class="block truncate text-xs text-muted-foreground">{skill.description || 'No description yet: open it to fix the file'}</span>
					</span>
				</button>
				<!-- svelte-ignore a11y_click_events_have_key_events, a11y_no_static_element_interactions -->
				<span class="flex cursor-default" onclick={(e) => e.stopPropagation()}><Switch checked={on} onCheckedChange={(v) => toggled(skill.name, v)} aria-label="Give the agent {skill.name}" /></span>
			</div>
		{:else}
			<p class="rounded-lg border border-dashed px-3 py-6 text-center text-sm text-muted-foreground">No skills yet. A skill is a short guide that agents read when a task calls for it.</p>
		{/each}
		{#each missing as name (name)}
			<div class="flex items-center gap-3 rounded-lg border border-yellow-500/30 bg-yellow-500/5 px-3 py-2.5" transition:slide={{ duration: 160 }}>
				<AlertTriangleIcon class="size-4 shrink-0 text-yellow-300" />
				<span class="min-w-0 flex-1">
					<span class="block truncate font-mono text-sm">{name}</span>
					<span class="block text-xs text-yellow-300">No longer exists in this project</span>
				</span>
				<Button type="button" variant="outline" size="sm" onclick={() => toggled(name, false)}>Remove</Button>
			</div>
		{/each}
		{#if error}<p class="px-1 text-sm text-destructive" role="alert">{error}</p>{/if}
		</div>
		{#if canEdit}
			<div class="border-t p-2">
				<Button type="button" variant="outline" size="sm" class="w-full" onclick={startNew}><PlusIcon /> New skill</Button>
			</div>
		{/if}
	</div>

	<div class="relative flex h-[26rem] min-w-0 flex-col overflow-hidden rounded-lg border bg-background/40 lg:h-auto">
		{#if current && volumeId !== null}
			<div class="flex flex-wrap items-center gap-2 border-b px-4 py-2.5" in:fade={{ duration: 150 }}>
				<div class="min-w-0 flex-1">
					<p class="truncate font-mono text-sm font-medium">{current.name}</p>
					<p class="truncate text-xs text-muted-foreground">
						{selected.includes(current.name) ? 'This agent has it.' : 'This agent does not have it.'} Other agents may.
					</p>
				</div>
				<Button variant="ghost" size="icon-sm" class="text-muted-foreground" aria-label="Open the folder in Files" title="Open in Files" href="/projects/{projectId}/files#config/skills/{current.name}/{file}"><FolderOpenIcon /></Button>
				{#if canEdit}
					<Button variant="ghost" size="icon-sm" class="text-muted-foreground hover:text-destructive" aria-label="Delete {current.name}" onclick={() => (doomed = current)}><Trash2Icon /></Button>
				{/if}
			</div>
			{#if files.length > 1}
				<div class="flex flex-wrap gap-1 border-b px-3 py-2" role="tablist" aria-label="Files of {current.name}">
					{#each files as f (f)}
						<Button variant={f === file ? 'secondary' : 'ghost'} size="sm" class="h-7 gap-1.5 px-2 font-mono text-xs" role="tab" aria-selected={f === file} onclick={() => pickFile(f)}>
							<FileIcon class="size-3.5" />{f}
						</Button>
					{/each}
				</div>
			{/if}
			<div class="relative m-4 flex min-h-0 flex-1 flex-col">
				{#key `${current.name}/${file}`}
					<ConfigFilePane {volumeId} path={joinPath(`skills/${current.name}`, file)} {canEdit} bind:dirty={paneDirty} onsaved={reload} />
				{/key}
			</div>
		{:else}
			<div class="m-auto max-w-xs px-6 text-center" in:fade={{ duration: 150 }}>
				<SparklesIcon class="mx-auto size-7 text-muted-foreground" />
				<p class="mt-3 text-sm font-medium">Pick a skill to read it</p>
				<p class="mt-1 text-xs text-muted-foreground">Its files open here, and can be edited and saved on the spot. The switch beside a skill gives it to this agent.</p>
			</div>
		{/if}
	</div>
</div>

<Dialog.Root bind:open={creating}>
	<Dialog.Content class="sm:max-w-sm">
		<form onsubmit={create} class="grid gap-4">
			<Dialog.Header>
				<Dialog.Title>New skill</Dialog.Title>
				<Dialog.Description>It starts from a template that you fill in. The agent you are editing is given it.</Dialog.Description>
			</Dialog.Header>
			<div class="grid gap-1.5">
				<Input bind:value={newName} required maxlength={40} placeholder="e.g. pdf-tips" class="font-mono" aria-label="Skill name" />
				{#if createError}<p class="text-xs text-destructive" role="alert">{createError}</p>{/if}
			</div>
			<Dialog.Footer>
				<Button type="button" variant="ghost" onclick={() => (creating = false)}>Cancel</Button>
				<Button type="submit" disabled={busy || !newName.trim()}>Create skill</Button>
			</Dialog.Footer>
		</form>
	</Dialog.Content>
</Dialog.Root>

<AlertDialog.Root open={doomed !== null} onOpenChange={(o) => !o && (doomed = null)}>
	<AlertDialog.Content>
		<AlertDialog.Header>
			<AlertDialog.Title>Delete this skill?</AlertDialog.Title>
			<AlertDialog.Description>
				"{doomed?.name}" and everything in its folder are deleted for good, and every agent that has it loses it.
			</AlertDialog.Description>
		</AlertDialog.Header>
		<AlertDialog.Footer>
			<AlertDialog.Cancel>Keep it</AlertDialog.Cancel>
			<AlertDialog.Action onclick={remove}>Delete</AlertDialog.Action>
		</AlertDialog.Footer>
	</AlertDialog.Content>
</AlertDialog.Root>

<AlertDialog.Root open={pending !== null} onOpenChange={(o) => !o && (pending = null)}>
	<AlertDialog.Content>
		<AlertDialog.Header>
			<AlertDialog.Title>You have unsaved changes</AlertDialog.Title>
			<AlertDialog.Description>The file you are editing was changed and not saved. Keep editing, or discard the changes and go on.</AlertDialog.Description>
		</AlertDialog.Header>
		<AlertDialog.Footer>
			<AlertDialog.Cancel>Keep editing</AlertDialog.Cancel>
			<AlertDialog.Action
				onclick={() => {
					const go = pending
					pending = null
					paneDirty = false
					go?.()
				}}>Discard changes</AlertDialog.Action
			>
		</AlertDialog.Footer>
	</AlertDialog.Content>
</AlertDialog.Root>
