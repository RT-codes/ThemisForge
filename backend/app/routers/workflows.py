"""A project's workflow (the graph drawn in the editor) and the history of its runs."""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from ..deps import CurrentUser, SessionDep
from ..models import NodeStatus, Workflow, WorkflowNodeRun, WorkflowRun, utcnow
from ..workflows import Graph, WorkflowRunner
from .projects import _project, _task

router = APIRouter(tags=["workflows"])


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
    # the statuses whose tasks start this workflow by themselves (its Triggers); empty for a manual workflow
    watches: list[str]


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
    nodes: list[NodeRunOut]


def _runner(request: Request) -> WorkflowRunner:
    return request.app.state.workflows


def _detail(run: WorkflowRun) -> RunDetail:
    return RunDetail(
        id=run.id, project_id=run.project_id, workflow_id=run.workflow_id, status=run.status, trigger=run.trigger, outcome=run.outcome,
        started_at=run.started_at, finished_at=run.finished_at, nodes=[NodeRunOut.model_validate(n) for n in run.nodes],
    )  # fmt: skip


async def _run(session: SessionDep, run_id: int, user: CurrentUser) -> WorkflowRun:
    run = await session.scalar(
        select(WorkflowRun)
        .where(WorkflowRun.id == run_id)
        .options(selectinload(WorkflowRun.nodes))
        .execution_options(populate_existing=True)  # always what the engine wrote last, not a cached copy
    )
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Run not found")
    await _project(session, run.project_id, user)  # only the owner may look
    return run


def _out(wf: Workflow) -> WorkflowOut:
    return WorkflowOut(
        id=wf.id, project_id=wf.project_id, name=wf.name, description=wf.description, graph=Graph.model_validate(wf.graph),
        created_at=wf.created_at, updated_at=wf.updated_at,
    )  # fmt: skip


async def _workflow(session: SessionDep, workflow_id: int, user: CurrentUser) -> Workflow:
    wf = await session.get(Workflow, workflow_id)
    if wf is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Workflow not found")
    await _project(session, wf.project_id, user)  # only the owner of the project may look
    return wf


async def _next_name(session: SessionDep, project_id: int) -> str:
    """The first "Workflow N" that no workflow of the project uses (case does not matter)."""
    names = (await session.scalars(select(Workflow.name).where(Workflow.project_id == project_id))).all()
    taken = {n.casefold() for n in names}
    n = 1
    while f"workflow {n}" in taken:
        n += 1
    return f"Workflow {n}"


@router.get("/projects/{project_id}/workflows", response_model=list[WorkflowSummary])
async def list_workflows(project_id: int, session: SessionDep, user: CurrentUser) -> list[WorkflowSummary]:
    await _project(session, project_id, user)
    flows = (
        await session.scalars(
            select(Workflow).where(Workflow.project_id == project_id).order_by(Workflow.name, Workflow.id)
        )
    ).all()
    run_counts = dict(
        (
            await session.execute(
                select(WorkflowRun.workflow_id, func.count())
                .where(WorkflowRun.project_id == project_id)
                .group_by(WorkflowRun.workflow_id)
            )
        ).all()
    )
    newest = (
        select(func.max(WorkflowRun.id))
        .where(WorkflowRun.project_id == project_id)
        .group_by(WorkflowRun.workflow_id)
    )
    last = {
        r.workflow_id: LastRun(id=r.id, status=r.status, started_at=r.started_at)
        for r in (await session.scalars(select(WorkflowRun).where(WorkflowRun.id.in_(newest)))).all()
    }
    return [
        WorkflowSummary(
            id=w.id, project_id=w.project_id, name=w.name, description=w.description, node_count=len(w.graph.get("nodes", [])),
            created_at=w.created_at, updated_at=w.updated_at, runs=run_counts.get(w.id, 0), last_run=last.get(w.id),
            watches=list(dict.fromkeys(n.config.get("status", "") for n in Graph.model_validate(w.graph).status_triggers())),
        )
        for w in flows
    ]  # fmt: skip


@router.post(
    "/projects/{project_id}/workflows", response_model=WorkflowOut, status_code=status.HTTP_201_CREATED
)
async def create_workflow(
    project_id: int, body: WorkflowIn, session: SessionDep, user: CurrentUser
) -> WorkflowOut:
    """Without a graph a new workflow starts with a Start node, so it can be tested straight away. Without a name it gets
    the first free "Workflow N", so the default names never clash."""
    await _project(session, project_id, user)
    name = body.name.strip() if body.name else await _next_name(session, project_id)
    start = {"id": "n1", "kind": "start", "label": "Start", "config": {}, "position": {"x": 0, "y": 0}}
    graph = body.graph.model_dump() if body.graph else {"nodes": [start], "edges": []}
    wf = Workflow(project_id=project_id, name=name, description=body.description, graph=graph)
    session.add(wf)
    await session.commit()
    return _out(wf)


@router.get("/workflows/{workflow_id}", response_model=WorkflowOut)
async def get_workflow(workflow_id: int, session: SessionDep, user: CurrentUser) -> WorkflowOut:
    return _out(await _workflow(session, workflow_id, user))


@router.patch("/workflows/{workflow_id}", response_model=WorkflowOut)
async def update_workflow(
    workflow_id: int, body: WorkflowPatch, session: SessionDep, user: CurrentUser
) -> WorkflowOut:
    wf = await _workflow(session, workflow_id, user)
    fields = body.model_fields_set
    if "name" in fields and body.name is not None:
        if not (name := body.name.strip()):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "The name cannot be empty")
        wf.name = name
    if "description" in fields and body.description is not None:
        wf.description = body.description
    if "graph" in fields and body.graph is not None:
        wf.graph = body.graph.model_dump()
    wf.updated_at = utcnow()
    await session.commit()
    return _out(wf)


@router.delete("/workflows/{workflow_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_workflow(workflow_id: int, session: SessionDep, user: CurrentUser) -> None:
    wf = await _workflow(session, workflow_id, user)
    running = await session.scalar(
        select(func.count())
        .select_from(WorkflowRun)
        .where(WorkflowRun.workflow_id == wf.id, WorkflowRun.status == "running")
    )
    if running:
        raise HTTPException(status.HTTP_409_CONFLICT, "This workflow is running. Cancel its run first.")
    await session.delete(wf)  # its runs go with it; tasks that played it keep existing, with nothing to play
    await session.commit()


@router.post("/workflows/{workflow_id}/runs", response_model=RunDetail, status_code=status.HTTP_201_CREATED)
async def start_run(workflow_id: int, request: Request, session: SessionDep, user: CurrentUser) -> RunDetail:
    """Run the saved workflow now, as a test."""
    wf = await _workflow(session, workflow_id, user)
    graph = Graph.model_validate(wf.graph)
    if not graph.start_nodes:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "Add a Start node first: a run begins at the Start nodes."
        )
    run_id = await _runner(request).start(wf.project_id, wf.id, graph)
    await session.commit()  # end this read transaction so the next query sees the run the engine just wrote
    return _detail(await _run(session, run_id, user))


@router.get("/workflows/{workflow_id}/runs", response_model=list[RunSummary])
async def list_runs(
    workflow_id: int, session: SessionDep, user: CurrentUser, limit: Annotated[int, Query(ge=1, le=200)] = 50
) -> list[RunSummary]:
    await _workflow(session, workflow_id, user)
    runs = (
        await session.scalars(
            select(WorkflowRun)
            .where(WorkflowRun.workflow_id == workflow_id)
            .order_by(WorkflowRun.id.desc())
            .limit(limit)
        )
    ).all()
    counts: dict[int, dict[str, int]] = {}
    if runs:
        rows = await session.execute(
            select(WorkflowNodeRun.run_id, WorkflowNodeRun.status, func.count())
            .where(WorkflowNodeRun.run_id.in_([r.id for r in runs]))
            .group_by(WorkflowNodeRun.run_id, WorkflowNodeRun.status)
        )
        for run_id, node_status, n in rows:
            counts.setdefault(run_id, {})[node_status] = n
    return [
        RunSummary(
            id=r.id, status=r.status, trigger=r.trigger, outcome=r.outcome, started_at=r.started_at, finished_at=r.finished_at,
            nodes_total=sum(counts.get(r.id, {}).values()),
            nodes_succeeded=counts.get(r.id, {}).get(NodeStatus.SUCCEEDED, 0),
            nodes_failed=counts.get(r.id, {}).get(NodeStatus.FAILED, 0),
        )
        for r in runs
    ]  # fmt: skip


class TaskRunOut(BaseModel):
    id: int
    workflow_id: int
    workflow_name: str
    status: str
    outcome: str
    started_at: datetime
    finished_at: datetime | None


@router.get("/tasks/{task_id}/workflow-runs", response_model=list[TaskRunOut])
async def task_runs(
    task_id: int, session: SessionDep, user: CurrentUser, limit: Annotated[int, Query(ge=1, le=200)] = 50
) -> list[TaskRunOut]:
    """The workflow runs that this task started by moving into a status, newest first."""
    await _task(session, task_id, user)
    rows = await session.execute(
        select(WorkflowRun, Workflow.name)
        .join(Workflow, Workflow.id == WorkflowRun.workflow_id)
        .where(WorkflowRun.trigger_task_id == task_id)
        .order_by(WorkflowRun.id.desc())
        .limit(limit)
    )
    return [
        TaskRunOut(
            id=r.id, workflow_id=r.workflow_id, workflow_name=name, status=r.status, outcome=r.outcome,
            started_at=r.started_at, finished_at=r.finished_at,
        )
        for r, name in rows
    ]  # fmt: skip


@router.get("/workflow-runs/{run_id}", response_model=RunDetail)
async def get_run(run_id: int, session: SessionDep, user: CurrentUser) -> RunDetail:
    return _detail(await _run(session, run_id, user))


@router.post("/workflow-runs/{run_id}/cancel", response_model=RunDetail)
async def cancel_run(run_id: int, request: Request, session: SessionDep, user: CurrentUser) -> RunDetail:
    run = await _run(session, run_id, user)
    if not await _runner(request).cancel(run.id):
        raise HTTPException(status.HTTP_409_CONFLICT, "This run is not running")
    await session.commit()  # same: look again at what the engine wrote while cancelling
    return _detail(await _run(session, run_id, user))
