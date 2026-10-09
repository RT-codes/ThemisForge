<script lang="ts">
	import type { TaskStatus } from '$lib/api'
	import { statusLabel } from '$lib/format'
	import { cn } from '$lib/utils'

	let { status, class: className }: { status: TaskStatus; class?: string } = $props()

	const styles: Record<TaskStatus, string> = {
		backlog: 'bg-muted text-muted-foreground',
		ready: 'bg-sky-500/15 text-sky-300',
		running: 'bg-primary/15 text-primary',
		review: 'bg-violet-500/15 text-violet-300',
		done: 'bg-emerald-500/15 text-emerald-300',
		blocked: 'bg-yellow-500/15 text-yellow-300',
		failed: 'bg-destructive/15 text-destructive',
	}
</script>

<span
	class={cn(
		'inline-flex h-5 items-center gap-1.5 rounded-full px-2 text-xs font-medium whitespace-nowrap',
		styles[status],
		className
	)}
>
	{#if status === 'running'}
		<span class="size-1.5 animate-pulse rounded-full bg-current"></span>
	{/if}
	{statusLabel(status)}
</span>
