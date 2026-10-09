from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..app_settings import load_settings
from ..deps import CurrentUser, SessionDep
from ..models import (
    Agent,
    Attempt,
    AttemptStatus,
    NodeStatus,
    Project,
    ProjectEvent,
    RunStatus,
    ScheduleKind,
    Task,
    TaskStatus,
    Workflow,
    WorkflowNodeRun,
    WorkflowRun,
    utcnow,
)
from ..properties import clean_values, validate_definitions
from ..scheduling import cron_occurrences, refresh_next_run
from ..schemas import (
    AttemptDetail,
    AttemptOut,
    ProjectEventOut,
    ProjectIn,
    ProjectOut,
    ProjectPatch,
    ProjectSummary,
    ScheduledRun,
    TaskIn,
    TaskOut,
    TaskPatch,
    TaskSnapshot,
    TaskWorkflowRun,
    check_schedule,
)

router = APIRouter(tags=["projects"])


# helpers


async def _project(session: AsyncSession, project_id: int, user: CurrentUser) -> Project:
    project = await session.get(Project, project_id)
    if project is None or project.owner_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Project not found")
    return project


async def _task(session: AsyncSession, task_id: int, user: CurrentUser) -> Task:
    task = await session.get(Task, task_id)
    project = await session.get(Project, task.project_id) if task else None
    if task is None or project is None or project.owner_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Task not found")
    return task


async def _task_out(session: AsyncSession, tasks: list[Task]) -> list[TaskOut]:
    """Tasks plus the status of their latest attempt (one query for all of them)."""
    latest: dict[int, AttemptStatus] = {}
    if tasks:
        newest = (
            select(func.max(Attempt.id))
            .where(Attempt.task_id.in_([t.id for t in tasks]))
            .group_by(Attempt.task_id)
        )
        rows = await session.execute(select(Attempt.task_id, Attempt.status).where(Attempt.id.in_(newest)))
        latest = {task_id: AttemptStatus(attempt_status) for task_id, attempt_status in rows}
    running = await _running_workflow_runs(session, [t.id for t in tasks])
    out = []
    for t in tasks:
        item = TaskOut.model_validate(t)
        item.last_attempt_status = latest.get(t.id)
        item.workflow_run = running.get(t.id)
        out.append(item)
    return out


async def _running_workflow_runs(session: AsyncSession, task_ids: list[int]) -> dict[int, TaskWorkflowRun]:
    """For each task, the workflow run it started that is still going (the newest, if there are several)."""
    if not task_ids:
        return {}
    rows = await session.execute(
        select(WorkflowRun.trigger_task_id, WorkflowRun.id, WorkflowRun.workflow_id, Workflow.name)
        .join(Workflow, Workflow.id == WorkflowRun.workflow_id)
        .where(WorkflowRun.trigger_task_id.in_(task_ids), WorkflowRun.status == RunStatus.RUNNING)
        .order_by(WorkflowRun.id)  # a later run overwrites an earlier one below
    )
    runs = {task_id: (run_id, wf_id, name) for task_id, run_id, wf_id, name in rows}
    if not runs:
        return {}
    steps = dict(
        (
            await session.execute(
                select(WorkflowNodeRun.run_id, WorkflowNodeRun.label)
                .where(
                    WorkflowNodeRun.run_id.in_([r[0] for r in runs.values()]),
                    WorkflowNodeRun.status == NodeStatus.RUNNING,
                )
                .order_by(WorkflowNodeRun.id)
            )
        ).all()
    )
    return {
        task_id: TaskWorkflowRun(
            run_id=run_id, workflow_id=wf_id, workflow_name=name, step=steps.get(run_id, "")
        )
        for task_id, (run_id, wf_id, name) in runs.items()
    }


async def _next_position(session: AsyncSession, project_id: int, status_: str) -> float:
    top = await session.scalar(
        select(func.max(Task.position)).where(Task.project_id == project_id, Task.status == status_)
    )
    return (top or 0.0) + 1.0


def _bad(detail: str) -> HTTPException:
    return HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail)


async def _workflow_for(
    session: AsyncSession, project_id: int, harness: str, workflow_id: int | None
) -> int | None:
    """The workflow a task may play: only when it runs with one, and only one from its own project."""
    if harness != "workflow":
        return None
    if workflow_id is None:
        raise _bad("Choose the workflow this task should play")
    wf = await session.get(Workflow, workflow_id)
    if wf is None or wf.project_id != project_id:
        raise _bad("That workflow does not exist in this project")
    return workflow_id


# projects


async def _agent_for(session: AsyncSession, project_id: int, agent_id: int) -> Agent:
    agent = await session.get(Agent, agent_id)
    if agent is None or agent.project_id != project_id:
        raise _bad("That agent does not exist in this project")
    return agent


@router.get("/projects", response_model=list[ProjectSummary])
async def list_projects(session: SessionDep, user: CurrentUser) -> list[ProjectSummary]:
    projects = (
        await session.scalars(select(Project).where(Project.owner_id == user.id).order_by(Project.name))
    ).all()
    counts: dict[int, dict[str, int]] = {}
    rows = await session.execute(
        select(Task.project_id, Task.status, func.count())
        .where(Task.project_id.in_([p.id for p in projects]))
        .group_by(Task.project_id, Task.status)
    )
    for project_id, task_status, n in rows:
        counts.setdefault(project_id, {})[task_status] = n
    next_rows = await session.execute(
        select(Task.project_id, func.min(Task.next_run_at))
        .where(Task.status == TaskStatus.READY, Task.next_run_at.is_not(None))
        .group_by(Task.project_id)
    )
    nexts = {project_id: at for project_id, at in next_rows}
    return [
        ProjectSummary(
            **ProjectOut.model_validate(p).model_dump(),
            task_counts=counts.get(p.id, {}),
            next_run_at=nexts.get(p.id),
        )
        for p in projects
    ]


@router.post("/projects", response_model=ProjectOut, status_code=status.HTTP_201_CREATED)
async def create_project(body: ProjectIn, session: SessionDep, user: CurrentUser) -> Project:
    project = Project(
        owner_id=user.id,
        name=body.name,
        description=body.description,
        properties=[],
        cell_profile=body.cell_profile.clean() if body.cell_profile else None,
    )
    session.add(project)
    await session.commit()
    return project


@router.get("/projects/{project_id}", response_model=ProjectOut)
async def get_project(project_id: int, session: SessionDep, user: CurrentUser) -> Project:
    return await _project(session, project_id, user)


@router.patch("/projects/{project_id}", response_model=ProjectOut)
async def update_project(
    project_id: int, body: ProjectPatch, session: SessionDep, user: CurrentUser
) -> Project:
    project = await _project(session, project_id, user)
    if body.name is not None:
        project.name = body.name.strip() or project.name
    if body.description is not None:
        project.description = body.description
    if "cell_profile" in body.model_fields_set:
        project.cell_profile = body.cell_profile.clean() if body.cell_profile else None
    if body.properties is not None:
        try:
            project.properties = validate_definitions(body.properties)
        except ValueError as e:
            raise _bad(str(e)) from None
    await session.commit()
    return project


@router.delete("/projects/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(project_id: int, session: SessionDep, user: CurrentUser) -> None:
    project = await _project(session, project_id, user)
    running = await session.scalar(
        select(func.count()).where(Task.project_id == project.id, Task.status == TaskStatus.RUNNING)
    )
    if running:
        raise HTTPException(status.HTTP_409_CONFLICT, "Cancel the running tasks before deleting the project")
    await session.delete(project)
    await session.commit()


# tasks


@router.get("/projects/{project_id}/tasks", response_model=list[TaskOut])
async def list_tasks(project_id: int, session: SessionDep, user: CurrentUser) -> list[TaskOut]:
    await _project(session, project_id, user)
    tasks = (
        await session.scalars(
            select(Task).where(Task.project_id == project_id).order_by(Task.position, Task.id)
        )
    ).all()
    return await _task_out(session, list(tasks))


@router.post("/projects/{project_id}/tasks", response_model=TaskOut, status_code=status.HTTP_201_CREATED)
async def create_task(
    project_id: int, body: TaskIn, request: Request, session: SessionDep, user: CurrentUser
) -> TaskOut:
    project = await _project(session, project_id, user)
    try:
        props = clean_values(project.properties, body.properties)
    except ValueError as e:
        raise _bad(str(e)) from None
    task = Task(
        project_id=project.id,
        title=body.title,
        description=body.description,
        status=body.status,
        position=await _next_position(session, project.id, body.status),
        properties=props,
        schedule_kind=body.schedule_kind,
        cron=body.cron,
        run_at=body.run_at,
        review_on_success=body.review_on_success,
        harness=body.harness,
        workflow_id=await _workflow_for(session, project.id, body.harness, body.workflow_id),
    )
    if body.agent_id is not None:
        agent = await _agent_for(session, project.id, body.agent_id)
        task.agent_id, task.harness, task.workflow_id = agent.id, agent.harness, None
    refresh_next_run(task, (await load_settings(session)).timezone, utcnow())
    session.add(task)
    await session.commit()
    if task.status == TaskStatus.READY:
        request.app.state.scheduler.wake()
    return (await _task_out(session, [task]))[0]


@router.get("/tasks/{task_id}", response_model=TaskOut)
async def get_task(task_id: int, session: SessionDep, user: CurrentUser) -> TaskOut:
    return (await _task_out(session, [await _task(session, task_id, user)]))[0]


@router.patch("/tasks/{task_id}", response_model=TaskOut)
async def update_task(
    task_id: int, body: TaskPatch, request: Request, session: SessionDep, user: CurrentUser
) -> TaskOut:
    task = await _task(session, task_id, user)
    if task.status == TaskStatus.RUNNING:
        raise HTTPException(status.HTTP_409_CONFLICT, "This task is running. Cancel it first.")
    project = await session.get(Project, task.project_id)
    assert project is not None
    fields = body.model_fields_set
    reschedule = False

    if "title" in fields and body.title is not None:
        if not (title := body.title.strip()):
            raise _bad("Title cannot be empty")
        task.title = title
    if "description" in fields and body.description is not None:
        task.description = body.description
    if "properties" in fields and body.properties is not None:
        try:
            task.properties = clean_values(project.properties, body.properties)
        except ValueError as e:
            raise _bad(str(e)) from None
    if "review_on_success" in fields and body.review_on_success is not None:
        task.review_on_success = body.review_on_success
    if fields & {"harness", "workflow_id"}:
        harness = body.harness if "harness" in fields and body.harness is not None else task.harness
        wanted = body.workflow_id if "workflow_id" in fields else task.workflow_id
        task.harness = harness
        task.workflow_id = await _workflow_for(session, project.id, harness, wanted)
    if "agent_id" in fields:
        task.agent_id = (
            None if body.agent_id is None else (await _agent_for(session, project.id, body.agent_id)).id
        )
    if task.agent_id is not None:  # an agent decides how its tasks run
        agent = await _agent_for(session, project.id, task.agent_id)
        task.harness, task.workflow_id = agent.harness, None
    if "position" in fields and body.position is not None:
        task.position = body.position
    if "status" in fields and body.status is not None and body.status != task.status:
        task.status = body.status
        reschedule = True
        if "position" not in fields:
            task.position = await _next_position(session, project.id, body.status)
    if fields & {"schedule_kind", "cron", "run_at"}:
        kind = body.schedule_kind if "schedule_kind" in fields and body.schedule_kind else task.schedule_kind
        cron = body.cron if "cron" in fields else task.cron
        run_at = body.run_at if "run_at" in fields else task.run_at
        try:
            task.cron, task.run_at = check_schedule(ScheduleKind(kind), cron, run_at)
        except ValueError as e:
            raise _bad(str(e)) from None
        task.schedule_kind = kind
        reschedule = True

    if reschedule:
        refresh_next_run(task, (await load_settings(session)).timezone, utcnow())
    await session.commit()
    if task.status == TaskStatus.READY:
        request.app.state.scheduler.wake()
    return (await _task_out(session, [task]))[0]


@router.delete("/tasks/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_task(task_id: int, session: SessionDep, user: CurrentUser) -> None:
    task = await _task(session, task_id, user)
    if task.status == TaskStatus.RUNNING:
        raise HTTPException(status.HTTP_409_CONFLICT, "This task is running. Cancel it first.")
    # the history keeps its own copy, so a deleted task can still be looked at (and put back by hand) afterwards
    session.add(
        ProjectEvent(
            project_id=task.project_id,
            kind="task_deleted",
            title=task.title,
            actor=user.name,
            data=TaskSnapshot.model_validate(task).model_dump(mode="json"),
        )
    )
    await session.delete(task)
    await session.commit()


@router.get("/projects/{project_id}/history", response_model=list[ProjectEventOut])
async def project_history(
    project_id: int,
    session: SessionDep,
    user: CurrentUser,
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
) -> list[ProjectEvent]:
    """What was done to the project, newest first."""
    await _project(session, project_id, user)
    return list(
        await session.scalars(
            select(ProjectEvent)
            .where(ProjectEvent.project_id == project_id)
            .order_by(ProjectEvent.id.desc())
            .limit(limit)
        )
    )


@router.post("/tasks/{task_id}/run", response_model=TaskOut)
async def run_task_now(task_id: int, request: Request, session: SessionDep, user: CurrentUser) -> TaskOut:
    task = await _task(session, task_id, user)
    if task.status == TaskStatus.RUNNING:
        raise HTTPException(status.HTTP_409_CONFLICT, "This task is already running")
    task.status = TaskStatus.READY
    task.next_run_at = utcnow()
    await session.commit()
    request.app.state.scheduler.wake()
    return (await _task_out(session, [task]))[0]


@router.post("/tasks/{task_id}/cancel", response_model=TaskOut)
async def cancel_task(task_id: int, request: Request, session: SessionDep, user: CurrentUser) -> TaskOut:
    task = await _task(session, task_id, user)
    if task.status != TaskStatus.RUNNING:
        raise HTTPException(status.HTTP_409_CONFLICT, "This task is not running")
    running = await session.scalar(
        select(Attempt.id)
        .where(Attempt.task_id == task.id, Attempt.status == "running")
        .order_by(Attempt.id.desc())
    )
    if running is None or not await request.app.state.scheduler.cancel(running):
        raise HTTPException(status.HTTP_409_CONFLICT, "The cell for this task is no longer running")
    await session.refresh(task)
    return (await _task_out(session, [task]))[0]


# attempts


@router.get("/tasks/{task_id}/attempts", response_model=list[AttemptOut])
async def list_attempts(
    task_id: int, session: SessionDep, user: CurrentUser, limit: Annotated[int, Query(ge=1, le=100)] = 20
) -> list[Attempt]:
    await _task(session, task_id, user)
    return list(
        (
            await session.scalars(
                select(Attempt).where(Attempt.task_id == task_id).order_by(Attempt.id.desc()).limit(limit)
            )
        ).all()
    )


@router.get("/attempts/{attempt_id}", response_model=AttemptDetail)
async def get_attempt(attempt_id: int, session: SessionDep, user: CurrentUser) -> AttemptDetail:
    attempt = await session.get(Attempt, attempt_id)
    if attempt is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Attempt not found")
    await _task(session, attempt.task_id, user)
    out = AttemptDetail.model_validate(attempt)
    if attempt.workflow_run_id:
        run = await session.get(WorkflowRun, attempt.workflow_run_id)
        out.workflow_id = run.workflow_id if run else None
    return out


# schedule


@router.get("/projects/{project_id}/schedule", response_model=list[ScheduledRun])
async def upcoming_runs(
    project_id: int,
    session: SessionDep,
    user: CurrentUser,
    hours: Annotated[int, Query(ge=1, le=24 * 14)] = 24,
) -> list[ScheduledRun]:
    """What is going to run in the next N hours (one-off and every occurrence of recurring tasks)."""
    await _project(session, project_id, user)
    tz = (await load_settings(session)).timezone
    now = utcnow()
    end = now + timedelta(hours=hours)
    tasks = (
        await session.scalars(
            select(Task).where(
                Task.project_id == project_id,
                (Task.status == TaskStatus.READY)
                | ((Task.status == TaskStatus.RUNNING) & (Task.schedule_kind == ScheduleKind.CRON)),
            )
        )
    ).all()
    runs: list[ScheduledRun] = []
    for t in tasks:
        if t.schedule_kind == ScheduleKind.CRON and t.cron:
            runs += [
                ScheduledRun(task_id=t.id, title=t.title, at=at, recurring=True)
                for at in cron_occurrences(t.cron, tz, now, end)
            ]
        elif t.next_run_at is not None and t.next_run_at <= end:
            runs.append(
                ScheduledRun(task_id=t.id, title=t.title, at=max(t.next_run_at, now), recurring=False)
            )
    return sorted(runs, key=lambda r: r.at)[:500]
