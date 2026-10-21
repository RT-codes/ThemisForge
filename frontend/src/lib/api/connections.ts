// Connections to outside services (see backend/app/connections.py) and the Codex login.

import { request, send } from './core'

export interface ConnectionMethod {
  id: 'token' | 'oauth'
  available: boolean
  reason: string // why it is not available, in words for the person
}

export interface ConnectionField {
  key: string
  label: string
  placeholder: string
  help: string
}

export interface ConnectionProvider {
  id: string
  name: string
  category: string // "ai" | "service"
  description: string
  icon: string // a Lucide icon name
  token_help: string
  harness: string // the harness this is the login of ("claude"), used by all its agents instead of chosen per project
  methods: ConnectionMethod[]
  config_fields: ConnectionField[] // what a project sets on its connection
}

export interface Connection {
  id: number
  provider: string
  method: 'token' | 'oauth'
  account: string
  settings: Record<string, unknown>
  connected_at: string
  checked_at: string | null
  needs_reconnect: boolean // stored, but unreadable (the secret key changed)
}

export interface ConnectionsList {
  secret_key_secure: boolean
  providers: ConnectionProvider[]
  connections: Connection[]
}

export interface ConnectionLogin {
  status: 'starting' | 'waiting' | 'connected' | 'failed' | 'cancelled'
  verification_url: string
  code: string
  expires_at: string | null
  error: string
}

export interface ProjectConnection {
  provider: string
  connection_id: number
  account: string
  config: Record<string, string>
}

export interface CodexLogin {
  status: 'starting' | 'waiting' | 'connected' | 'failed' | 'cancelled'
  verification_url: string
  code: string
  expires_at: string | null
  error: string
}

export interface CodexStatus {
  can_sign_in: boolean // false when this server cannot run the sign in (Docker is missing, or in development no Codex CLI)
  sign_in_problem: string // why, in words for the person
  secret_key_secure: boolean
  connected: boolean
  needs_reconnect: boolean
  account: string
  connected_at: string | null
  refreshed_at: string | null
  login: CodexLogin | null
}

export const connectionsApi = {
  connections: () => request<ConnectionsList>('/connections'),
  connectWithToken: (provider: string, token: string) => request<Connection>('/connections', send('POST', { provider, token })),
  testConnection: (id: number) => request<Connection>(`/connections/${id}/test`, send('POST')),
  disconnect: (id: number) => request<void>(`/connections/${id}`, send('DELETE')),
  startConnectionLogin: (provider: string) => request<ConnectionLogin>(`/connection-logins/${provider}`, send('POST')),
  connectionLogin: (provider: string) => request<ConnectionLogin | null>(`/connection-logins/${provider}`),
  cancelConnectionLogin: (provider: string) => request<void>(`/connection-logins/${provider}`, send('DELETE')),
  projectConnections: (projectId: number) => request<ProjectConnection[]>(`/projects/${projectId}/connections`),
  useConnection: (projectId: number, provider: string, connectionId: number, config: Record<string, string>) =>
    request<ProjectConnection>(`/projects/${projectId}/connections/${provider}`, send('PUT', { connection_id: connectionId, config })),
  stopUsingConnection: (projectId: number, provider: string) => request<void>(`/projects/${projectId}/connections/${provider}`, send('DELETE')),
  codex: () => request<CodexStatus>('/codex'),
  codexStartLogin: () => request<CodexLogin>('/codex/login', send('POST')),
  codexCancelLogin: () => request<void>('/codex/login', send('DELETE')),
  codexDisconnect: () => request<void>('/codex', send('DELETE')),
}
