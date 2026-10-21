from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from app.errors import ApplicationError
from app.features.projects.access import require_project
from app.features.system.settings import load_settings
from app.features.tasks import usage
from app.features.tasks.access import require_task
from app.features.tasks.scheduling import cron_occurrences
from app.features.tasks.schemas import (
    AttemptDetail,
    ScheduledRun,
    TaskOut,
    TaskStageOut,
    TaskWorkflowRun,
    UsageRow,
)
from app.persistence.models import (
    Attempt,
    AttemptStatus,
    NodeStatus,
    RunStatus,
    ScheduleKind,
    Task,
    TaskStage,
    TaskStatus,
    User,
    Workflow,
    WorkflowNodeRun,
    WorkflowRun,
    utcnow,
)


async def _task_out(session: AsyncSession, tasks: list[Task]) -> list[TaskOut]:
    """Tasks plus the status of their latest attempt (one query for all of them)."""
    latest: dict[int, AttemptStatus] = {}
    reasons: dict[int, str] = {}
    if tasks:
        newest = (
            select(func.max(Attempt.id))
            .where(Attempt.task_id.in_([t.id for t in tasks]))
            .group_by(Attempt.task_id)
        )
        rows = await session.execute(
            select(Attempt.task_id, Attempt.status, Attempt.failure).where(Attempt.id.in_(newest))
        )
        for task_id, attempt_status, failure in rows:
            latest[task_id] = AttemptStatus(attempt_status)
            reasons[task_id] = (failure or {}).get("reason", "")
    running = await _running_workflow_runs(session, [t.id for t in tasks])
    stages = await _stages_out(session, tasks)
    out = []
    for t in tasks:
        item = TaskOut.model_validate(t)
        item.last_attempt_status = latest.get(t.id)
        item.last_failure_reason = reasons.get(t.id, "")
        item.workflow_run = running.get(t.id)
        item.stages = stages.get(t.id, [])
        out.append(item)
    return out


async def _stages_out(session: AsyncSession, tasks: list[Task]) -> dict[int, list[TaskStageOut]]:
    """Each task's stages in play order, with the workflow's name and how far the latest attempt got (three queries
    for all of the tasks)."""
    if not tasks:
        return {}
    rows = list(
        await session.scalars(
            select(TaskStage)
            .where(TaskStage.task_id.in_([t.id for t in tasks]))
            .order_by(TaskStage.task_id, TaskStage.position)
        )
    )
    if not rows:
        return {}
    names = dict(
        (
            await session.execute(
                select(Workflow.id, Workflow.name).where(Workflow.id.in_({st.workflow_id for st in rows}))
            )
        ).all()
    )
    run_ids = {st.workflow_run_id for st in rows if st.workflow_run_id}
    states = {}
    if run_ids:
        found = await session.execute(
            select(WorkflowRun.id, WorkflowRun.status).where(WorkflowRun.id.in_(run_ids))
        )
        states = dict(found.all())
    out: dict[int, list[TaskStageOut]] = {}
    for st in rows:
        out.setdefault(st.task_id, []).append(
            TaskStageOut(
                workflow_id=st.workflow_id,
                workflow_name=names.get(st.workflow_id, "Workflow"),
                status=states.get(st.workflow_run_id, "pending"),
                run_id=st.workflow_run_id,
            )
        )
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


async def list_tasks(
    project_id: int,
    session: AsyncSession,
    user: User,
    board_id: int | None = None,
    include_steps: bool = False,
) -> list[TaskOut]:
    await require_project(session, project_id, user)
    query = select(Task).where(Task.project_id == project_id).order_by(Task.position, Task.id)
    if not include_steps:
        query = query.where(Task.internal.is_(False))
    if board_id is not None:
        query = query.where(Task.board_id == board_id)
    return await _task_out(session, list((await session.scalars(query)).all()))


async def get_task(task_id: int, session: AsyncSession, user: User) -> TaskOut:
    return (await _task_out(session, [await require_task(session, task_id, user)]))[0]


async def list_attempts(task_id: int, session: AsyncSession, user: User, limit: int = 20) -> list[Attempt]:
    await require_task(session, task_id, user)
    return list(
        (
            await session.scalars(
                select(Attempt).where(Attempt.task_id == task_id).order_by(Attempt.id.desc()).limit(limit)
            )
        ).all()
    )


async def get_attempt(attempt_id: int, session: AsyncSession, user: User) -> AttemptDetail:
    attempt = await session.get(Attempt, attempt_id)
    if attempt is None:
        raise ApplicationError(status.HTTP_404_NOT_FOUND, "Attempt not found")
    await require_task(session, attempt.task_id, user)
    out = AttemptDetail.model_validate(attempt)
    if attempt.workflow_run_id:
        run = await session.get(WorkflowRun, attempt.workflow_run_id)
        out.workflow_id = run.workflow_id if run else None
    return out


async def project_usage(
    project_id: int,
    session: AsyncSession,
    user: User,
    days: int = 7,
) -> list[UsageRow]:
    """What the project's attempts used, per harness and model."""
    await require_project(session, project_id, user)
    return await usage.usage_by_model(session, project_id, utcnow() - timedelta(days=days))


async def upcoming_runs(
    project_id: int,
    session: AsyncSession,
    user: User,
    hours: int = 24,
) -> list[ScheduledRun]:
    """What is going to run in the next N hours (one-off and every occurrence of recurring tasks)."""
    await require_project(session, project_id, user)
    tz = (await load_settings(session)).timezone
    now = utcnow()
    end = now + timedelta(hours=hours)
    tasks = (
        await session.scalars(
            select(Task).where(
                Task.project_id == project_id,
                Task.internal.is_(False),  # a workflow step runs at once: it is not "coming up"
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
