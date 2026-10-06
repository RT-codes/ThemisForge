<script lang="ts">
	import { api, ApiError, type Skill } from '$lib/api'
	import * as AlertDialog from '$lib/components/ui/alert-dialog/index.js'
	import { Button } from '$lib/components/ui/button/index.js'
	import * as Dialog from '$lib/components/ui/dialog/index.js'
	import { Input } from '$lib/components/ui/input/index.js'
	import { Label } from '$lib/components/ui/label/index.js'
	import { Textarea } from '$lib/components/ui/textarea/index.js'
	import { isSkillName, skillTemplate, withName } from '$lib/skills'
	import { router } from '$lib/router.svelte'
	import PlusIcon from '@lucide/svelte/icons/plus'
	import SparklesIcon from '@lucide/svelte/icons/sparkles'
	import Trash2Icon from '@lucide/svelte/icons/trash-2'
	import { onMount, tick } from 'svelte'
	import { slide } from 'svelte/transition'

	// The skills of a project: SKILL.md files that agents can be given. Each one tells an agent how to do a kind of work.
	let { projectId }: { projectId: number } = $props()

	let skills = $state<Skill[]>([])
	let loaded = $state(false)
	let error = $state('')
	let section = $state<HTMLElement>()

	let open = $state(false)
	let editing = $state<string | null>(null) // the name of the skill being edited, null for a new one
	let name = $state('')
	let content = $state('')
	let saving = $state(false)
	let formError = $state('')
	let doomed = $state<Skill | null>(null)
	let confirmOpen = $state(false)

	async function load() {
		try {
			skills = await api.skills(projectId)
			error = ''
		} catch (e) {
			error = e instanceof Error ? e.message : 'Could not load the skills'
		} finally {
			loaded = true
		}
	}
	onMount(() => {
		load().then(async () => {
			await tick()
			if (router.hash === 'skills') section?.scrollIntoView({ behavior: 'smooth' })
		})
	})

	function startNew() {
		editing = null
		name = ''
		content = skillTemplate()
		formError = ''
		open = true
	}

	async function edit(skill: Skill) {
		formError = ''
		try {
			content = (await api.skill(projectId, skill.name)).content
			editing = skill.name
			name = skill.name
			open = true
		} catch (e) {
			error = e instanceof Error ? e.message : 'Could not open the skill'
		}
	}

	async function save(e: SubmitEvent) {
		e.preventDefault()
		formError = ''
		const target = editing ?? name.trim().toLowerCase()
		if (!isSkillName(target)) {
			formError = 'A skill name uses lowercase letters, digits and dashes, and starts with a letter or digit'
			return
		}
		saving = true
		try {
			await api.saveSkill(projectId, target, editing ? content : withName(content, target))
			open = false
			await load()
		} catch (err) {
			formError = err instanceof ApiError || err instanceof Error ? err.message : 'Could not save the skill'
		} finally {
			saving = false
		}
	}

	async function remove() {
		const target = doomed
		confirmOpen = false
		if (!target) return
		try {
			await api.deleteSkill(projectId, target.name)
			await load()
		} catch (err) {
			error = err instanceof ApiError || err instanceof Error ? err.message : 'Could not delete the skill'
		}
	}
</script>

<section bind:this={section} id="skills" class="mt-6 scroll-mt-6 rounded-xl border bg-card">
	<div class="flex items-center gap-3 p-5 pb-3">
		<div class="min-w-0 flex-1">
			<h3 class="text-base font-semibold tracking-tight">Skills</h3>
			<p class="text-sm text-muted-foreground">How to do a kind of work. An agent that is given a skill reads it when the task calls for it.</p>
		</div>
		<Button size="sm" onclick={startNew}><PlusIcon /> New skill</Button>
	</div>

	{#if error}<p class="px-5 pb-3 text-sm text-destructive" role="alert">{error}</p>{/if}

	{#if !loaded}
		<p class="px-5 pb-5 text-sm text-muted-foreground">Loading...</p>
	{:else if skills.length === 0}
		<div class="mx-5 mb-5 rounded-lg border border-dashed py-8 text-center">
			<p class="text-sm font-medium">No skills yet</p>
			<p class="mt-1 text-xs text-muted-foreground">A skill is a short guide in a SKILL.md file. Agents choose which ones they are given.</p>
		</div>
	{:else}
		<ul class="divide-y border-t">
			{#each skills as skill (skill.name)}
				<li class="flex items-center gap-3 px-5 py-3 transition-colors hover:bg-accent/40" transition:slide={{ duration: 200 }}>
					<button type="button" class="flex min-w-0 flex-1 items-center gap-3 text-start" onclick={() => edit(skill)}>
						<span class="flex size-8 shrink-0 items-center justify-center rounded-md bg-primary/15 text-primary"><SparklesIcon class="size-4" /></span>
						<span class="min-w-0 flex-1">
							<span class="block truncate font-mono text-sm font-medium">{skill.name}</span>
							<span class="block truncate text-xs text-muted-foreground">
								{skill.description || 'No description yet: open it to fix the file'}{skill.files > 1 ? ` · ${skill.files} files` : ''}
							</span>
						</span>
					</button>
					<Button variant="ghost" size="icon-sm" aria-label={`Delete ${skill.name}`} class="-me-2 shrink-0 text-muted-foreground/60 transition-colors hover:text-destructive" onclick={() => ((doomed = skill), (confirmOpen = true))}>
						<Trash2Icon />
					</Button>
				</li>
			{/each}
		</ul>
	{/if}
</section>

<Dialog.Root bind:open>
	<Dialog.Content class="sm:max-w-2xl">
		<Dialog.Header>
			<Dialog.Title>{editing ? `Edit ${editing}` : 'New skill'}</Dialog.Title>
			<Dialog.Description>
				The file starts with a name and a description between two --- lines. The description is how an agent decides when to use it.
				{editing ? 'Other files in its folder (scripts, notes) are kept and given to the agent too.' : ''}
			</Dialog.Description>
		</Dialog.Header>
		<form onsubmit={save} class="grid gap-4">
			{#if !editing}
				<div class="grid gap-2">
					<Label for="skill-name">Name</Label>
					<Input id="skill-name" bind:value={name} required maxlength={40} placeholder="e.g. pdf-tips" class="font-mono" />
				</div>
			{/if}
			<div class="grid gap-2">
				<Label for="skill-content">SKILL.md</Label>
				<Textarea id="skill-content" bind:value={content} rows={16} class="font-mono text-sm" spellcheck={false} />
			</div>
			{#if formError}<p class="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive" role="alert">{formError}</p>{/if}
			<Dialog.Footer>
				<Button type="button" variant="ghost" onclick={() => (open = false)}>Cancel</Button>
				<Button type="submit" disabled={saving || (!editing && !name.trim())}>{editing ? 'Save' : 'Create skill'}</Button>
			</Dialog.Footer>
		</form>
	</Dialog.Content>
</Dialog.Root>

<AlertDialog.Root bind:open={confirmOpen}>
	<AlertDialog.Content>
		<AlertDialog.Header>
			<AlertDialog.Title>Delete this skill?</AlertDialog.Title>
			<AlertDialog.Description>
				"{doomed?.name}" and everything in its folder are removed, and agents that had it lose it.
			</AlertDialog.Description>
		</AlertDialog.Header>
		<AlertDialog.Footer>
			<AlertDialog.Cancel>Keep it</AlertDialog.Cancel>
			<AlertDialog.Action onclick={remove}>Delete</AlertDialog.Action>
		</AlertDialog.Footer>
	</AlertDialog.Content>
</AlertDialog.Root>
