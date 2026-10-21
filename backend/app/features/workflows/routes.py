from typing import Annotated

from fastapi import APIRouter, Query, Request, status

import app.features.workflows.service as operations
from app.api.dependencies import CurrentUser, SessionDep
from app.features.workflows.schemas import (
    ApprovalOut,
    DecisionIn,
    NodePresetIn,
    NodePresetOut,
    RunDetail,
    RunSummary,
    TaskRunOut,
    WorkflowIn,
    WorkflowOut,
    WorkflowPatch,
    WorkflowSummary,
)
from app.persistence.models import (
    NodePreset,
)

router = APIRouter(tags=["workflows"])


@router.get("/projects/{project_id}/workflows", response_model=list[WorkflowSummary])
async def list_workflows(project_id: int, session: SessionDep, user: CurrentUser) -> list[WorkflowSummary]:
    return await operations.list_workflows(project_id, session, user)


@router.post(
    "/projects/{project_id}/workflows", response_model=WorkflowOut, status_code=status.HTTP_201_CREATED
)
async def create_workflow(
    project_id: int, body: WorkflowIn, session: SessionDep, user: CurrentUser
) -> WorkflowOut:
    """Without a graph a new workflow starts with a Start node, so it can be tested straight away. Without a name it gets
    the first free "Workflow N", so the default names never clash."""

    return await operations.create_workflow(project_id, body, session, user)


@router.get("/projects/{project_id}/node-presets", response_model=list[NodePresetOut])
async def list_node_presets(project_id: int, session: SessionDep, user: CurrentUser) -> list[NodePreset]:
    return await operations.list_node_presets(project_id, session, user)


@router.post(
    "/projects/{project_id}/node-presets", response_model=NodePresetOut, status_code=status.HTTP_201_CREATED
)
async def create_node_preset(
    project_id: int, body: NodePresetIn, session: SessionDep, user: CurrentUser
) -> NodePreset:
    return await operations.create_node_preset(project_id, body, session, user)


@router.delete("/node-presets/{preset_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_node_preset(preset_id: int, session: SessionDep, user: CurrentUser) -> None:
    return await operations.delete_node_preset(preset_id, session, user)


@router.get("/workflows/{workflow_id}", response_model=WorkflowOut)
async def get_workflow(workflow_id: int, session: SessionDep, user: CurrentUser) -> WorkflowOut:
    return await operations.get_workflow(workflow_id, session, user)


@router.patch("/workflows/{workflow_id}", response_model=WorkflowOut)
async def update_workflow(
    workflow_id: int, body: WorkflowPatch, session: SessionDep, user: CurrentUser
) -> WorkflowOut:
    return await operations.update_workflow(workflow_id, body, session, user)


@router.delete("/workflows/{workflow_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_workflow(workflow_id: int, session: SessionDep, user: CurrentUser) -> None:
    return await operations.delete_workflow(workflow_id, session, user)


@router.post("/workflows/{workflow_id}/runs", response_model=RunDetail, status_code=status.HTTP_201_CREATED)
async def start_run(workflow_id: int, request: Request, session: SessionDep, user: CurrentUser) -> RunDetail:
    """Run the saved workflow now, as a test."""

    return await operations.start_run(workflow_id, request.app.state, session, user)


@router.get("/workflows/{workflow_id}/runs", response_model=list[RunSummary])
async def list_runs(
    workflow_id: int, session: SessionDep, user: CurrentUser, limit: Annotated[int, Query(ge=1, le=200)] = 50
) -> list[RunSummary]:
    return await operations.list_runs(workflow_id, session, user, limit)


@router.get("/tasks/{task_id}/workflow-runs", response_model=list[TaskRunOut])
async def task_runs(
    task_id: int, session: SessionDep, user: CurrentUser, limit: Annotated[int, Query(ge=1, le=200)] = 50
) -> list[TaskRunOut]:
    """The workflow runs that this task started by moving into a status, newest first."""

    return await operations.task_runs(task_id, session, user, limit)


@router.get("/workflow-runs/{run_id}", response_model=RunDetail)
async def get_run(run_id: int, session: SessionDep, user: CurrentUser) -> RunDetail:
    return await operations.get_run(run_id, session, user)


@router.post("/workflow-runs/{run_id}/cancel", response_model=RunDetail)
async def cancel_run(run_id: int, request: Request, session: SessionDep, user: CurrentUser) -> RunDetail:
    return await operations.cancel_run(run_id, request.app.state, session, user)


@router.get("/approvals", response_model=list[ApprovalOut])
async def list_approvals(session: SessionDep, user: CurrentUser) -> list[ApprovalOut]:
    """Every open approval of the user's projects, oldest first (the one waiting longest comes first)."""

    return await operations.list_approvals(session, user)


@router.post("/approvals/{approval_id}/decision", status_code=status.HTTP_204_NO_CONTENT)
async def decide_approval(
    approval_id: int, body: DecisionIn, request: Request, session: SessionDep, user: CurrentUser
) -> None:
    """Approve or reject an open gate. The first answer stands; the run carries on (or the node fails) at once."""

    return await operations.decide_approval(approval_id, body, request.app.state, session, user)
