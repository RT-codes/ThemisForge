// Workflows, their runs and the approval gates in them.

import { request, send } from './core'
import type { TaskStatus } from './tasks'
import type { Graph } from '../workflow'
import type { NodeKind } from '../workflow'

export type RunStatus = 'running' | 'succeeded' | 'failed' | 'cancelled'

/** 'waiting' is an approval gate that has not been answered yet */
export type NodeRunStatus = 'running' | 'succeeded' | 'failed' | 'skipped' | 'cancelled' | 'waiting'

export interface NodeRun {
  id: number
  node_id: string
  kind: NodeKind
  label: string
  seq: number
  status: NodeRunStatus
  started_at: string | null
  finished_at: string | null
  log: string
  result: string
  error: string
  task_id: number | null
  attempt_id: number | null
  /** an approval gate: what it asks, and how it was answered ('' while it is open) */
  gate: { prompt: string } | null
  decision: '' | 'approved' | 'rejected'
  decision_note: string
  decided_by: string
}

/** a workflow run parked at an approval gate, waiting for a person */
export interface Approval {
  /** the gate's record in the run: what the decision is sent to */
  id: number
  run_id: number
  project_id: number
  project_name: string
  workflow_id: number
  workflow_name: string
  label: string
  prompt: string
  /** the step before the gate, and what it produced: the thing to approve */
  previous_label: string
  previous: string
  waiting_since: string
}

export interface WorkflowSummary {
  id: number
  project_id: number
  name: string
  description: string
  node_count: number
  created_at: string
  updated_at: string
  runs: number
  last_run: { id: number; status: RunStatus; started_at: string } | null
  /** the statuses whose tasks start this workflow by themselves; empty for one that is only run by hand */
  /** what starts it by itself: a status and where ("" anywhere, "w:<id>" a workspace, "b:<id>" a board) */
  watches: { status: TaskStatus; where: string }[]
}

export interface TaskWorkflowRunSummary {
  id: number
  workflow_id: number
  workflow_name: string
  status: RunStatus
  outcome: string
  started_at: string
  finished_at: string | null
}

export interface WorkflowDetail {
  id: number
  project_id: number
  name: string
  description: string
  graph: Graph
  created_at: string
  updated_at: string
}

/** a configured node a project keeps in the editor's palette */
export interface NodePreset {
  id: number
  kind: NodeKind
  label: string
  config: Record<string, string>
  created_at: string
}

export interface WorkflowRunSummary {
  id: number
  status: RunStatus
  trigger: string
  outcome: string
  started_at: string
  finished_at: string | null
  nodes_total: number
  nodes_succeeded: number
  nodes_failed: number
}

export interface WorkflowRunDetail {
  id: number
  project_id: number
  workflow_id: number
  status: RunStatus
  trigger: string
  outcome: string
  started_at: string
  finished_at: string | null
  /** the graph as it was when the run began */
  graph: Graph
  nodes: NodeRun[]
}

export const workflowsApi = {
  workflows: (projectId: number) => request<WorkflowSummary[]>(`/projects/${projectId}/workflows`),
  createWorkflow: (projectId: number, body: { name?: string; graph?: Graph } = {}) => request<WorkflowDetail>(`/projects/${projectId}/workflows`, send('POST', body)),
  workflow: (id: number) => request<WorkflowDetail>(`/workflows/${id}`),
  updateWorkflow: (id: number, patch: { name?: string; description?: string; graph?: Graph }) => request<WorkflowDetail>(`/workflows/${id}`, send('PATCH', patch)),
  deleteWorkflow: (id: number) => request<void>(`/workflows/${id}`, send('DELETE')),
  nodePresets: (projectId: number) => request<NodePreset[]>(`/projects/${projectId}/node-presets`),
  createNodePreset: (projectId: number, body: { kind: NodeKind; label: string; config: Record<string, string> }) => request<NodePreset>(`/projects/${projectId}/node-presets`, send('POST', body)),
  deleteNodePreset: (id: number) => request<void>(`/node-presets/${id}`, send('DELETE')),
  startWorkflowRun: (workflowId: number) => request<WorkflowRunDetail>(`/workflows/${workflowId}/runs`, send('POST')),
  taskWorkflowRuns: (taskId: number) => request<TaskWorkflowRunSummary[]>(`/tasks/${taskId}/workflow-runs`),
  workflowRuns: (workflowId: number) => request<WorkflowRunSummary[]>(`/workflows/${workflowId}/runs`),
  workflowRun: (id: number) => request<WorkflowRunDetail>(`/workflow-runs/${id}`),
  cancelWorkflowRun: (id: number) => request<WorkflowRunDetail>(`/workflow-runs/${id}/cancel`, send('POST')),
  approvals: () => request<Approval[]>('/approvals'),
  decideApproval: (id: number, approved: boolean, note: string) => request<void>(`/approvals/${id}/decision`, send('POST', { approved, note })),
}
