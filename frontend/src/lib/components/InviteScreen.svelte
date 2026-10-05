<script lang="ts">
	import { api, ApiError } from '$lib/api'
	import { auth } from '$lib/auth.svelte'
	import { Button } from '$lib/components/ui/button/index.js'
	import { Input } from '$lib/components/ui/input/index.js'
	import { Label } from '$lib/components/ui/label/index.js'
	import { router } from '$lib/router.svelte'
	import { onMount } from 'svelte'
	import AuthShell from './AuthShell.svelte'

	let { token }: { token: string } = $props()

	let email = $state<string | null>(null)
	let invalid = $state('')
	let name = $state('')
	let password = $state('')
	let error = $state('')
	let busy = $state(false)

	onMount(async () => {
		try {
			email = (await api.checkInvite(token)).email
		} catch (e) {
			invalid = e instanceof ApiError && e.status === 404 ? e.message : 'Could not check this invite link'
		}
	})

	async function submit(e: SubmitEvent) {
		e.preventDefault()
		error = ''
		busy = true
		try {
			auth.signedIn(await api.acceptInvite(token, name, password))
			router.navigate('/')
		} catch (err) {
			error = err instanceof Error ? err.message : 'Something went wrong'
		} finally {
			busy = false
		}
	}
</script>

{#if invalid}
	<AuthShell title="Invite not valid" description={invalid}>
		<p class="text-sm text-muted-foreground">Ask the administrator for a new link. Invite links work once and expire after 7 days.</p>
		<Button class="mt-4 w-full" variant="outline" onclick={() => router.navigate('/')}>Go to sign in</Button>
	</AuthShell>
{:else if email}
	<AuthShell title="You are invited" description="Choose a name and password to create your account.">
		<form onsubmit={submit} class="grid gap-4">
			<div class="grid gap-2">
				<Label for="invite-email">Email</Label>
				<Input id="invite-email" type="email" value={email} readonly class="text-muted-foreground" />
			</div>
			<div class="grid gap-2">
				<Label for="invite-name">Name</Label>
				<Input id="invite-name" autocomplete="name" required maxlength={100} bind:value={name} />
			</div>
			<div class="grid gap-2">
				<Label for="invite-password">Password</Label>
				<Input id="invite-password" type="password" autocomplete="new-password" minlength={8} required bind:value={password} />
			</div>
			{#if error}<p class="text-sm text-destructive" role="alert">{error}</p>{/if}
			<Button type="submit" disabled={busy} class="w-full">{busy ? 'Please wait...' : 'Create account'}</Button>
		</form>
	</AuthShell>
{:else}
	<div class="min-h-svh"></div>
{/if}
