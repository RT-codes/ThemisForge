<script lang="ts">
	import { settingsApi, type CellPackage, type CellPackageDefaults } from '$lib/api/settings'
	import { Button } from '$lib/components/ui/button/index.js'
	import { Input } from '$lib/components/ui/input/index.js'
	import { Label } from '$lib/components/ui/label/index.js'
	import { Switch } from '$lib/components/ui/switch/index.js'
	import { Textarea } from '$lib/components/ui/textarea/index.js'
	import { approxTokens, formatWaits, parseWaits, shownText, storedText } from '$lib/cellPackage'
	import RotateCcwIcon from '@lucide/svelte/icons/rotate-ccw'
	import { onMount } from 'svelte'

	// What Themis puts into every Codex cell by itself (the "Themis package"): the rules in the prompt, the themis-cell
	// skill and how often a run is started again. It is edited in place and saved with the Settings page's save bar.
	let { pkg = $bindable() }: { pkg: CellPackage } = $props()

	let defaults = $state<CellPackageDefaults | null>(null)
	let loadError = $state('')
	let waitsText = $state(formatWaits(pkg.retry_waits))
	const waitsValid = $derived(parseWaits(waitsText) !== null)

	onMount(async () => {
		try {
			defaults = await settingsApi.cellPackageDefaults()
		} catch (e) {
			loadError = e instanceof Error ? e.message : 'Could not load the built-in text'
		}
	})

	// a save hands back the settings, so the text box follows them
	$effect(() => {
		const typed = parseWaits(waitsText)
		const current = formatWaits(pkg.retry_waits)
		// only a text that means something else is replaced: one still being typed (or wrong) is left alone
		if (typed !== null && formatWaits(typed) !== current) waitsText = current
	})

	function setWaits(text: string) {
		waitsText = text
		const waits = parseWaits(text)
		if (waits !== null) pkg.retry_waits = waits
	}
</script>

<div class="grid gap-6">
	<p class="text-xs text-muted-foreground">
		Themis adds this to every agent run, on top of the agent's own instructions. It is why a run that cannot do its job stops and
		says why on the ticket, instead of inventing its own way around it. Everything here applies to all agents; leave a text as it is
		to keep the built-in one, which improves with new versions.
	</p>
	{#if loadError}<p class="text-sm text-destructive" role="alert">{loadError}</p>{/if}

	{#if defaults}
		{@const rules = shownText(pkg.rules, defaults.rules)}
		<div class="grid gap-2">
			<div class="flex flex-wrap items-center justify-between gap-2">
				<Label for="package-rules">Rules <span class="font-normal text-muted-foreground">· in every prompt, about {approxTokens(rules)} tokens</span></Label>
				<div class="flex items-center gap-3">
					{#if pkg.rules}
						<Button type="button" variant="ghost" size="sm" class="h-7 gap-1 px-2 text-xs" onclick={() => (pkg.rules = '')}>
							<RotateCcwIcon class="size-3" />Use the built-in text
						</Button>
					{/if}
					<Switch id="package-rules-on" bind:checked={pkg.rules_enabled} aria-label="Rules on" />
				</div>
			</div>
			<Textarea
				id="package-rules"
				rows={6}
				class="font-mono text-xs"
				disabled={!pkg.rules_enabled}
				value={rules}
				oninput={(e) => (pkg.rules = storedText(e.currentTarget.value, defaults!.rules))}
			/>
			<p class="text-xs text-muted-foreground">
				Tells the agent that the container has no root, and to write <code>/cell/blocked.md</code> when it cannot do the task. That file
				is what fails the ticket with a reason and what to do about it. Switched off, agents get none of this and a stuck run is
				only seen as a failed exit code.
			</p>
		</div>

		{@const skill = shownText(pkg.skill, defaults.skill)}
		<div class="grid gap-2">
			<div class="flex flex-wrap items-center justify-between gap-2">
				<Label for="package-skill">Skill <code class="font-mono">themis-cell</code> <span class="font-normal text-muted-foreground">· about {approxTokens(skill)} tokens when read</span></Label>
				<div class="flex items-center gap-3">
					{#if pkg.skill}
						<Button type="button" variant="ghost" size="sm" class="h-7 gap-1 px-2 text-xs" onclick={() => (pkg.skill = '')}>
							<RotateCcwIcon class="size-3" />Use the built-in text
						</Button>
					{/if}
					<Switch id="package-skill-on" bind:checked={pkg.skill_enabled} aria-label="Skill on" />
				</div>
			</div>
			<Textarea
				id="package-skill"
				rows={16}
				class="font-mono text-xs"
				disabled={!pkg.skill_enabled}
				value={skill}
				oninput={(e) => (pkg.skill = storedText(e.currentTarget.value, defaults!.skill))}
			/>
			<p class="text-xs text-muted-foreground">
				A map of the computer an agent has: what is installed and how to use the browser. Only its one-line description is in the
				agent's context until the skill is needed. It is mounted read only in every cell, so agents cannot change it. It describes the
				default image: edit it when your agents use another one. It must keep the name <code>themis-cell</code> and a description.
			</p>
		</div>
	{/if}

	<div class="grid gap-2 sm:max-w-md">
		<Label for="package-waits">Retry when the model provider is busy</Label>
		<Input
			id="package-waits"
			value={waitsText}
			oninput={(e) => setWaits(e.currentTarget.value)}
			placeholder="30, 90, 180"
			class="font-mono"
			aria-invalid={!waitsValid}
		/>
		<p class="text-xs {waitsValid ? 'text-muted-foreground' : 'text-destructive'}">
			{waitsValid
				? 'Seconds to wait before each new try, in order: three numbers mean three retries. Empty means never retry. Only for errors like "model is at capacity", never for a usage limit.'
				: 'Whole numbers of seconds (0 to 3600), at most 10, separated by commas.'}
		</p>
	</div>
</div>
