// Signing in, access requests and invites (backend/app/routers/auth.py and access.py).

import { request, send } from './core'

export interface User {
  id: number
  email: string
  name: string
  is_admin: boolean
}

export interface AccessRequest {
  id: number
  name: string
  email: string
  reason: string
  status: 'pending' | 'approved' | 'denied'
  created_at: string
  decided_at: string | null
}

export interface Invite {
  id: number
  email: string
  created_at: string
  expires_at: string
}

export interface InviteCreated extends Invite {
  token: string
}

export const authApi = {
  me: () => request<User>('/auth/me'),
  login: (email: string, password: string) => request<User>('/auth/login', send('POST', { email, password })),
  register: (name: string, email: string, password: string) =>
    request<User>('/auth/register', send('POST', { name, email, password })),
  logout: () => request<void>('/auth/logout', send('POST')),
  setup: () => request<{ needs_admin: boolean }>('/auth/setup'),
  requestAccess: (name: string, email: string, reason: string) =>
    request<{ status: string }>('/access-requests', send('POST', { name, email, reason })),
  accessRequests: () => request<AccessRequest[]>('/access-requests'),
  approveRequest: (id: number) => request<InviteCreated>(`/access-requests/${id}/approve`, send('POST')),
  denyRequest: (id: number) => request<AccessRequest>(`/access-requests/${id}/deny`, send('POST')),
  invites: () => request<Invite[]>('/invites'),
  createInvite: (email: string) => request<InviteCreated>('/invites', send('POST', { email })),
  revokeInvite: (id: number) => request<void>(`/invites/${id}`, send('DELETE')),
  checkInvite: (token: string) => request<{ email: string }>(`/invites/by-token/${encodeURIComponent(token)}`),
  acceptInvite: (token: string, name: string, password: string) =>
    request<User>(`/invites/by-token/${encodeURIComponent(token)}/accept`, send('POST', { name, password })),
}
