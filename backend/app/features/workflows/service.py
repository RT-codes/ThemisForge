from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from starlette import status

from app.errors import ApplicationError
from app.features.projects.access import require_project
from app.features.tasks.access import require_task
from app.features.workflows.graph import Graph
from app.features.workflows.runner import WorkflowRunner
from app.features.workflows.schemas import (
    ApprovalOut,
    DecisionIn,
    LastRun,
    NodePresetIn,
    NodeRunOut,
    RunDetail,
    RunSummary,
    TaskRunOut,
    Watch,
    WorkflowIn,
    WorkflowOut,
    WorkflowPatch,
    WorkflowSummary,
)
from app.persistence.models import (
    NodePreset,
    NodeStatus,
    Project,
    RunStatus,
    User,
    Workflow,
    WorkflowNodeRun,
    WorkflowRun,
    utcnow,
)
from app.runtime import Runtime

MAX_NODE_PRESETS = 100  # per project; a palette longer than this is no longer a shortcut


def _runner(runtime: Runtime) -> WorkflowRunner:
    return runtime.workflows


def _detail(run: WorkflowRun) -> RunDetail:
    return RunDetail(
        id=run.id, project_id=run.project_id, workflow_id=run.workflow_id, status=run.status, trigger=run.trigger, outcome=run.outcome,
        started_at=run.started_at, finished_at=run.finished_at, graph=run.graph,
        nodes=[NodeRunOut.model_validate(n) for n in run.nodes],
    )  # fmt: skip


async def _run(session: AsyncSession, run_id: int, user: User) -> WorkflowRun:
    run = await session.scalar(
        select(WorkflowRun)
        .where(WorkflowRun.id == run_id)
        .options(selectinload(WorkflowRun.nodes))
        .execution_options(populate_existing=True)  # always what the engine wrote last, not a cached copy
    )
    if run is None:
        raise ApplicationError(status.HTTP_404_NOT_FOUND, "Run not found")
    await require_project(session, run.project_id, user)  # only the owner may look
    return run


def _out(wf: Workflow) -> WorkflowOut:
    return WorkflowOut(
        id=wf.id, project_id=wf.project_id, name=wf.name, description=wf.description, graph=Graph.model_validate(wf.graph),
        created_at=wf.created_at, updated_at=wf.updated_at,
    )  # fmt: skip


async def _workflow(session: AsyncSession, workflow_id: int, user: User) -> Workflow:
    wf = await session.get(Workflow, workflow_id)
    if wf is None:
        raise ApplicationError(status.HTTP_404_NOT_FOUND, "Workflow not found")
    await require_project(session, wf.project_id, user)  # only the owner of the project may look
    return wf


async def _next_name(session: AsyncSession, project_id: int) -> str:
    """The first "Workflow N" that no workflow of the project uses (case does not matter)."""
    names = (await session.scalars(select(Workflow.name).where(Workflow.project_id == project_id))).all()
    taken = {n.casefold() for n in names}
    n = 1
    while f"workflow {n}" in taken:
        n += 1
    return f"Workflow {n}"


async def list_workflows(project_id: int, session: AsyncSession, user: User) -> list[WorkflowSummary]:
    await require_project(session, project_id, user)
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
            watches=list({(n.config.get("status", ""), n.config.get("where", "")): Watch(status=n.config.get("status", ""), where=n.config.get("where", "")) for n in Graph.model_validate(w.graph).status_triggers()}.values()),
        )
        for w in flows
    ]  # fmt: skip


async def create_workflow(
    project_id: int, body: WorkflowIn, session: AsyncSession, user: User
) -> WorkflowOut:
    """Without a graph a new workflow starts with a Start node, so it can be tested straight away. Without a name it gets
    the first free "Workflow N", so the default names never clash."""
    await require_project(session, project_id, user)
    name = body.name.strip() if body.name else await _next_name(session, project_id)
    start = {"id": "n1", "kind": "start", "label": "Start", "config": {}, "position": {"x": 0, "y": 0}}
    graph = body.graph.model_dump() if body.graph else {"nodes": [start], "edges": []}
    wf = Workflow(project_id=project_id, name=name, description=body.description, graph=graph)
    session.add(wf)
    await session.commit()
    return _out(wf)


async def list_node_presets(project_id: int, session: AsyncSession, user: User) -> list[NodePreset]:
    await require_project(session, project_id, user)
    query = select(NodePreset).where(NodePreset.project_id == project_id).order_by(NodePreset.id)
    return list((await session.scalars(query)).all())


async def create_node_preset(
    project_id: int, body: NodePresetIn, session: AsyncSession, user: User
) -> NodePreset:
    await require_project(session, project_id, user)
    count = await session.scalar(
        select(func.count()).select_from(NodePreset).where(NodePreset.project_id == project_id)
    )
    if (count or 0) >= MAX_NODE_PRESETS:
        raise ApplicationError(
            status.HTTP_409_CONFLICT,
            f"A project keeps at most {MAX_NODE_PRESETS} saved nodes. Remove one first.",
        )
    preset = NodePreset(project_id=project_id, kind=body.kind, label=body.label.strip(), config=body.config)
    session.add(preset)
    await session.commit()
    return preset


async def delete_node_preset(preset_id: int, session: AsyncSession, user: User) -> None:
    preset = await session.get(NodePreset, preset_id)
    if preset is None:
        raise ApplicationError(status.HTTP_404_NOT_FOUND, "Saved node not found")
    await require_project(session, preset.project_id, user)  # only the owner of the project may look
    await session.delete(preset)
    await session.commit()


async def get_workflow(workflow_id: int, session: AsyncSession, user: User) -> WorkflowOut:
    return _out(await _workflow(session, workflow_id, user))


async def update_workflow(
    workflow_id: int, body: WorkflowPatch, session: AsyncSession, user: User
) -> WorkflowOut:
    wf = await _workflow(session, workflow_id, user)
    fields = body.model_fields_set
    if "name" in fields and body.name is not None:
        if not (name := body.name.strip()):
            raise ApplicationError(status.HTTP_422_UNPROCESSABLE_CONTENT, "The name cannot be empty")
        wf.name = name
    if "description" in fields and body.description is not None:
        wf.description = body.description
    if "graph" in fields and body.graph is not None:
        wf.graph = body.graph.model_dump()
    wf.updated_at = utcnow()
    await session.commit()
    return _out(wf)


async def delete_workflow(workflow_id: int, session: AsyncSession, user: User) -> None:
    wf = await _workflow(session, workflow_id, user)
    running = await session.scalar(
        select(func.count())
        .select_from(WorkflowRun)
        .where(WorkflowRun.workflow_id == wf.id, WorkflowRun.status == "running")
    )
    if running:
        raise ApplicationError(status.HTTP_409_CONFLICT, "This workflow is running. Cancel its run first.")
    await session.delete(wf)  # its runs go with it; tasks that played it keep existing, with nothing to play
    await session.commit()


async def start_run(workflow_id: int, runtime: Runtime, session: AsyncSession, user: User) -> RunDetail:
    """Run the saved workflow now, as a test."""
    wf = await _workflow(session, workflow_id, user)
    graph = Graph.model_validate(wf.graph)
    if not graph.start_nodes:
        raise ApplicationError(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "Add a Start node first: a run begins at the Start nodes."
        )
    if (project := await session.get(Project, wf.project_id)) and project.halted_at is not None:
        raise ApplicationError(status.HTTP_409_CONFLICT, "This project is halted. Resume it first.")
    run_id = await _runner(runtime).start(wf.project_id, wf.id, graph)
    await session.commit()  # end this read transaction so the next query sees the run the engine just wrote
    return _detail(await _run(session, run_id, user))


async def list_runs(workflow_id: int, session: AsyncSession, user: User, limit: int = 50) -> list[RunSummary]:
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


async def task_runs(task_id: int, session: AsyncSession, user: User, limit: int = 50) -> list[TaskRunOut]:
    """The workflow runs that this task started by moving into a status, newest first."""
    await require_task(session, task_id, user)
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


async def get_run(run_id: int, session: AsyncSession, user: User) -> RunDetail:
    return _detail(await _run(session, run_id, user))


async def cancel_run(run_id: int, runtime: Runtime, session: AsyncSession, user: User) -> RunDetail:
    run = await _run(session, run_id, user)
    if not await _runner(runtime).cancel(run.id):
        raise ApplicationError(status.HTTP_409_CONFLICT, "This run is not running")
    await session.commit()  # same: look again at what the engine wrote while cancelling
    return _detail(await _run(session, run_id, user))


async def list_approvals(session: AsyncSession, user: User) -> list[ApprovalOut]:
    """Every open approval of the user's projects, oldest first (the one waiting longest comes first)."""
    rows = await session.execute(
        select(WorkflowNodeRun, WorkflowRun, Workflow.name, Project.name)
        .join(WorkflowRun, WorkflowRun.id == WorkflowNodeRun.run_id)
        .join(Workflow, Workflow.id == WorkflowRun.workflow_id)
        .join(Project, Project.id == WorkflowRun.project_id)
        .where(
            WorkflowNodeRun.status == NodeStatus.WAITING,
            WorkflowNodeRun.decision == "",
            WorkflowRun.status == RunStatus.RUNNING,
            Project.owner_id == user.id,
        )
        .order_by(WorkflowNodeRun.started_at, WorkflowNodeRun.id)
    )
    out = []
    for node, run, workflow_name, project_name in rows:
        gate = node.gate or {}
        previous = gate.get("previous") or {}
        out.append(
            ApprovalOut(
                id=node.id, run_id=run.id, project_id=run.project_id, project_name=project_name,
                workflow_id=run.workflow_id, workflow_name=workflow_name, label=node.label,
                prompt=gate.get("prompt", ""), previous_label=previous.get("label", ""),
                previous=previous.get("result", ""), waiting_since=node.started_at or run.started_at,
            )
        )  # fmt: skip
    return out


async def decide_approval(
    approval_id: int, body: DecisionIn, runtime: Runtime, session: AsyncSession, user: User
) -> None:
    """Approve or reject an open gate. The first answer stands; the run carries on (or the node fails) at once."""
    node = await session.get(WorkflowNodeRun, approval_id)
    run = await session.get(WorkflowRun, node.run_id) if node else None
    project = await session.get(Project, run.project_id) if run else None
    if node is None or node.kind != "approval" or project is None or project.owner_id != user.id:
        raise ApplicationError(status.HTTP_404_NOT_FOUND, "Approval not found")
    if not _runner(runtime).is_live(run.id):
        raise ApplicationError(status.HTTP_409_CONFLICT, "This run is no longer going")
    if not await _runner(runtime).decide(node.id, body.approved, body.note.strip(), user.name):
        raise ApplicationError(status.HTTP_409_CONFLICT, "This approval was already answered")
