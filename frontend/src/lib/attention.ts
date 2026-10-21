import type { Task } from './api/tasks'

export type AttentionReason = 'Waiting for review' | 'Last run failed'

export function attentionTasks(tasks: Task[], limit = 5): {
  items: { task: Task; reason: AttentionReason }[]
  total: number
} {
  const items: { task: Task; reason: AttentionReason }[] = []
  for (const task of new Map(tasks.map((task) => [task.id, task])).values()) {
    if (task.status === 'review') {
      items.push({ task, reason: 'Waiting for review' })
    } else if (task.status === 'failed' ||
      (task.status === 'ready' && task.schedule_kind === 'cron' && task.last_attempt_status === 'failed')) {
      items.push({ task, reason: 'Last run failed' })
    }
  }
  // Human decisions come first; recent changes stay visible within each reason.
  items.sort((a, b) =>
    Number(b.task.status === 'review') - Number(a.task.status === 'review') ||
    b.task.updated_at.localeCompare(a.task.updated_at) || a.task.id - b.task.id
  )
  return { items: items.slice(0, Math.max(0, limit)), total: items.length }
}
