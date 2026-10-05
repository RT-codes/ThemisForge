<script lang="ts">
	import { auth } from '$lib/auth.svelte'
	import { Button } from '$lib/components/ui/button/index.js'
	import * as Card from '$lib/components/ui/card/index.js'
	import { Input } from '$lib/components/ui/input/index.js'
	import { Label } from '$lib/components/ui/label/index.js'
	import Logo from './Logo.svelte'

	let mode = $state<'login' | 'register'>('login')
	let name = $state('')
	let email = $state('')
	let password = $state('')
	let error = $state('')
	let busy = $state(false)

	async function submit(e: SubmitEvent) {
		e.preventDefault()
		error = ''
		busy = true
		try {
			if (mode === 'login') await auth.login(email, password)
			else await auth.register(name, email, password)
		} catch (err) {
			error = err instanceof Error ? err.message : 'Something went wrong'
		} finally {
			busy = false
		}
	}

	function toggle() {
		mode = mode === 'login' ? 'register' : 'login'
		error = ''
	}
</script>

<main class="forge-glow flex min-h-svh items-center justify-center p-4">
	<div class="w-full max-w-sm">
		<div class="mb-8 flex flex-col items-center gap-3 text-center">
			<Logo size="lg" />
			<div>
				<h1 class="text-2xl font-semibold tracking-tight">ThemisForge</h1>
				<p class="text-sm text-muted-foreground">Forge your flows with clarity.</p>
			</div>
		</div>

		<Card.Root>
			<Card.Header>
				<Card.Title>{mode === 'login' ? 'Welcome back' : 'Create your account'}</Card.Title>
				<Card.Description>
					{mode === 'login' ? 'Sign in to continue to ThemisForge.' : 'Get started in a few seconds.'}
				</Card.Description>
			</Card.Header>
			<Card.Content>
				<form onsubmit={submit} class="grid gap-4">
					{#if mode === 'register'}
						<div class="grid gap-2">
							<Label for="name">Name</Label>
							<Input id="name" autocomplete="name" required bind:value={name} />
						</div>
					{/if}
					<div class="grid gap-2">
						<Label for="email">Email</Label>
						<Input id="email" type="email" autocomplete="email" required bind:value={email} />
					</div>
					<div class="grid gap-2">
						<Label for="password">Password</Label>
						<Input
							id="password"
							type="password"
							autocomplete={mode === 'login' ? 'current-password' : 'new-password'}
							minlength={mode === 'register' ? 8 : undefined}
							required
							bind:value={password}
						/>
					</div>
					{#if error}
						<p class="text-sm text-destructive" role="alert">{error}</p>
					{/if}
					<Button type="submit" disabled={busy} class="w-full">
						{busy ? 'Please wait...' : mode === 'login' ? 'Sign in' : 'Create account'}
					</Button>
				</form>
			</Card.Content>
			<Card.Footer class="justify-center text-sm text-muted-foreground">
				{mode === 'login' ? "Don't have an account?" : 'Already have an account?'}
				<button type="button" class="ml-1 font-medium text-primary hover:underline" onclick={toggle}>
					{mode === 'login' ? 'Sign up' : 'Sign in'}
				</button>
			</Card.Footer>
		</Card.Root>
	</div>
</main>
