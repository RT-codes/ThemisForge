import asyncio
import logging
from collections.abc import Awaitable, Callable

from sqlalchemy import event, inspect, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import Session

from app.features.projects import automation, halt
from app.features.system.settings import load_settings
from app.features.workflows.folders import task_workdir
from app.features.workflows.graph import (
    Graph,
    LoopError,
)
from app.persistence.models import (
    Board,
    Project,
    RunStatus,
    Task,
    Workflow,
    WorkflowRun,
    utcnow,
)

log = logging.getLogger("themis.workflows")


def _changed(obj: Task, attribute: str) -> bool:
    """Did this flush give the attribute a new value (or its first one, for a new row)?"""
    history = inspect(obj).attrs[attribute].history
    return bool(history.added) and history.added != history.deleted


class StatusTriggers:
    """Observe committed task moves; never start a workflow before commit."""

    def __init__(
        self,
        maker: async_sessionmaker[AsyncSession],
        start: Callable[..., Awaitable[int]],
        stopping: Callable[[], bool],
    ) -> None:
        self.maker, self.start, self.stopping = maker, start, stopping
        self._firing: set[asyncio.Task] = set()
        event.listen(Session, "after_flush", self._note_moves)
        event.listen(Session, "after_commit", self._fire_moves)
        event.listen(Session, "after_rollback", self._drop_moves)

    def close(self) -> None:
        event.remove(Session, "after_flush", self._note_moves)
        event.remove(Session, "after_commit", self._fire_moves)
        event.remove(Session, "after_rollback", self._drop_moves)
        for firing in self._firing:
            firing.cancel()

    def _ours(self, session: Session) -> bool:
        return session.get_bind() is self.maker.kw["bind"].sync_engine

    def _note_moves(self, session: Session, _ctx) -> None:
        """Remember the tasks this flush moved into a status (or created in one); they count once the commit succeeds."""
        if not self._ours(session):
            return
        for obj in (*session.new, *session.dirty):
            # arriving on another board counts too: the card lands in a column there
            if isinstance(obj, Task) and (_changed(obj, "status") or _changed(obj, "board_id")):
                session.info.setdefault("status_moves", []).append((obj.project_id, obj.id, obj.status))

    def _drop_moves(self, session: Session) -> None:
        if self._ours(session):
            session.info.pop("status_moves", None)

    def _fire_moves(self, session: Session) -> None:
        if not self._ours(session):  # another runner's session (several exist in tests): leave its list alone
            return
        moves = session.info.pop("status_moves", None)
        if moves and not self.stopping():
            firing = asyncio.get_running_loop().create_task(self._fire(moves))
            self._firing.add(firing)
            firing.add_done_callback(self._firing.discard)

    async def _fire(self, moves: list[tuple[int, int, str]]) -> None:
        """Start the workflows whose Trigger says "a task moves into <status>" for each move.

        A task is not offered twice to the same workflow while its run is going or within the start cooldown. That is
        the guard against a workflow that moves a task into the very status that starts it."""
        try:
            for project_id, task_id, status in moves:
                async with self.maker() as s:
                    cfg = await load_settings(s)
                    task = await s.get(Task, task_id)
                    if task is None or task.internal:
                        continue  # gone, or the task an Agent node made for itself: part of that workflow, not board work
                    if await halt.why_held(s, task):
                        continue  # the project or the board is halted: nothing starts until it is resumed
                    board = await s.get_one(Board, task.board_id)
                    cooldown = automation.start_cooldown(cfg, await s.get(Project, project_id), task)
                    workflows = (
                        await s.scalars(select(Workflow).where(Workflow.project_id == project_id))
                    ).all()
                    for wf in workflows:
                        graph = Graph.model_validate(wf.graph)
                        starts = [n.id for n in graph.status_triggers(status, board)]
                        if not starts or await self._recently_started(s, wf.id, task_id, cooldown):
                            continue
                        try:
                            await self.start(
                                project_id,
                                wf.id,
                                graph,
                                trigger="status",
                                trigger_task_id=task_id,
                                starts=starts,
                                workdir_id=await task_workdir(s, task),
                            )
                        except LoopError:
                            log.warning("workflow %s not started by task %s: it would loop", wf.id, task_id)
        # fire-and-forget, after the task's own commit: a failed trigger must not surface anywhere
        except Exception:
            log.exception("starting workflows for moved tasks failed")

    @staticmethod
    async def _recently_started(s: AsyncSession, workflow_id: int, task_id: int, cooldown: int) -> bool:
        latest = await s.scalar(
            select(WorkflowRun)
            .where(WorkflowRun.workflow_id == workflow_id, WorkflowRun.trigger_task_id == task_id)
            .order_by(WorkflowRun.id.desc())
            .limit(1)
        )
        return latest is not None and (
            latest.status == RunStatus.RUNNING or (utcnow() - latest.started_at).total_seconds() < cooldown
        )
