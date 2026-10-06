"""A project's workflow (the graph drawn in the editor) and the history of its runs."""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from ..deps import CurrentUser, SessionDep
from ..models import NodeStatus, Workflow, WorkflowNodeRun, WorkflowRun, utcnow
from ..workflows import Graph, WorkflowRunner
from .projects import _project

router = APIRouter(tags=["workflows"])


class WorkflowOut(BaseModel):
    graph: Graph
    updated_at: datetime | None


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
        id=run.id, project_id=run.project_id, status=run.status, trigger=run.trigger, outcome=run.outcome,
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


@router.get("/projects/{project_id}/workflow", response_model=WorkflowOut)
async def get_workflow(project_id: int, session: SessionDep, user: CurrentUser) -> WorkflowOut:
    await _project(session, project_id, user)
    wf = await session.scalar(select(Workflow).where(Workflow.project_id == project_id))
    return WorkflowOut(
        graph=Graph.model_validate(wf.graph) if wf else Graph(), updated_at=wf.updated_at if wf else None
    )


@router.put("/projects/{project_id}/workflow", response_model=WorkflowOut)
async def save_workflow(project_id: int, body: Graph, session: SessionDep, user: CurrentUser) -> WorkflowOut:
    await _project(session, project_id, user)
    wf = await session.scalar(select(Workflow).where(Workflow.project_id == project_id))
    if wf is None:
        wf = Workflow(project_id=project_id)
        session.add(wf)
    wf.graph = body.model_dump()
    wf.updated_at = utcnow()
    await session.commit()
    return WorkflowOut(graph=body, updated_at=wf.updated_at)


@router.post(
    "/projects/{project_id}/workflow/runs", response_model=RunDetail, status_code=status.HTTP_201_CREATED
)
async def start_run(project_id: int, request: Request, session: SessionDep, user: CurrentUser) -> RunDetail:
    """Run the saved workflow now, as a test."""
    await _project(session, project_id, user)
    wf = await session.scalar(select(Workflow).where(Workflow.project_id == project_id))
    graph = Graph.model_validate(wf.graph) if wf else Graph()
    if not graph.start_nodes:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "Add a Start node first: a run begins at the Start nodes."
        )
    run_id = await _runner(request).start(project_id, graph)
    await session.commit()  # end this read transaction so the next query sees the run the engine just wrote
    return _detail(await _run(session, run_id, user))


@router.get("/projects/{project_id}/workflow/runs", response_model=list[RunSummary])
async def list_runs(
    project_id: int, session: SessionDep, user: CurrentUser, limit: Annotated[int, Query(ge=1, le=200)] = 50
) -> list[RunSummary]:
    await _project(session, project_id, user)
    runs = (
        await session.scalars(
            select(WorkflowRun)
            .where(WorkflowRun.project_id == project_id)
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
