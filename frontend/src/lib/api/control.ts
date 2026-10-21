// Keys that let an agent control Themis over MCP (backend/app/control.py).

import { request, send } from './core'

/** a key an outside agent holds to use one project through MCP; the secret is only in ControlConnect */
/** what a connection may do, each including the one before: look, run the project's work, set the project up */
export type ControlScope = 'read' | 'write' | 'manage'

export interface ControlToken {
  id: number
  /** the one project it reaches; null: all of the owner's projects */
  project_id: number | null
  name: string
  scope: ControlScope
  /** the last characters of the secret, to tell tokens apart */
  token_hint: string
  last_used_at: string | null
  created_at: string
}

/** everything pasted into an agent to connect it, secret included */
export interface ControlConnect {
  url: string
  token: string
  /** the command that adds this project to Claude Code */
  claude_code: string
  /** the same for clients that read an mcpServers file */
  config_json: string
}

export const controlApi = {
  controlTokens: (projectId: number) => request<ControlToken[]>(`/projects/${projectId}/control/tokens`),
  createControlToken: (projectId: number, body: { name: string; scope?: ControlScope }) =>
    request<ControlToken>(`/projects/${projectId}/control/tokens`, send('POST', body)),
  /** the keys that reach all of the user's projects (and, for an administrator, the global settings) */
  accountControlTokens: () => request<ControlToken[]>('/control/tokens'),
  createAccountControlToken: (body: { name: string; scope?: ControlScope }) =>
    request<ControlToken>('/control/tokens', send('POST', body)),
  /** the command and config that connect an agent; can be asked for again at any time */
  controlConnect: (id: number) => request<ControlConnect>(`/control/tokens/${id}/connect`),
  deleteControlToken: (id: number) => request<void>(`/control/tokens/${id}`, send('DELETE')),
}
