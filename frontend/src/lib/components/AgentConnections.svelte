<script lang="ts">
	import { api, type ConnectionProvider, type ProjectConnection } from '$lib/api'
	import { router } from '$lib/router.svelte'
	import { Checkbox } from '$lib/components/ui/checkbox/index.js'
	import DynamicIcon from '$lib/components/DynamicIcon.svelte'
	import PlugIcon from '@lucide/svelte/icons/plug'
	import { onMount } from 'svelte'

	// The services an agent may use. A service must first be chosen on the project (its Connections card); the agent
	// then opts in here, so a token is only in the hands of the agents that were given it.
	let {
		projectId,
		selected = $bindable([]),
		readonly = false,
	}: { projectId: number; selected?: string[]; readonly?: boolean } = $props()

	let services = $state<ConnectionProvider[]>([])
	let bound = $state<ProjectConnection[]>([])
	let loaded = $state(false)

	onMount(async () => {
		try {
			const [list, used] = await Promise.all([api.connections(), api.projectConnections(projectId)])
			services = list.providers.filter((p) => p.category === 'service')
			bound = used
		} finally {
			loaded = true
		}
	})

	const shown = $derived(readonly ? services.filter((s) => selected.includes(s.id)) : services)
	const account = (id: string) => bound.find((b) => b.provider === id)?.account ?? ''
	const toggle = (id: string, on: boolean) => (selected = on ? [...selected.filter((x) => x !== id), id] : selected.filter((x) => x !== id))
</script>

{#if loaded && (!readonly || shown.length)}
	<div class="grid gap-2">
		{#each shown as service (service.id)}
			{@const who = account(service.id)}
			<label class="flex items-center gap-3 rounded-lg border px-3 py-2.5">
				{#if !readonly}
					<Checkbox checked={selected.includes(service.id)} disabled={!who && !selected.includes(service.id)} onCheckedChange={(on) => toggle(service.id, !!on)} aria-label="Give it {service.name}" />
				{/if}
				<DynamicIcon name={service.icon} fallback={PlugIcon} class="size-4 shrink-0 text-muted-foreground" />
				<span class="min-w-0 flex-1 text-sm">{service.name}</span>
				<span class="text-xs text-muted-foreground">
					{#if who}as @{who}{:else}<button type="button" class="underline-offset-4 hover:underline" onclick={() => router.navigate(`/projects/${projectId}`)}>Not set up on the project</button>{/if}
				</span>
			</label>
		{:else}
			<p class="text-sm text-muted-foreground">No services to connect yet.</p>
		{/each}
	</div>
{/if}
