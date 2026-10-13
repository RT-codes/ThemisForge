// What a project still needs before its agents can do their work, for the overview's "Needs setup" strip. It only
// reads what the settings page already shows, so each issue links to the section that fixes it.

import type { Agent, McpServer } from './api'

export interface SetupIssue {
  id: string
  text: string
  href: string
}

export interface SetupInput {
  projectId: number
  agents: Pick<Agent, 'id' | 'name' | 'config_error' | 'connections'>[]
  tools: Pick<McpServer, 'id' | 'name' | 'config_error' | 'sign_in'>[]
  /** the providers (github, ...) the project has a connection for */
  connected: string[]
  /** a provider's name for people ("GitHub"), the id when it is not known */
  providerName: (provider: string) => string
}

const list = (names: string[]) => (names.length <= 2 ? names.join(' and ') : `${names.slice(0, 2).join(', ')} and ${names.length - 2} more`)

export function setupIssues({ projectId, agents, tools, connected, providerName }: SetupInput): SetupIssue[] {
  const settings = `/projects/${projectId}/settings`
  const issues: SetupIssue[] = []

  for (const a of agents) {
    if (a.config_error) {
      issues.push({ id: `agent-${a.id}`, text: `Agent ${a.name} has a problem: ${a.config_error}`, href: `/projects/${projectId}/agents/${a.id}` })
    }
  }

  // one issue per missing connection, naming the agents that want it
  const wanting = new Map<string, string[]>()
  for (const a of agents) {
    for (const provider of a.connections) {
      if (!connected.includes(provider)) wanting.set(provider, [...(wanting.get(provider) ?? []), a.name])
    }
  }
  for (const [provider, names] of wanting) {
    const name = providerName(provider)
    issues.push({
      id: `connection-${provider}`,
      text: `${list(names)} ${names.length === 1 ? 'uses' : 'use'} ${name}, but this project has no ${name} connection`,
      href: `${settings}#connections`,
    })
  }

  for (const t of tools) {
    if (t.config_error) {
      issues.push({ id: `tool-${t.id}`, text: `Tool ${t.name} has a problem: ${t.config_error}`, href: `${settings}#tools` })
    } else if (t.sign_in?.state === 'not_signed_in') {
      issues.push({ id: `tool-${t.id}`, text: `Tool ${t.name} needs you to sign in`, href: `${settings}#tools` })
    } else if (t.sign_in?.state === 'needs_sign_in') {
      issues.push({ id: `tool-${t.id}`, text: `Tool ${t.name} needs a new sign in`, href: `${settings}#tools` })
    }
  }
  return issues
}
