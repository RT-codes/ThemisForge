<script lang="ts">
	import type { Board } from '$lib/api/projects'
	import type { BuiltinStatus } from '$lib/api/tasks'
	import { statusLabel } from '$lib/boards'
	import { chipStyle } from '$lib/colors'
	import StatusIcon from './StatusIcon.svelte'
	import { cn } from '$lib/utils'

	// `board` names a custom status and gives it its colour; the built-in ones need nothing
	let { status, board = null, class: className }: { status: string; board?: Board | null; class?: string } = $props()

	const styles: Record<BuiltinStatus, string> = {
		backlog: 'bg-muted text-muted-foreground',
		ready: 'bg-tone-sky/15 text-tone-sky',
		running: 'bg-primary/15 text-primary',
		review: 'bg-tone-violet/15 text-tone-violet',
		done: 'bg-tone-green/15 text-tone-green',
		blocked: 'bg-tone-yellow/15 text-tone-yellow',
		failed: 'bg-destructive/15 text-destructive',
	}
	const builtin = $derived(styles[status as BuiltinStatus])
	const column = $derived(board?.columns.find((c) => c.key === status))
	const color = $derived(column?.color ?? undefined)
</script>

<span
	class={cn(
		'inline-flex h-5 items-center gap-1.5 rounded-full px-2 text-xs font-medium whitespace-nowrap',
		builtin ?? (color ? 'border' : 'bg-muted text-muted-foreground'),
		className
	)}
	style={builtin ? undefined : chipStyle(color)}
>
	<StatusIcon {status} icon={column?.icon ?? ''} class={cn('size-3', status === 'running' && 'animate-pulse')} />
	{statusLabel(status, board)}
</span>
