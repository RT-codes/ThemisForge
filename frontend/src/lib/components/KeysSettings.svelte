<script lang="ts">
	import { settingsApi, type Secret } from '$lib/api/settings'
	import { Button } from '$lib/components/ui/button/index.js'
	import { Input } from '$lib/components/ui/input/index.js'
	import * as Select from '$lib/components/ui/select/index.js'
	import SettingsSection from '$lib/components/SettingsSection.svelte'
	import { dateTime } from '$lib/format'
	import { summarizeKeys } from '$lib/settingsView'
	import KeyRoundIcon from '@lucide/svelte/icons/key-round'
	import Trash2Icon from '@lucide/svelte/icons/trash-2'
	import { onMount } from 'svelte'

	// The credentials agents are given (see Secret): listed by name and hint, never shown again. Loaded here and not by
	// the page, so a failure to list them is shown in this section and not as a page that looks empty.
	let secrets = $state<Secret[]>([])
	let loadError = $state('')
	let secretName = $state('')
	let secretKind = $state('anthropic')
	let secretValue = $state('')
	let secretError = $state('')

	const kinds = ['anthropic', 'openai', 'google', 'github', 'custom']

	onMount(async () => {
		try {
			secrets = await settingsApi.secrets()
		} catch (e) {
			loadError = e instanceof Error ? e.message : 'Could not load the keys'
		}
	})

	async function addSecret(e: SubmitEvent) {
		e.preventDefault()
		secretError = ''
		try {
			await settingsApi.createSecret(secretName, secretKind, secretValue)
			secretName = secretValue = ''
			secrets = await settingsApi.secrets()
		} catch (err) {
			secretError = err instanceof Error ? err.message : 'Could not add the secret'
		}
	}

	async function removeSecret(s: Secret) {
		await settingsApi.deleteSecret(s.id)
		secrets = await settingsApi.secrets()
	}
</script>

<SettingsSection id="keys" title="Keys" description="Credentials for model providers and tools. They are encrypted and never shown again." summary={summarizeKeys(secrets.length)}>
	{#if loadError}<p class="text-sm text-destructive" role="alert">{loadError}</p>{/if}
	{#if secrets.length}
		<ul class="divide-y rounded-lg border">
			{#each secrets as s (s.id)}
				<li class="flex items-center gap-3 px-3 py-2.5">
					<KeyRoundIcon class="size-4 shrink-0 text-muted-foreground" />
					<div class="min-w-0">
						<p class="truncate text-sm font-medium">{s.name}</p>
						<p class="text-xs text-muted-foreground">{s.kind} · <span class="font-mono">{s.hint}</span> · added {dateTime(s.created_at)}</p>
					</div>
					<Button type="button" variant="ghost" size="icon" class="ms-auto" aria-label={`Delete ${s.name}`} onclick={() => removeSecret(s)}>
						<Trash2Icon />
					</Button>
				</li>
			{/each}
		</ul>
	{:else}
		<p class="rounded-lg border border-dashed py-6 text-center text-sm text-muted-foreground">No keys yet.</p>
	{/if}

	<form onsubmit={addSecret} class="grid gap-3 sm:grid-cols-[1fr_9rem]">
		<Input bind:value={secretName} placeholder="Name, e.g. Anthropic (work)" required aria-label="Secret name" />
		<Select.Root type="single" bind:value={secretKind}>
			<Select.Trigger class="w-full capitalize">{secretKind}</Select.Trigger>
			<Select.Content>
				{#each kinds as k (k)}<Select.Item value={k} label={k} class="capitalize">{k}</Select.Item>{/each}
			</Select.Content>
		</Select.Root>
		<Input type="password" autocomplete="off" bind:value={secretValue} placeholder="Key or token" required class="font-mono sm:col-span-2" aria-label="Secret value" />
		{#if secretError}<p class="text-sm text-destructive sm:col-span-2" role="alert">{secretError}</p>{/if}
		<Button type="submit" variant="secondary" class="justify-self-start sm:col-span-2">Add key</Button>
	</form>
</SettingsSection>
