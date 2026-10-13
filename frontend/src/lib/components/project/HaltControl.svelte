<script lang="ts">
	import { api, ApiError } from '$lib/api'
	import * as AlertDialog from '$lib/components/ui/alert-dialog/index.js'
	import { Button } from '$lib/components/ui/button/index.js'
	import { Checkbox } from '$lib/components/ui/checkbox/index.js'
	import { Label } from '$lib/components/ui/label/index.js'
	import OctagonXIcon from '@lucide/svelte/icons/octagon-x'
	import PlayIcon from '@lucide/svelte/icons/play'

	// The emergency brake of a project or a board. Halting keeps anything in it from starting until it is resumed, and
	// (by default) stops what is running. Resuming is one click: it only lets the waiting work go on, and what the halt
	// interrupted stays in Blocked until someone runs it again.
	let {
		scope,
		id,
		name,
		haltedAt,
		running = 0,
		labelled = false,
		onchange,
	}: {
		scope: 'project' | 'board'
		id: number
		name: string
		haltedAt: string | null
		/** how many tasks are running in it now, so the question can say what stopping them means */
		running?: number
		/** a page-level control: a larger red button that says what it does, instead of the quiet icon of a board header */
		labelled?: boolean
		onchange: () => void
	} = $props()

	let open = $state(false)
	let stopRunning = $state(true)
	let busy = $state(false)
	let error = $state('')
	const noun = $derived(scope === 'project' ? 'project' : 'board')

	async function act(action: () => Promise<unknown>) {
		busy = true
		error = ''
		try {
			await action()
			open = false
			onchange()
		} catch (e) {
			error = e instanceof ApiError || e instanceof Error ? e.message : 'That did not work'
		} finally {
			busy = false
		}
	}

	const halt = () => act(() => (scope === 'project' ? api.haltProject(id, stopRunning) : api.haltBoard(id, stopRunning)))
	const resume = () => act(() => (scope === 'project' ? api.resumeProject(id) : api.resumeBoard(id)))
</script>

{#if haltedAt}
	<Button size={labelled ? 'lg' : 'sm'} variant="outline" class="border-amber-500/50 text-amber-300 hover:text-amber-200" disabled={busy} onclick={resume} title="Let the {noun} start things again">
		<PlayIcon /> Resume
	</Button>
{:else if labelled}
	<Button
		variant="destructive"
		size="lg"
		aria-label="Halt {name}"
		title="Halt the {noun}: stop what is running and keep anything from starting until it is resumed"
		onclick={() => ((error = ''), (open = true))}
	><OctagonXIcon /> Halt</Button>
{:else}
	<Button
		variant="ghost"
		size="icon-sm"
		class="text-muted-foreground hover:text-destructive"
		aria-label="Halt {name}"
		title="Halt the {noun}: stop what is running and keep anything from starting until it is resumed"
		onclick={() => ((error = ''), (open = true))}
	><OctagonXIcon /></Button>
{/if}
{#if error && !open}
	<span class="text-xs text-destructive" role="alert">{error}</span>
{/if}

<AlertDialog.Root bind:open>
	<AlertDialog.Content>
		<AlertDialog.Header>
			<AlertDialog.Title>Halt the {noun} "{name}"?</AlertDialog.Title>
			<AlertDialog.Description>
				Nothing in it will start until you resume it, not even by schedule or by a workflow. Tasks that are waiting stay waiting. A
				task that was interrupted goes to Blocked and does not start again by itself.
			</AlertDialog.Description>
		</AlertDialog.Header>
		<div class="flex items-center gap-2">
			<Checkbox id="halt-stop-{scope}-{id}" bind:checked={stopRunning} />
			<Label for="halt-stop-{scope}-{id}" class="text-sm font-normal">
				Also stop what is running now{running ? ` (${running} ${running === 1 ? 'task' : 'tasks'})` : ''}
			</Label>
		</div>
		{#if error}<p class="text-sm text-destructive" role="alert">{error}</p>{/if}
		<AlertDialog.Footer>
			<AlertDialog.Cancel disabled={busy}>Cancel</AlertDialog.Cancel>
			<AlertDialog.Action disabled={busy} onclick={(e) => (e.preventDefault(), halt())}>Halt</AlertDialog.Action>
		</AlertDialog.Footer>
	</AlertDialog.Content>
</AlertDialog.Root>
