// Agents, their skills and the harnesses they run on (backend/app/routers/agents.py).

import { request, send } from './core'
import type { ProfileOverrides } from './settings'
import type { MountRef } from './volumes'
import type { ModelInfo } from '../models'

export interface Agent {
  id: number
  project_id: number
  name: string
  role: string
  description: string
  instructions: string
  harness: string
  model: string
  reasoning_effort: '' | 'low' | 'medium' | 'high' | 'xhigh' | 'max' | 'ultra'
  cell_profile: ProfileOverrides | null
  mounts: MountRef[]
  skills: string[]
  mcp_servers: number[]
  secrets: number[]
  connections: string[] // providers (github, ...) it may use through the project's connections
  path: string // the agent's file in the project's config folder
  config_error: string // why that file cannot be used right now, "" when it is fine
  created_at: string
  updated_at: string
}

export interface Skill {
  name: string
  description: string
  files: number
}

export interface SkillDetail extends Skill {
  content: string
}

/** a stored key as an agent sees it: never its value, only the variable it is available as */
export interface KeyInfo {
  id: number
  name: string
  kind: string
  env_name: string
}

export interface AgentCheck {
  image: string
  warnings: string[]
}

export type AgentInput = Omit<Agent, 'id' | 'project_id' | 'created_at' | 'updated_at' | 'path' | 'config_error'>

export interface HarnessInfo {
  id: string
  label: string
  description: string
  supports_skills: boolean
  supports_mcp: boolean
  supports_keys: boolean
  models: ModelInfo[] // what the Model dropdown offers; empty when the harness has no model to choose
  default_model: string // what an empty model means: the one in Settings
  default_effort: string
}

export const agentsApi = {
  skills: (projectId: number) => request<Skill[]>(`/projects/${projectId}/skills`),
  skill: (projectId: number, name: string) => request<SkillDetail>(`/projects/${projectId}/skills/${name}`),
  saveSkill: (projectId: number, name: string, content: string) => request<Skill>(`/projects/${projectId}/skills/${name}`, send('PUT', { content })),
  deleteSkill: (projectId: number, name: string) => request<void>(`/projects/${projectId}/skills/${name}`, send('DELETE')),
  keys: () => request<KeyInfo[]>('/keys'),
  checkAgent: (projectId: number, body: { harness: string; cell_profile: ProfileOverrides | null; mcp_servers: number[] }) =>
    request<AgentCheck>(`/projects/${projectId}/agents/check`, send('POST', body)),
  harnesses: () => request<HarnessInfo[]>('/harnesses'),
  agents: (projectId: number) => request<Agent[]>(`/projects/${projectId}/agents`),
  createAgent: (projectId: number, body: AgentInput) => request<Agent>(`/projects/${projectId}/agents`, send('POST', body)),
  updateAgent: (id: number, patch: Partial<AgentInput>) => request<Agent>(`/agents/${id}`, send('PATCH', patch)),
  deleteAgent: (id: number) => request<void>(`/agents/${id}`, send('DELETE')),
}
