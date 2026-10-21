from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.features.workflows.graph import Graph, Kind, NodeConfig


class WorkflowOut(BaseModel):
    id: int
    project_id: int
    name: str
    description: str
    graph: Graph
    created_at: datetime
    updated_at: datetime


class LastRun(BaseModel):
    id: int
    status: str
    started_at: datetime


class Watch(BaseModel):
    status: str
    where: str


class WorkflowSummary(BaseModel):
    id: int
    project_id: int
    name: str
    description: str
    node_count: int
    created_at: datetime
    updated_at: datetime
    runs: int
    last_run: LastRun | None
    # what starts this workflow by itself (its Triggers): a status, and where ("" anywhere, "w:<id>" a workspace, "b:<id>"
    # a board); empty for a manual workflow
    watches: list[Watch]


class WorkflowIn(BaseModel):
    name: str | None = Field(
        default=None, min_length=1, max_length=100
    )  # left out: "Workflow 1", "Workflow 2"...
    description: str = Field(default="", max_length=2000)
    graph: Graph | None = None  # left out: a graph with just a Start node


class WorkflowPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=2000)
    graph: Graph | None = None


class NodeRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    node_id: str
    kind: str
    label: str
    seq: int
    status: str
    started_at: datetime | None
    finished_at: datetime | None
    log: str
    result: str
    error: str
    task_id: int | None
    attempt_id: int | None
    # an approval gate: what it asks and what it was told ("" while it is open), see WorkflowNodeRun.gate
    gate: dict[str, Any] | None
    decision: str
    decision_note: str
    decided_by: str


class RunSummary(BaseModel):
    id: int
    status: str
    trigger: str
    outcome: str
    started_at: datetime
    finished_at: datetime | None
    nodes_total: int
    nodes_succeeded: int
    nodes_failed: int


class RunDetail(BaseModel):
    id: int
    project_id: int
    workflow_id: int
    status: str
    trigger: str
    outcome: str
    started_at: datetime
    finished_at: datetime | None
    graph: dict[str, Any]  # as it was when the run began, so a viewer can tell what comes after a node
    nodes: list[NodeRunOut]


class NodePresetIn(BaseModel):
    kind: Kind
    label: str = Field(default="", max_length=100)
    config: NodeConfig = Field(default_factory=dict)


class NodePresetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    kind: Kind
    label: str
    config: NodeConfig
    created_at: datetime


class TaskRunOut(BaseModel):
    id: int
    workflow_id: int
    workflow_name: str
    status: str
    outcome: str
    started_at: datetime
    finished_at: datetime | None


class ApprovalOut(BaseModel):
    id: int  # the gate's node run: what the decision is sent to
    run_id: int
    project_id: int
    project_name: str
    workflow_id: int
    workflow_name: str
    label: str
    prompt: str  # what the gate asks, as the workflow's author wrote it
    previous_label: str  # the node before the gate...
    previous: str  # ...and what it produced: the thing to approve
    waiting_since: datetime


class DecisionIn(BaseModel):
    approved: bool
    note: str = Field(default="", max_length=2000)
