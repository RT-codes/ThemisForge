<script lang="ts">
	import { agentsApi, type KeyInfo } from '$lib/api/agents'
	import RegistryAdd from '$lib/components/RegistryAdd.svelte'
	import { Button } from '$lib/components/ui/button/index.js'
	import { router } from '$lib/router.svelte'
	import CircleCheckIcon from '@lucide/svelte/icons/circle-check'
	import SearchIcon from '@lucide/svelte/icons/search'

	// Settings' way into the MCP registry. Tools themselves belong to a project, so this only finds them: the project is
	// asked for when one is picked, and the tool is made there like any other (see RegistryAdd).
	let open = $state(false)
	let keys = $state<KeyInfo[]>([])
	let added = $state<{ name: string; project: { id: number; name: string } } | null>(null)
	let error = $state('')

	async function browse() {
		error = ''
		try {
			keys = await agentsApi.keys()
			open = true
		} catch (e) {
			error = e instanceof Error ? e.message : 'Could not load the keys'
		}
	}
</script>

<div class="grid gap-3">
	<p class="text-sm text-muted-foreground">
		Tools are MCP servers an agent can use, such as a search service or a database. Browse the official registry here, pick one, and
		choose the project it is for. Keys are shared, so one key can serve tools in several projects.
	</p>
	<p class="text-xs text-muted-foreground">
		The first time, Themis reads the registry's whole listing in the background (a few minutes) and keeps a copy on this machine.
	</p>
	<div>
		<Button variant="outline" size="sm" onclick={browse}><SearchIcon /> Browse the registry</Button>
	</div>
	{#if error}<p class="text-sm text-destructive" role="alert">{error}</p>{/if}
	{#if added}
		<div class="flex items-center gap-2 rounded-md border bg-muted/40 px-3 py-2 text-sm" role="status">
			<CircleCheckIcon class="size-4 shrink-0 text-tone-green" />
			<span class="flex-1">Added <span class="font-mono">{added.name}</span> to {added.project.name}. Give it to an agent from that project.</span>
			<Button variant="ghost" size="sm" onclick={() => added && router.navigate(`/projects/${added.project.id}/settings#tools`)}>Open project</Button>
		</div>
	{/if}
</div>

<RegistryAdd bind:open projectId={null} {keys} onadded={(server, project) => (added = { name: server.name, project })} />
