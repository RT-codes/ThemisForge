"""Halting a project or a board: the emergency brake.

Stopping one task is an everyday thing (a cancelled one-off task goes to Blocked, a recurring one skips that run and
keeps its schedule, see scheduling.finish_task). A halt is bigger: until it is resumed NOTHING in its scope may start,
and what is running can be stopped with it. It is a flag on the project or the board, not a task status, so:

- it survives a restart, and a task that was queued is exactly as it was when the halt is lifted;
- it is checked at every place that starts work (the scheduler, workflow triggers, "Run now", manual workflow runs),
  and the flag is set before anything is cancelled so nothing can slip in between;
- what a halt interrupted is never restarted by the resume: it waits in Blocked for a decision, because the reason for
  a halt is often a task that misbehaves.

A task of a halted board and every task of a halted project is held. The tasks workflow Agent nodes make for their
steps (internal) follow the project only: they live on the project's first board, which says nothing about the
workflow they belong to.
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.projects import boards
from app.features.system.settings import load_settings
from app.features.tasks.scheduling import refresh_next_run
from app.persistence.models import Board, Project, ScheduleKind, Task, TaskStatus, utcnow


async def why_held(session: AsyncSession, task: Task) -> str | None:
    """Why this task may not start right now because of a halt, or None."""
    project = await session.get(Project, task.project_id)
    if project is not None and project.halted_at is not None:
        return "This project is halted. Resume it first."
    if not task.internal:
        board = await session.get(Board, task.board_id)
        if board is not None and board.halted_at is not None:
            return f'The board "{board.name}" is halted. Resume it first.'
    return None


async def halt(
    session: AsyncSession, scheduler, project: Project, board: Board | None, *, stop_running: bool, actor: str
) -> int:
    """Halt the project, or one board of it. With `stop_running` what is running there is cancelled too (otherwise it
    is allowed to finish, and only nothing new starts). Returns how many tasks were stopped."""
    target = board or project
    newly = target.halted_at is None
    if newly:
        target.halted_at = utcnow()
        await session.commit()  # from here on nothing in scope starts, before anything is cancelled
    stopped = await scheduler.stop_running(project.id, board.id if board else None) if stop_running else 0
    if newly or stopped:
        boards.record(
            session, "halted", project.id, board.name if board else project.name, actor,
            workspace_id=board.workspace_id if board else None, board_id=board.id if board else None,
            data={"scope": "board" if board else "project", "stopped": stopped, "newly": newly},
        )  # fmt: skip
        await session.commit()
    return stopped


async def resume(session: AsyncSession, scheduler, project: Project, board: Board | None, actor: str) -> None:
    """Lift a halt. Nothing is started by this itself: tasks that were waiting go on as usual, and the ones the halt
    interrupted stay in Blocked until someone runs them."""
    target = board or project
    if target.halted_at is None:
        return
    target.halted_at = None
    # A recurring task does not catch up on what it missed while halted: all of them at once would be a burst.
    tz = (await load_settings(session)).timezone
    now = utcnow()
    query = select(Task).where(
        Task.project_id == project.id,
        Task.status == TaskStatus.READY,
        Task.schedule_kind == ScheduleKind.CRON,
    )
    if board is not None:
        query = query.where(Task.board_id == board.id)
    for task in await session.scalars(query):
        if task.next_run_at is not None and task.next_run_at <= now:
            refresh_next_run(task, tz, now)
    boards.record(
        session, "resumed", project.id, board.name if board else project.name, actor,
        workspace_id=board.workspace_id if board else None, board_id=board.id if board else None,
        data={"scope": "board" if board else "project"},
    )  # fmt: skip
    await session.commit()
    scheduler.wake()
