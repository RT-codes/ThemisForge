"""The always-on loop: every few seconds, start cells for tasks that are due."""

import asyncio
import contextlib
import logging
import shutil
import time
from contextlib import AsyncExitStack
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from .app_settings import AppSettings, load_settings
from .cells import CellError, CellManager, CellSpec
from .codex import CodexError, lease_codex, lease_is_busy
from .config import settings
from .harness import CODEX_AUTH, build_prompt, plan_for, renderer_for
from .models import Attempt, AttemptStatus, Project, Task, TaskStatus, utcnow
from .scheduling import finish_task

log = logging.getLogger("themis.scheduler")

MAX_LOG_CHARS = 200_000
LOG_FLUSH_SECONDS = 1.0
PRUNE_EVERY_SECONDS = 3600


@dataclass
class _Live:
    task: asyncio.Task
    spec: CellSpec | None = None
    cancel_reason: str | None = None  # "user" | "shutdown"


class _LogBuffer:
    """Collects cell output and writes it to the attempt row at most once a second."""

    def __init__(self, maker: async_sessionmaker[AsyncSession], attempt_id: int) -> None:
        self.maker, self.attempt_id = maker, attempt_id
        self.text = ""
        self._flushed_len = 0
        self._last_flush = 0.0

    async def write(self, chunk: str) -> None:
        if len(self.text) < MAX_LOG_CHARS:
            self.text += chunk
            if len(self.text) >= MAX_LOG_CHARS:
                self.text = self.text[:MAX_LOG_CHARS] + "\n[log truncated]\n"
        if time.monotonic() - self._last_flush >= LOG_FLUSH_SECONDS:
            await self.flush()

    async def flush(self) -> None:
        self._last_flush = time.monotonic()
        if len(self.text) == self._flushed_len:
            return
        async with self.maker() as s:
            attempt = await s.get(Attempt, self.attempt_id)
            if attempt is not None:
                attempt.log = self.text
                await s.commit()
        self._flushed_len = len(self.text)


class Scheduler:
    def __init__(
        self, maker: async_sessionmaker[AsyncSession], cells: CellManager, interval: float = 3.0
    ) -> None:
        self.maker, self.cells, self.interval = maker, cells, interval
        self._live: dict[int, _Live] = {}  # attempt id -> running cell
        self._loop_task: asyncio.Task | None = None
        self._wake = asyncio.Event()
        self.max_cells = 0
        self._last_prune = float("-inf")

    # lifecycle

    async def start(self) -> None:
        await self.reconcile()
        self._loop_task = asyncio.create_task(self._loop(), name="themis-scheduler")

    async def stop(self) -> None:
        if self._loop_task:
            self._loop_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._loop_task
            self._loop_task = None
        for live in self._live.values():
            live.cancel_reason = "shutdown"
            live.task.cancel()
        await asyncio.gather(*(live.task for live in self._live.values()), return_exceptions=True)

    @property
    def running(self) -> bool:
        return self._loop_task is not None and not self._loop_task.done()

    @property
    def active_cells(self) -> int:
        return len(self._live)

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
            except Exception:
                log.exception("scheduler tick failed")
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._wake.wait(), self.interval)
            self._wake.clear()

    # startup recovery

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
                attempt.log += "\n[ThemisForge restarted while this attempt was running]\n"
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

    # picking work

    async def tick(self) -> int:
        """Start cells for due tasks while there are free slots. Returns how many were started."""
        async with self.maker() as s:
            cfg = await load_settings(s)
            self.max_cells = cfg.max_concurrent_cells
            free = cfg.max_concurrent_cells - len(self._live)
            if free <= 0:
                return 0
            now = utcnow()
            due = (
                await s.scalars(
                    select(Task)
                    .where(
                        Task.status == TaskStatus.READY,
                        (Task.next_run_at.is_(None)) | (Task.next_run_at <= now),
                    )
                    .order_by(Task.next_run_at.asc().nulls_first(), Task.id)
                    .limit(free)
                )
            ).all()
            started: list[tuple[int, CellSpec]] = []
            for task in due:
                project = await s.get(Project, task.project_id)
                if project is None:
                    continue
                attempt = Attempt(task_id=task.id, started_at=now)
                s.add(attempt)
                await s.flush()
                task.status = TaskStatus.RUNNING
                task.next_run_at = None
                task.last_run_at = now
                started.append((attempt.id, self._spec(attempt.id, task, project, cfg)))
            await s.commit()
        for attempt_id, spec in started:
            live = _Live(task=asyncio.create_task(self._execute(attempt_id, spec, cfg.timezone)), spec=spec)
            self._live[attempt_id] = live
            live.task.add_done_callback(lambda _t, aid=attempt_id: self._live.pop(aid, None))
        return len(started)

    async def prune_workspaces(self) -> int:
        """Remove the private working folders of attempts that finished more than the retention period ago,
        and those whose attempt no longer exists. Returns how many folders were removed."""
        folders = [d for d in (settings.data_dir / "projects").glob("*/workspaces/*") if d.name.isdigit()]
        if not folders:
            return 0
        async with self.maker() as s:
            cfg = await load_settings(s)
            attempts = {
                a.id: a
                for a in (
                    await s.scalars(select(Attempt).where(Attempt.id.in_([int(d.name) for d in folders])))
                ).all()
            }
        cutoff = utcnow() - timedelta(days=cfg.keep_workspaces_days)
        stale = []
        for d in folders:
            a = attempts.get(int(d.name))
            if a is None or (
                a.status != AttemptStatus.RUNNING and a.finished_at is not None and a.finished_at <= cutoff
            ):
                stale.append(d)
        for d in stale:
            await asyncio.to_thread(shutil.rmtree, d, True)
        if stale:
            log.info("removed %d old attempt workspace(s)", len(stale))
        return len(stale)

    @staticmethod
    def _spec(attempt_id: int, task: Task, project: Project, cfg: AppSettings) -> CellSpec:
        plan = plan_for(task.harness, cfg)
        return CellSpec(
            attempt_id=attempt_id,
            task_id=task.id,
            project_id=project.id,
            title=task.title,
            description=task.description,
            properties=task.properties,
            owner_id=project.owner_id,
            harness=task.harness,
            image=plan.image if plan else cfg.cell_image,
            script=plan.script if plan else None,
            writeback=plan.writeback if plan else (),
            prompt=build_prompt(task.title, task.description, task.properties) if plan else "",
            cpus=cfg.cell_cpus,
            memory_mb=cfg.cell_memory_mb,
            timeout_seconds=cfg.cell_timeout_seconds,
            docker_host=cfg.docker_host,
        )

    # running a cell

    async def _execute(self, attempt_id: int, spec: CellSpec, tz: str) -> None:
        buf = _LogBuffer(self.maker, attempt_id)
        outcome, exit_code, result = AttemptStatus.FAILED, None, ""
        try:
            async with AsyncExitStack() as stack:
                lease = None
                if spec.harness == "codex":
                    if lease_is_busy(spec.owner_id):
                        await buf.write("[Waiting for another Codex run of the same user to finish]\n")
                    lease = await stack.enter_async_context(lease_codex(self.maker, spec.owner_id))
                    spec.secret_files[CODEX_AUTH] = lease.auth_json
                renderer = renderer_for(spec.harness)

                async def sink(chunk: str) -> None:
                    if renderer is None:
                        await buf.write(chunk)
                    elif text := renderer.feed(chunk):
                        await buf.write(text)

                res = await self.cells.run(spec, sink)
                if renderer is not None and (tail := renderer.flush()):
                    await buf.write(tail)
                if (
                    lease is not None
                    and (fresh := res.writeback.get(CODEX_AUTH))
                    and fresh != lease.auth_json
                ):
                    try:
                        await lease.save_back(fresh)
                    except CodexError as e:
                        await buf.write(f"\n[The refreshed Codex login was not stored: {e}]\n")
            exit_code, result = res.exit_code, res.result
            outcome = AttemptStatus.SUCCEEDED if res.exit_code == 0 else AttemptStatus.FAILED
        except asyncio.CancelledError:
            reason = self._live[attempt_id].cancel_reason if attempt_id in self._live else None
            if reason == "shutdown":
                await buf.write("\n[ThemisForge shut down while this attempt was running]\n")
            else:
                outcome = AttemptStatus.CANCELLED
                await buf.write("\n[Cancelled]\n")
        except (CellError, CodexError) as e:
            await buf.write(f"\n[Cell error] {e}\n")
        except Exception as e:
            log.exception("attempt %s crashed", attempt_id)
            await buf.write(f"\n[Unexpected error] {e}\n")
        await self._finish(attempt_id, spec.task_id, buf, outcome, exit_code, result, tz)

    async def _finish(
        self,
        attempt_id: int,
        task_id: int,
        buf: _LogBuffer,
        outcome: AttemptStatus,
        exit_code: int | None,
        result: str,
        tz: str,
    ) -> None:
        async with self.maker() as s:
            attempt = await s.get(Attempt, attempt_id)
            task = await s.get(Task, task_id)
            now = utcnow()
            if attempt is not None:
                attempt.status = outcome
                attempt.finished_at = now
                attempt.exit_code = exit_code
                attempt.log = buf.text
                attempt.result = result
            if task is not None and task.status == TaskStatus.RUNNING:
                finish_task(task, outcome, tz, now)
            await s.commit()

    # cancelling

    async def cancel(self, attempt_id: int) -> bool:
        live = self._live.get(attempt_id)
        if live is None:
            return False
        live.cancel_reason = "user"
        live.task.cancel()
        await asyncio.gather(live.task, return_exceptions=True)
        return True
