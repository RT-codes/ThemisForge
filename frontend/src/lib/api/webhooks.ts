// Webhooks: addresses that turn a message from another service into a task.

import { request, send } from './core'
import type { Harness, PropertyValue, TaskStatus } from './tasks'

/** A condition on a message: the value at `path` is one of `equals`, or merely there when none are listed */
export interface WebhookRule {
  path: string
  equals: string[]
}

/** An address other programs post to, to make tasks. The sender only supplies the message; the rest is set here. */
export interface Webhook {
  id: number
  project_id: number
  name: string
  enabled: boolean
  /** the last characters of the secret in the address; the rest is only shown when the address is made */
  token_hint: string
  /** null after its board was deleted */
  board_id: number | null
  status: TaskStatus
  title_template: string
  description_template: string
  rules: WebhookRule[]
  harness: Harness
  agent_id: number | null
  workflow_ids: number[]
  properties: Record<string, PropertyValue>
  review_on_success: boolean
  last_received_at: string | null
  created_at: string
  /** why a message would be refused right now; empty when all is well */
  problem: string
}

/** a new address, or a new secret for one: the only time the whole path is known */
export interface WebhookCreated extends Webhook {
  path: string
}

export type WebhookInput = Partial<Omit<Webhook, 'id' | 'project_id' | 'token_hint' | 'last_received_at' | 'created_at' | 'problem'>>

export type DeliveryOutcome = 'created' | 'skipped' | 'duplicate' | 'refused'

export interface WebhookDelivery {
  id: number
  received_at: string
  outcome: DeliveryOutcome
  detail: string
  task_id: number | null
  event: string
  payload: string
}

export interface DeliveryResult {
  outcome: DeliveryOutcome
  detail: string
  task_id: number | null
}

export const webhooksApi = {
  webhooks: (projectId: number) => request<Webhook[]>(`/projects/${projectId}/webhooks`),
  createWebhook: (projectId: number, body: WebhookInput & { name: string }) =>
    request<WebhookCreated>(`/projects/${projectId}/webhooks`, send('POST', body)),
  updateWebhook: (id: number, patch: WebhookInput) => request<Webhook>(`/webhooks/${id}`, send('PATCH', patch)),
  /** a new address; the old one stops working at once */
  newWebhookSecret: (id: number) => request<WebhookCreated>(`/webhooks/${id}/token`, send('POST')),
  deleteWebhook: (id: number) => request<void>(`/webhooks/${id}`, send('DELETE')),
  webhookDeliveries: (id: number) => request<WebhookDelivery[]>(`/webhooks/${id}/deliveries`),
  /** sends the webhook a message of your own; it makes a real task */
  testWebhook: (id: number, body: { payload?: string; event?: string }) => request<DeliveryResult>(`/webhooks/${id}/test`, send('POST', body)),
}
