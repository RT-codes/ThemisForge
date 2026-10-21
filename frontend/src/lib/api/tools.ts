// Tool (MCP) servers, their sign ins, and the registry they are found in (backend/app/routers/tools.py).

import { request, send } from './core'

export interface McpServer {
  id: number
  project_id: number
  name: string
  description: string
  kind: 'stdio' | 'http'
  command: string
  args: string[]
  url: string
  env: Record<string, string>
  secret_env: Record<string, number>
  bearer_secret_id: number | null
  auth: string // how the server signs people in ('oauth'), '' when it does not ask for a sign in
  sign_in: ToolSignIn | null // where that stands for the project's owner, for a tool that signs in
  path: string // the tool's file in the project's config folder
  config_error: string
  last_test: McpTest | null
  created_at: string
}

/** where a tool that signs in stands: runs use the project owner's sign in (see backend/app/mcp_auth) */
export interface ToolSignIn {
  state: 'signed_in' | 'needs_sign_in' | 'not_signed_in'
  method: string // for people, such as "Sign in with the service"
  login_id: number | null
  account: string // whose workspace or account it is
  error: string // why it needs a new sign in
  expires_at: string | null // when the current token stops working (it is renewed before a run needs it)
}

/** one stored sign in to a tool server, as Settings lists it */
export interface McpLogin {
  id: number
  resource: string
  scheme: string
  status: 'active' | 'needs_sign_in'
  error: string
  account: string
  expires_at: string | null
  refreshed_at: string | null
  connected_at: string
}

/** the outcome of trying a tool: a web tool is connected to, a command is looked up in the image */
export interface McpTest {
  ok: boolean
  message: string
  tools: string[]
  at: string
}

export type McpInput = Omit<McpServer, 'id' | 'project_id' | 'created_at' | 'path' | 'config_error' | 'last_test' | 'sign_in'>

/** something to fill in before a tool from the MCP registry can be made; a secret one is a stored key's id */
export interface RegistryInput {
  id: string
  label: string
  description: string
  required: boolean
  secret: boolean
  choices: string[]
  default: string
}

/** a tool of the MCP registry, with whether this project can run it (and if not, the one reason) */
export interface RegistryTool {
  name: string
  title: string
  description: string
  version: string
  repository: string
  source: 'package' | 'remote' | ''
  runs: string
  command: string
  supported: boolean
  reason: string
  reason_text: string
  inputs: RegistryInput[]
  note: string
  icon: string // an image address to show, or '' to draw the initials
  category: string
  downloads: number | null // npm downloads in the last month, for npm packages that were counted
  updated: string
}

export interface RegistryCategory {
  id: string
  label: string
  count: number
}

/** how the local copy of the registry's catalog is doing; it is built in the background the first time */
export interface RegistryStatus {
  state: 'empty' | 'building' | 'updating' | 'ready' | 'error'
  count: number
  synced_at: string
  error: string
  counting: boolean
}

export interface RegistryPage {
  tools: RegistryTool[]
  total: number
  offset: number
  categories: RegistryCategory[]
  status: RegistryStatus
}

export type RegistrySort = 'recommended' | 'downloads' | 'updated' | 'name'

export interface RegistryQuery {
  q: string
  category: string
  sort: RegistrySort
  supportedOnly: boolean
  offset: number
}

const registryBase = (projectId: number | null) => (projectId === null ? '/mcp-registry' : `/projects/${projectId}/mcp-registry`)

export const toolsApi = {
  mcpServers: (projectId: number) => request<McpServer[]>(`/projects/${projectId}/mcp-servers`),
  createMcpServer: (projectId: number, body: McpInput) => request<McpServer>(`/projects/${projectId}/mcp-servers`, send('POST', body)),
  updateMcpServer: (id: number, body: McpInput) => request<McpServer>(`/mcp-servers/${id}`, send('PUT', body)),
  deleteMcpServer: (id: number) => request<void>(`/mcp-servers/${id}`, send('DELETE')),
  testMcpServer: (id: number) => request<McpTest>(`/mcp-servers/${id}/test`, send('POST')),
  /** where to send the browser to sign in to a tool; the service brings the person back to `returnTo` (a path) */
  mcpSignIn: (id: number, returnTo: string) =>
    request<{ url: string }>(`/mcp-servers/${id}/sign-in`, send('POST', { return_to: returnTo })),
  mcpLogins: () => request<McpLogin[]>('/mcp-auth/logins'),
  mcpSignOut: (id: number) => request<void>(`/mcp-auth/logins/${id}`, send('DELETE')),
  // The registry is browsed from a project (judged by its image) or from Settings, where there is none
  registryTools: (projectId: number | null, query: RegistryQuery) =>
    request<RegistryPage>(
      `${registryBase(projectId)}?` +
        new URLSearchParams({
          q: query.q,
          category: query.category,
          sort: query.sort,
          supported_only: String(query.supportedOnly),
          offset: String(query.offset),
          limit: '30',
        }),
    ),
  registryEntry: (projectId: number | null, name: string) =>
    request<RegistryTool>(`${registryBase(projectId)}/entry?name=${encodeURIComponent(name)}`),
  registryRefresh: (projectId: number | null) => request<RegistryStatus>(`${registryBase(projectId)}/refresh`, send('POST')),
  registryFeatured: (projectId: number | null) => request<RegistryTool[]>(`${registryBase(projectId)}/featured`),
  registryPrefill: (projectId: number | null, name: string, values: Record<string, string>) =>
    request<McpInput>(`${registryBase(projectId)}/prefill`, send('POST', { name, values })),
}
