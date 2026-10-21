// Webhooks: pure helpers for the form and the log (the components do the loading).

import type { DeliveryOutcome, WebhookRule } from './api/webhooks'

/** A rule as the form edits it: the values are one line, separated by commas. */
export interface RuleRow {
  path: string
  values: string
}

export const toRows = (rules: WebhookRule[]): RuleRow[] => rules.map((r) => ({ path: r.path, values: r.equals.join(', ') }))

/** The rules the server stores. A row without a path is one that was added and never filled in. */
export function toRules(rows: RuleRow[]): WebhookRule[] {
  return rows
    .filter((r) => r.path.trim())
    .map((r) => ({
      path: r.path.trim(),
      equals: r.values
        .split(',')
        .map((v) => v.trim())
        .filter(Boolean),
    }))
}

/** The address as the other side needs it: the path the server made, on the address this page was opened from. */
export const addressOf = (path: string, origin: string) => origin.replace(/\/$/, '') + path

/** What happened to a message, in words, and how loudly to say it. */
export const OUTCOMES: Record<DeliveryOutcome, { label: string; tone: 'good' | 'quiet' | 'bad' }> = {
  created: { label: 'Task made', tone: 'good' },
  skipped: { label: 'No task', tone: 'quiet' },
  duplicate: { label: 'Repeat', tone: 'quiet' },
  refused: { label: 'Refused', tone: 'bad' },
}

/** What the test form starts with: the two things every webhook understands without a template. */
export const SAMPLE_MESSAGE = '{\n  "title": "A test message",\n  "description": "Sent from Themis."\n}'

/** The example the setup explains templates with: what GitHub sends when an issue is opened, cut down. */
export const GITHUB_EXAMPLE = {
  title: '{{repository.name}}: {{issue.title}} (#{{issue.number}})',
  description: '{{issue.user.login}} opened {{issue.html_url}}\n\n{{issue.body}}',
  rules: [{ path: 'action', equals: ['opened'] }] as WebhookRule[],
}
