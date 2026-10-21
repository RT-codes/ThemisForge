from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from app.errors import ApplicationError, invalid
from app.features.projects import boards, halt
from app.features.projects.access import require_project
from app.features.projects.properties import clean_values
from app.features.system.settings import load_settings
from app.features.tasks.access import require_task
from app.features.tasks.creation import agent_for, new_task, set_stages, workflows_for
from app.features.tasks.queries import _stages_out, _task_out
from app.features.tasks.scheduling import refresh_next_run
from app.features.tasks.schemas import TaskIn, TaskOut, TaskPatch, TaskSnapshot, check_schedule
from app.persistence.models import (
    Attempt,
    Board,
    Project,
    ScheduleKind,
    Task,
    TaskStage,
    TaskStatus,
    User,
    utcnow,
)
from app.runtime import Runtime


async def create_task(
    project_id: int, body: TaskIn, runtime: Runtime, session: AsyncSession, user: User
) -> TaskOut:
    project = await require_project(session, project_id, user)
    task = await new_task(session, project, body, user.name)
    await session.commit()
    if task.status == TaskStatus.READY:
        runtime.scheduler.wake()
    return (await _task_out(session, [task]))[0]


async def duplicate_task(task_id: int, session: AsyncSession, user: User) -> TaskOut:
    """The same task again, parked in the Backlog of its board. It takes what the task asks for and how it runs
    (description, properties, schedule, agent or workflows, automation guard), and none of what happened to it: no
    attempts or history, no link to the task it follows, and not the working folder it carried on in (a copy starts
    fresh). The Backlog is where a task does not start by itself, so the copy runs when its owner moves it on."""
    origin = await require_task(session, task_id, user)
    if origin.internal:
        raise invalid("A workflow step is made by its workflow and cannot be duplicated")
    board = await session.get_one(Board, origin.board_id)
    # run_options may name the folder a workflow handed this task (see workflows.task_workdir); that is history too
    options = {k: v for k, v in (origin.run_options or {}).items() if k != "workdir"}
    copy = Task(
        project_id=origin.project_id,
        board_id=board.id,
        title=f"Copy of {origin.title}"[:200],
        description=origin.description,
        status=TaskStatus.BACKLOG,
        position=await boards.next_position(session, board.id, TaskStatus.BACKLOG),
        properties=dict(origin.properties),
        schedule_kind=origin.schedule_kind,
        cron=origin.cron,
        run_at=origin.run_at,
        review_on_success=origin.review_on_success,
        harness=origin.harness,
        agent_id=origin.agent_id,
        run_options=options or None,
        cooldown_seconds=origin.cooldown_seconds,
        max_hops=origin.max_hops,
    )
    session.add(copy)
    await session.flush()
    stages = await session.scalars(
        select(TaskStage.workflow_id).where(TaskStage.task_id == origin.id).order_by(TaskStage.position)
    )
    await set_stages(session, copy, list(stages))
    boards.record_task(
        session,
        "task_created",
        copy,
        user.name,
        board,
        {"to": boards.place(board, copy.status), "copy_of": origin.title},
    )
    await session.commit()
    return (await _task_out(session, [copy]))[0]


async def update_task(
    task_id: int, body: TaskPatch, runtime: Runtime, session: AsyncSession, user: User
) -> TaskOut:
    task = await require_task(session, task_id, user)
    if task.status == TaskStatus.RUNNING:
        raise ApplicationError(status.HTTP_409_CONFLICT, "This task is running. Cancel it first.")
    project = await session.get(Project, task.project_id)
    assert project is not None
    fields = body.model_fields_set
    reschedule = False

    if "title" in fields and body.title is not None:
        if not (title := body.title.strip()):
            raise invalid("Title cannot be empty")
        task.title = title
    if "description" in fields and body.description is not None:
        task.description = body.description
    if "properties" in fields and body.properties is not None:
        try:
            task.properties = clean_values(project.properties, body.properties)
        except ValueError as e:
            raise invalid(str(e)) from None
    if "review_on_success" in fields and body.review_on_success is not None:
        task.review_on_success = body.review_on_success
    if fields & {"harness", "workflow_ids"}:
        harness = body.harness if "harness" in fields and body.harness is not None else task.harness
        wanted = body.workflow_ids
        if wanted is None:  # only the harness changed: keep the list it has
            wanted = list(
                await session.scalars(
                    select(TaskStage.workflow_id)
                    .where(TaskStage.task_id == task.id)
                    .order_by(TaskStage.position)
                )
            )
        task.harness = harness
        await set_stages(session, task, await workflows_for(session, project.id, harness, wanted))
    if "cooldown_seconds" in fields:  # null puts the project's value back
        task.cooldown_seconds = body.cooldown_seconds
    if "max_hops" in fields:
        task.max_hops = body.max_hops
    if "agent_id" in fields:
        task.agent_id = (
            None if body.agent_id is None else (await agent_for(session, project.id, body.agent_id)).id
        )
    if task.agent_id is not None:  # an agent decides how its tasks run
        agent = await agent_for(session, project.id, task.agent_id)
        task.harness = agent.harness
        await set_stages(session, task, [])
    if "position" in fields and body.position is not None:
        task.position = body.position
    if "status" in fields and body.status is not None and body.status != task.status:
        board = await session.get(Board, task.board_id)
        try:
            boards.check_status(board, body.status)
        except boards.BoardError as e:
            raise invalid(str(e)) from None
        was, task.status = task.status, body.status
        task.hops = 0  # a person took it from here: automation counts again from nothing
        boards.record_status_change(session, task, board, user.name, was)
        reschedule = True
        if "position" not in fields:
            task.position = await boards.next_position(session, task.board_id, body.status)
    if fields & {"schedule_kind", "cron", "run_at"}:
        kind = body.schedule_kind if "schedule_kind" in fields and body.schedule_kind else task.schedule_kind
        cron = body.cron if "cron" in fields else task.cron
        run_at = body.run_at if "run_at" in fields else task.run_at
        try:
            task.cron, task.run_at = check_schedule(ScheduleKind(kind), cron, run_at)
        except ValueError as e:
            raise invalid(str(e)) from None
        task.schedule_kind = kind
        reschedule = True

    if reschedule:
        refresh_next_run(task, (await load_settings(session)).timezone, utcnow())
    await session.commit()
    if task.status == TaskStatus.READY:
        runtime.scheduler.wake()
    return (await _task_out(session, [task]))[0]


async def delete_task(task_id: int, session: AsyncSession, user: User) -> None:
    task = await require_task(session, task_id, user)
    if task.status == TaskStatus.RUNNING:
        raise ApplicationError(status.HTTP_409_CONFLICT, "This task is running. Cancel it first.")
    # the history keeps its own copy, so a deleted task can still be looked at (and put back by hand) afterwards
    snapshot = TaskSnapshot.model_validate(task)
    snapshot.workflow_ids = [s.workflow_id for s in (await _stages_out(session, [task])).get(task.id, [])]
    boards.record_task(
        session,
        "task_deleted",
        task,
        user.name,
        await session.get(Board, task.board_id),
        snapshot.model_dump(mode="json"),
    )
    await session.delete(task)
    await session.commit()


async def run_task_now(task_id: int, runtime: Runtime, session: AsyncSession, user: User) -> TaskOut:
    task = await require_task(session, task_id, user)
    if task.status == TaskStatus.RUNNING:
        raise ApplicationError(status.HTTP_409_CONFLICT, "This task is already running")
    if held := await halt.why_held(session, task):
        raise ApplicationError(status.HTTP_409_CONFLICT, held)
    task.status = TaskStatus.READY
    task.next_run_at = utcnow()
    await session.commit()
    runtime.scheduler.wake()
    return (await _task_out(session, [task]))[0]


async def cancel_task(task_id: int, runtime: Runtime, session: AsyncSession, user: User) -> TaskOut:
    task = await require_task(session, task_id, user)
    if task.status != TaskStatus.RUNNING:
        raise ApplicationError(status.HTTP_409_CONFLICT, "This task is not running")
    running = await session.scalar(
        select(Attempt.id)
        .where(Attempt.task_id == task.id, Attempt.status == "running")
        .order_by(Attempt.id.desc())
    )
    if running is None or not await runtime.scheduler.cancel(running):
        raise ApplicationError(status.HTTP_409_CONFLICT, "The cell for this task is no longer running")
    await session.refresh(task)
    return (await _task_out(session, [task]))[0]
