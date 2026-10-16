<script lang="ts">
	import { api, ApiError, type Webhook, type Workspace } from '$lib/api'
	import { destinationLabel, statusLabel } from '$lib/boards'
	import { Button } from '$lib/components/ui/button/index.js'
	import { Switch } from '$lib/components/ui/switch/index.js'
	import WebhookDialog from '$lib/components/WebhookDialog.svelte'
	import { relative } from '$lib/format'
	import { router } from '$lib/router.svelte'
	import ChevronRightIcon from '@lucide/svelte/icons/chevron-right'
	import PlusIcon from '@lucide/svelte/icons/plus'
	import WebhookIcon from '@lucide/svelte/icons/webhook'
	import { onMount, tick } from 'svelte'
	import { slide } from 'svelte/transition'

	// The webhooks of a project: addresses other programs send messages to, each of which makes a task. A row opens the
	// webhook, where its messages are listed too.
	let { projectId }: { projectId: number } = $props()

	let hooks = $state<Webhook[]>([])
	let workspaces = $state<Workspace[]>([])
	let loaded = $state(false)
	let error = $state('')
	let section = $state<HTMLElement>()
	let dialogOpen = $state(false)
	let editing = $state<Webhook | null>(null)

	async function load() {
		try {
			;[hooks, workspaces] = await Promise.all([api.webhooks(projectId), api.workspaces(projectId)])
			error = ''
		} catch (e) {
			error = e instanceof Error ? e.message : 'Could not load the webhooks'
		} finally {
			loaded = true
		}
	}

	onMount(() => {
		load().then(async () => {
			await tick()
			if (router.hash === 'webhooks') section?.scrollIntoView({ behavior: 'smooth' })
		})
	})

	function openDialog(hook: Webhook | null) {
		editing = hook
		dialogOpen = true
	}

	async function toggle(hook: Webhook, enabled: boolean) {
		try {
			await api.updateWebhook(hook.id, { enabled })
			await load()
		} catch (e) {
			error = e instanceof ApiError || e instanceof Error ? e.message : 'Could not change the webhook'
		}
	}

	// "Tasks > Backlog": where its tasks land
	function target(hook: Webhook): string {
		const board = workspaces.flatMap((w) => w.boards).find((b) => b.id === hook.board_id)
		return board ? `${destinationLabel(workspaces, board)} · ${statusLabel(hook.status, board)}` : 'No board'
	}
</script>

<section bind:this={section} id="webhooks" class="mt-6 scroll-mt-6 rounded-xl border bg-card">
	<div class="flex items-center gap-3 p-5 pb-3">
		<div class="min-w-0 flex-1">
			<h3 class="text-base font-semibold tracking-tight">Webhooks</h3>
			<p class="text-sm text-muted-foreground">Let other programs make tasks here: a shop, GitHub, a form, your own script.</p>
		</div>
		<Button size="sm" onclick={() => openDialog(null)}><PlusIcon /> New webhook</Button>
	</div>

	{#if error}<p class="px-5 pb-3 text-sm text-destructive" role="alert">{error}</p>{/if}

	{#if !loaded}
		<p class="px-5 pb-5 text-sm text-muted-foreground">Loading...</p>
	{:else if hooks.length === 0}
		<div class="mx-5 mb-5 rounded-lg border border-dashed py-8 text-center">
			<p class="text-sm font-medium">No webhooks yet</p>
			<p class="mt-1 text-xs text-muted-foreground">A webhook is an address. Whatever posts a message to it makes a task, set up the way you choose.</p>
		</div>
	{:else}
		<ul class="divide-y border-t">
			{#each hooks as h (h.id)}
				<li class="flex items-center gap-3 px-5 py-3 transition-colors hover:bg-accent/40" transition:slide={{ duration: 200 }}>
					<button type="button" class="group flex min-w-0 flex-1 items-center gap-3 text-start" onclick={() => openDialog(h)}>
						<span class="flex size-8 shrink-0 items-center justify-center rounded-md bg-primary/15 text-primary"><WebhookIcon class="size-4" /></span>
						<span class="min-w-0 flex-1">
							<span class="block truncate text-sm font-medium">{h.name}</span>
							<span class={h.problem ? 'block truncate text-xs text-destructive' : 'block truncate text-xs text-muted-foreground'}>
								{#if h.problem}{h.problem}{:else}{target(h)} · {h.last_received_at ? `last message ${relative(h.last_received_at)}` : 'nothing received yet'}{/if}
							</span>
						</span>
						<ChevronRightIcon class="size-4 shrink-0 text-muted-foreground/50 transition-transform group-hover:translate-x-0.5 group-hover:text-foreground" />
					</button>
					<Switch checked={h.enabled} onCheckedChange={(v) => toggle(h, v)} aria-label="{h.name} on" />
				</li>
			{/each}
		</ul>
	{/if}
</section>

<WebhookDialog bind:open={dialogOpen} {projectId} webhook={editing} {workspaces} onchanged={load} />
