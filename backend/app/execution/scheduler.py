import asyncio
import contextlib
import logging
import time

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.execution.active_runs import ActiveRuns, _Live
from app.execution.budget import Cost, never_fits
from app.execution.cells.contract import CellManager, CellSpec
from app.execution.executor import AttemptExecutor
from app.execution.failures import _themis_failure
from app.execution.harnesses.prompts import log_tail
from app.execution.planning import RunPlan as _Plan
from app.execution.planning import RunPlanner
from app.execution.retention import prune_workspaces
from app.features.notifications.delivery import notify
from app.features.projects.automation import cooled_down
from app.features.system.settings import AppSettings, load_settings
from app.features.tasks.scheduling import finish_task
from app.persistence.models import (
    Attempt,
    AttemptStatus,
    Board,
    Project,
    Task,
    TaskStatus,
    utcnow,
)

log = logging.getLogger("themis.scheduler")


PRUNE_EVERY_SECONDS = 3600

KEEP_ALIVE_EVERY_SECONDS = (
    3600  # how often to look for tool sign ins that need renewing (the policy is in days)
)

MAX_PLAYING = 8  # tasks playing a workflow at the same time

MAX_WAITING = 50  # how many waiting tasks one tick looks at when handing out the budget


class Scheduler:
    def __init__(
        self, maker: async_sessionmaker[AsyncSession], cells: CellManager, interval: float = 3.0
    ) -> None:
        self.maker, self.cells, self.interval = maker, cells, interval
        self.runs = ActiveRuns()
        self.planner = RunPlanner()
        self.executor = AttemptExecutor(
            maker, cells, self.runs, lambda: self.mcp_logins, lambda: self.workflows
        )
        self._loop_task: asyncio.Task | None = None
        self._wake = asyncio.Event()
        self._last_prune = float("-inf")
        self._last_keep_alive = float("-inf")
        self.mcp_logins = None  # the McpLogins, set by the app; gives runs the tokens of tools that sign in
        self.workflows = None  # the WorkflowRunner, set by the app; plays the workflows of tasks that run one
        self.cells_ready = True  # False while Docker cannot run cells: set by the app's preflight check

    async def start(self) -> None:
        await self.reconcile()
        self._loop_task = asyncio.create_task(self._loop(), name="themis-scheduler")

    async def stop(self) -> None:
        if self._loop_task:
            self._loop_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._loop_task
            self._loop_task = None
        for live in self.runs.live.values():
            live.cancel_reason = "shutdown"
            live.task.cancel()
        await asyncio.gather(*(live.task for live in self.runs.live.values()), return_exceptions=True)

    @property
    def running(self) -> bool:
        return self._loop_task is not None and not self._loop_task.done()

    def wake(self) -> None:
        """Run a tick right away (used when a user presses 'Run now')."""
        self._wake.set()

    async def _loop(self) -> None:
        while True:
            try:
                await self.tick()
                if time.monotonic() - self._last_prune >= PRUNE_EVERY_SECONDS:
                    self._last_prune = time.monotonic()
                    await self.prune_workspaces()
                if self.mcp_logins and time.monotonic() - self._last_keep_alive >= KEEP_ALIVE_EVERY_SECONDS:
                    self._last_keep_alive = time.monotonic()
                    await self.mcp_logins.keep_alive()
            except Exception:  # one bad pass must not end the loop: nothing else would ever start a task
                log.exception("scheduler tick failed")
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._wake.wait(), self.interval)
            self._wake.clear()

    async def reconcile(self) -> None:
        """After a restart nothing is running: close dangling attempts and remove leftover cells.

        A one-off task that was mid-flight is marked FAILED rather than silently re-run, because
        re-running an agent can repeat side effects. A human decides ('Run now'). Recurring tasks
        simply go back to waiting for their next occurrence.
        """
        async with self.maker() as s:
            cfg = await load_settings(s)
            dangling = (await s.scalars(select(Attempt).where(Attempt.status == AttemptStatus.RUNNING))).all()
            now = utcnow()
            for attempt in dangling:
                attempt.status = AttemptStatus.FAILED
                attempt.finished_at = now
                attempt.log += "\n[Themis restarted while this attempt was running]\n"
                attempt.failure = {
                    **_themis_failure(
                        "Themis restarted while this attempt was running.", "Run it again with Run now."
                    ),
                    "tail": log_tail(attempt.log),
                }
                task = await s.get(Task, attempt.task_id)
                if task is not None and task.status == TaskStatus.RUNNING:
                    finish_task(task, AttemptStatus.FAILED, cfg.timezone, now)
            stray = (await s.scalars(select(Task).where(Task.status == TaskStatus.RUNNING))).all()
            for task in stray:  # running with no attempt row: should not happen, but never leave it stuck
                finish_task(task, AttemptStatus.FAILED, cfg.timezone, now)
            await s.commit()
        removed = await self.cells.cleanup_orphans(cfg.docker_host)
        if dangling or removed:
            log.warning(
                "recovered %d interrupted attempt(s), removed %d leftover cell(s)", len(dangling), removed
            )

    async def tick(self) -> int:
        """Start cells for due tasks while they fit the resource budget. Returns how many were started."""
        self.runs.starting = []  # whatever an interrupted earlier tick left behind
        async with self.maker() as s:
            cfg = await load_settings(s)
            now = utcnow()
            waiting, playing_workflows = await self._due_tasks(s, cfg, now)
            cells = await self.planner.plans(s, waiting, cfg)
            workflows = await self.planner.plans(s, playing_workflows, cfg)

            # what cannot run at all fails now, with the reason, instead of waiting forever
            budget = cfg.budget.as_cost()
            broken = [p for p in cells if p.error or never_fits(budget, p.cost)]
            for plan in broken:
                await self._fail(s, plan, budget, cfg, now)
            cells = [p for p in cells if p not in broken]

            due = [*self.runs.admit(budget, cells), *workflows]
            if not due:
                if broken:
                    await s.commit()
                return 0
            # the awaits below (flush, commit) happen before the runs are in `_live`: these folders already count as in
            # use meanwhile (see runs_using), so nothing renames or changes them in that gap
            self.runs.starting = [
                (frozenset(m.volume_id for m in p.mounts), p.task.id, p.task.title) for p in due
            ]
            started = await self._open_attempts(s, due, cfg, now)
            await s.commit()
        for attempt_id, spec, locks in started:
            self._launch(attempt_id, spec, locks, cfg)
        self.runs.starting = []
        return len(started)

    async def _due_tasks(self, s: AsyncSession, cfg: AppSettings, now) -> tuple[list[Task], list[Task]]:
        """The READY tasks that may start now: those that need a cell (as many as one tick looks at) and those that
        play a workflow (as many as there is room to play)."""
        playing = len(self.runs.live) - self.runs.active_cells
        ready = (
            Task.status == TaskStatus.READY,
            (Task.next_run_at.is_(None)) | (Task.next_run_at <= now),
            # cooldown: updated_at moves whenever the task changes status, including when a run ends. A workflow
            # step is exempt: its workflow is already waiting for it and made it exactly once
            Task.internal.is_(True) | cooled_down(cfg, int(now.timestamp())),
            # a halt (see app/features/projects/halt.py): a halted project holds everything, a halted board its own tasks; the steps
            # of workflows (internal) only follow the project, since the board they sit on says nothing of them
            Project.halted_at.is_(None),
            Task.internal.is_(True) | Board.halted_at.is_(None),
        )

        async def pick(harness_filter, limit: int) -> list[Task]:
            query = (
                select(Task)
                .join(Project, Project.id == Task.project_id)
                .join(Board, Board.id == Task.board_id)
                .where(*ready, harness_filter)
                .order_by(Task.next_run_at.asc().nulls_first(), Task.id)
                .limit(limit)
            )
            return list((await s.scalars(query)).all())

        waiting: list[Task] = []
        if (
            self.cells_ready
        ):  # without Docker nothing can start, so tasks stay READY instead of failing (see preflight.py)
            waiting = await pick(Task.harness != "workflow", MAX_WAITING)
        playing_workflows: list[Task] = []
        if playing < MAX_PLAYING:  # workflows only have a cap, since they wait on other tasks' cells
            playing_workflows = await pick(Task.harness == "workflow", MAX_PLAYING - playing)
        return waiting, playing_workflows

    async def _open_attempts(
        self, s: AsyncSession, due: list[_Plan], cfg: AppSettings, now
    ) -> list[tuple[int, CellSpec, frozenset[int]]]:
        """Give each planned task its attempt and mark the task running. The caller commits. Returns what to launch."""
        started: list[tuple[int, CellSpec, frozenset[int]]] = []
        for plan in due:
            task = plan.task
            attempt = Attempt(task_id=task.id, started_at=now)
            s.add(attempt)
            await s.flush()
            spec = self.planner.spec(attempt.id, plan, cfg)
            if plan.harness:  # recorded now, so a run that never reports tokens still says what it ran on
                attempt.harness = spec.harness
                attempt.model, attempt.billing = plan.harness.model, plan.harness.billing
            # a task that plays workflows runs no cell: its attempt takes the folder its stages end in instead
            if spec.harness != "workflow":
                attempt.workdir_id = spec.workdir_id
            task.status = TaskStatus.RUNNING
            task.next_run_at = None
            task.last_run_at = now
            started.append((attempt.id, spec, plan.locks))
        return started

    def _launch(self, attempt_id: int, spec: CellSpec, locks: frozenset[int], cfg: AppSettings) -> None:
        """Run an attempt in the background and keep it in `_live` until it ends."""
        live = _Live(
            task=asyncio.create_task(
                self.executor.execute(attempt_id, spec, cfg.timezone, tuple(cfg.cell_package.retry_waits))
            ),
            spec=spec,
            cell=spec.harness != "workflow",
            locks=locks,
        )
        self.runs.live[attempt_id] = live
        live.task.add_done_callback(lambda _t, aid=attempt_id: self.runs.live.pop(aid, None))

    async def _fail(self, s: AsyncSession, plan: _Plan, budget: Cost, cfg: AppSettings, now) -> None:
        """Record an attempt that never started, with the reason in its log."""
        if plan.error:
            reason = plan.error
        else:
            reason = (
                f"This task needs {plan.cost.cpus:g} CPU and {plan.cost.memory_mb} MB, more than the whole "
                f"resource budget ({budget.cpus:g} CPU, {budget.memory_mb} MB). Raise the budget in Settings, "
                "or give the task a smaller cell."
            )
        s.add(
            Attempt(
                task_id=plan.task.id,
                status=AttemptStatus.FAILED,
                started_at=now,
                finished_at=now,
                log=f"[Cell error] {reason}\n",
                failure={**_themis_failure(reason), "tail": ""},
            )
        )
        plan.task.last_run_at = now
        finish_task(plan.task, AttemptStatus.FAILED, cfg.timezone, now)
        if not plan.task.internal:
            notify(self.maker, plan.task.project_id, "failed", plan.task.title, reason)

    async def stop_running(self, project_id: int, board_id: int | None = None) -> int:
        """Cancel everything that is running in a project, or on one of its boards (a halt, see app/halt.py). Returns
        how many tasks were stopped. Each ends as a cancelled task does: a one-off goes to Blocked, a recurring one
        goes back to waiting for its next time."""
        async with self.maker() as s:
            query = (
                select(Attempt.id, Task.internal)
                .join(Task, Task.id == Attempt.task_id)
                .where(Task.project_id == project_id, Attempt.status == AttemptStatus.RUNNING)
            )
            if board_id is not None:
                query = query.where(Task.board_id == board_id, Task.internal.is_(False))
            rows = (await s.execute(query)).all()
        stopped = 0
        # what plays workflows goes first: cancelling it ends its run, which stops the cells of the steps under it
        for attempt_id in (a for a, internal in rows if not internal):
            stopped += await self.cancel(attempt_id)
        if self.workflows is not None:
            # runs that no task of the scope is playing (a manual run, one a moved task started)
            await self.workflows.cancel_runs(project_id, board_id)
        if board_id is None:
            for attempt_id in (a for a, internal in rows if internal):
                stopped += await self.cancel(attempt_id)
        return stopped

    async def cancel(self, attempt_id: int) -> bool:
        live = self.runs.live.get(attempt_id)
        if live is None:
            return False
        live.cancel_reason = "user"
        live.task.cancel()
        await asyncio.gather(live.task, return_exceptions=True)
        return True

    @property
    def active_cells(self) -> int:
        return self.runs.active_cells

    def runs_using(self, volume_id: int) -> list[tuple[int, str]]:
        return self.runs.runs_using(volume_id)

    def renaming(self, volume_id: int):
        return self.runs.renaming(volume_id)

    async def prune_workspaces(self) -> int:
        return await prune_workspaces(self.maker)
