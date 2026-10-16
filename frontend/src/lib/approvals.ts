import type { Approval } from './api'

/** Where an approval's run is shown: the workflow editor, with that run open. */
export const approvalHref = (a: Pick<Approval, 'project_id' | 'workflow_id' | 'run_id'>): string =>
  `/projects/${a.project_id}/workflows/${a.workflow_id}/runs/${a.run_id}`

/** What a toast says about approvals that appeared since the last poll. */
export type Announcement = { kind: 'one'; approval: Approval } | { kind: 'many'; count: number } | null

/**
 * The approvals nobody has been told about yet (`seen` holds the ids already announced), as one announcement: a toast for
 * the approval itself when it is the only new one, or a single toast for the lot, so a burst of gates never stacks up a
 * wall of toasts.
 */
export function announce(seen: ReadonlySet<number>, pending: Approval[]): Announcement {
  const fresh = pending.filter((a) => !seen.has(a.id))
  if (fresh.length === 0) return null
  return fresh.length === 1 ? { kind: 'one', approval: fresh[0] } : { kind: 'many', count: fresh.length }
}

/** The first line of what a gate asks (the question is the headline; the rest is read in the panel). */
export const headline = (a: Pick<Approval, 'prompt' | 'label'>): string => a.prompt.trim().split('\n')[0] || a.label
