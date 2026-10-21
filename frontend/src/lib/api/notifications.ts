// Where Themis tells people about what happened (backend/app/notifications.py).

import { request, send } from './core'

/** One thing a notification service needs from you (the stored value is never shown again) */
export interface NotificationField {
  name: string
  label: string
  placeholder: string
  help: string
}

/** A service Themis can send messages to; the form is built from `fields`, so a new service needs no new screen */
export interface NotificationKind {
  key: string
  label: string
  description: string
  fields: NotificationField[]
}

export interface NotificationOptions {
  kinds: NotificationKind[]
  /** what a target can listen for, in the order to show them */
  events: { key: string; label: string }[]
}

/** Somewhere a project tells its owner that something happened. The secret (an address, a token) is never returned. */
export interface NotificationTarget {
  id: number
  project_id: number
  name: string
  kind: string
  enabled: boolean
  /** the end of the secret, to tell targets apart */
  hint: string
  events: string[]
  last_sent_at: string | null
  /** empty when the last message went through */
  last_error: string
  created_at: string
}

export interface NotificationInput {
  name: string
  kind: string
  config: Record<string, string>
  events: string[]
  enabled?: boolean
}

export const notificationsApi = {
  notificationOptions: () => request<NotificationOptions>('/notification-options'),
  notifications: (projectId: number) => request<NotificationTarget[]>(`/projects/${projectId}/notifications`),
  createNotification: (projectId: number, body: NotificationInput) =>
    request<NotificationTarget>(`/projects/${projectId}/notifications`, send('POST', body)),
  /** `config` replaces the whole secret; leave it out to keep the one stored */
  updateNotification: (id: number, patch: Partial<NotificationInput>) =>
    request<NotificationTarget>(`/notifications/${id}`, send('PATCH', patch)),
  deleteNotification: (id: number) => request<void>(`/notifications/${id}`, send('DELETE')),
  /** sends the target a message of its own, even when it is switched off */
  testNotification: (id: number) => request<{ ok: boolean; detail: string }>(`/notifications/${id}/test`, send('POST')),
}
