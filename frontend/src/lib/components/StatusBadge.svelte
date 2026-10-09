<script lang="ts">
	import type { Board, BuiltinStatus } from '$lib/api'
	import { statusLabel } from '$lib/boards'
	import { chipStyle } from '$lib/colors'
	import { cn } from '$lib/utils'

	// `board` names a custom status and gives it its colour; the built-in ones need nothing
	let { status, board = null, class: className }: { status: string; board?: Board | null; class?: string } = $props()

	const styles: Record<BuiltinStatus, string> = {
		backlog: 'bg-muted text-muted-foreground',
		ready: 'bg-sky-500/15 text-sky-300',
		running: 'bg-primary/15 text-primary',
		review: 'bg-violet-500/15 text-violet-300',
		done: 'bg-emerald-500/15 text-emerald-300',
		blocked: 'bg-yellow-500/15 text-yellow-300',
		failed: 'bg-destructive/15 text-destructive',
	}
	const builtin = $derived(styles[status as BuiltinStatus])
	const color = $derived(board?.columns.find((c) => c.key === status)?.color ?? undefined)
</script>

<span
	class={cn(
		'inline-flex h-5 items-center gap-1.5 rounded-full px-2 text-xs font-medium whitespace-nowrap',
		builtin ?? (color ? 'border' : 'bg-muted text-muted-foreground'),
		className
	)}
	style={builtin ? undefined : chipStyle(color)}
>
	{#if status === 'running'}
		<span class="size-1.5 animate-pulse rounded-full bg-current"></span>
	{/if}
	{statusLabel(status, board)}
</span>
