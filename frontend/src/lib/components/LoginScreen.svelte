<script lang="ts">
	import { api } from '$lib/api'
	import { auth } from '$lib/auth.svelte'
	import { Button } from '$lib/components/ui/button/index.js'
	import { Input } from '$lib/components/ui/input/index.js'
	import { Label } from '$lib/components/ui/label/index.js'
	import { Textarea } from '$lib/components/ui/textarea/index.js'
	import CircleCheckIcon from '@lucide/svelte/icons/circle-check'
	import AuthShell from './AuthShell.svelte'

	// 'setup' creates the first (administrator) account, 'request' asks the administrator for access
	let view = $state<'login' | 'request'>('login')
	let name = $state('')
	let email = $state('')
	let password = $state('')
	let reason = $state('I would like to collaborate on project X')
	let error = $state('')
	let busy = $state(false)
	let sent = $state(false)

	const mode = $derived(auth.needsAdmin ? 'setup' : view)

	async function submit(e: SubmitEvent) {
		e.preventDefault()
		error = ''
		busy = true
		try {
			if (mode === 'login') await auth.login(email, password)
			else if (mode === 'setup') await auth.register(name, email, password)
			else {
				await api.requestAccess(name, email, reason)
				sent = true
			}
		} catch (err) {
			error = err instanceof Error ? err.message : 'Something went wrong'
		} finally {
			busy = false
		}
	}

	function show(next: 'login' | 'request') {
		view = next
		error = ''
		sent = false
	}

	const titles = {
		login: ['Welcome back', 'Sign in to continue to Themis.'],
		setup: ['Create the administrator account', 'This is the first account. Everyone else joins by invitation.'],
		request: ['Request access', 'Themis is invite only. Tell the administrator who you are and why.'],
	} as const
</script>

{#snippet links()}
	{#if mode === 'login'}
		Need an account?
		<button type="button" class="ml-1 font-medium text-primary hover:underline" onclick={() => show('request')}>Request access</button>
	{:else if mode === 'request'}
		Already have an account?
		<button type="button" class="ml-1 font-medium text-primary hover:underline" onclick={() => show('login')}>Sign in</button>
	{/if}
{/snippet}

<AuthShell title={titles[mode][0]} description={titles[mode][1]} footer={mode === 'setup' || sent ? undefined : links}>
	{#if mode === 'request' && sent}
		<div class="grid justify-items-center gap-3 py-4 text-center">
			<CircleCheckIcon class="size-8 text-emerald-400" />
			<p class="font-medium">Request sent</p>
			<p class="text-sm text-muted-foreground">
				The administrator will look at it. If they approve, they will send you a personal link to create your account.
			</p>
			<Button variant="outline" onclick={() => show('login')}>Back to sign in</Button>
		</div>
	{:else}
		<form onsubmit={submit} class="grid gap-4">
			{#if mode !== 'login'}
				<div class="grid gap-2">
					<Label for="name">Name</Label>
					<Input id="name" autocomplete="name" required maxlength={100} bind:value={name} />
				</div>
			{/if}
			<div class="grid gap-2">
				<Label for="email">Email</Label>
				<Input id="email" type="email" autocomplete="email" required bind:value={email} />
			</div>
			{#if mode === 'request'}
				<div class="grid gap-2">
					<Label for="reason">Why do you want access?</Label>
					<Textarea id="reason" rows={3} required maxlength={1000} bind:value={reason} />
				</div>
			{:else}
				<div class="grid gap-2">
					<Label for="password">Password</Label>
					<Input
						id="password"
						type="password"
						autocomplete={mode === 'login' ? 'current-password' : 'new-password'}
						minlength={mode === 'setup' ? 8 : undefined}
						required
						bind:value={password}
					/>
				</div>
			{/if}
			{#if error}
				<p class="text-sm text-destructive" role="alert">{error}</p>
			{/if}
			<Button type="submit" disabled={busy} class="w-full">
				{busy ? 'Please wait...' : mode === 'login' ? 'Sign in' : mode === 'setup' ? 'Create account' : 'Send request'}
			</Button>
		</form>
	{/if}
</AuthShell>
