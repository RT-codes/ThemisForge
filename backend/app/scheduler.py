"""The always-on loop: every few seconds, start cells for tasks that are due."""

import asyncio
import contextlib
import logging
import shutil
import time
from contextlib import AsyncExitStack
from dataclasses import dataclass, field
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from .app_settings import AppSettings, load_settings
from .budget import Cost, admit, never_fits
from .cells import CellError, CellManager, CellResult, CellSpec, Mount
from .codex import CodexError, lease_codex, lease_is_busy
from .config import settings
from .crypto import decrypt
from .harness import CODEX_AUTH, HarnessPlan, agent_preamble, build_prompt, plan_for, renderer_for
from .keys import Redactor, key_path, unique_env_names
from .mcp import CONFIG_PATH, McpSpec, config_toml
from .models import Agent, Attempt, AttemptStatus, McpServer, Project, Secret, Task, TaskStatus, utcnow
from .profiles import Profile, resolve_profile
from .project_config import sync_project
from .scheduling import finish_task
from .skills import missing as missing_skills
from .volumes import MountError, plan_mounts

log = logging.getLogger("themis.scheduler")

MAX_LOG_CHARS = 200_000
LOG_FLUSH_SECONDS = 1.0
PRUNE_EVERY_SECONDS = 3600
MAX_PLAYING = 8  # tasks playing a workflow at the same time
MAX_WAITING = 50  # how many waiting tasks one tick looks at when handing out the budget


@dataclass
class _Live:
    task: asyncio.Task
    spec: CellSpec | None = None
    cancel_reason: str | None = None  # "user" | "shutdown"
    cell: bool = True  # False for a task that plays a workflow: it orchestrates, so it holds no cell slot
    locks: frozenset[int] = frozenset()  # volumes this run holds while it writes (writers take turns)


@dataclass
class _Plan:
    """Everything decided about one task before its cell starts."""

    task: Task
    project: Project
    agent: Agent | None
    profile: Profile
    harness: HarnessPlan | None
    mounts: list[Mount]
    error: str = ""  # why it cannot run at all
    skills: list[str] = field(default_factory=list)
    mcp: list[McpSpec] = field(default_factory=list)
    keys: dict[int, str] = field(
        default_factory=dict
    )  # key id -> variable name, for the keys the agent is given

    @property
    def cost(self) -> Cost:
        return Cost(self.profile.cpus, self.profile.memory_mb)

    @property
    def locks(self) -> frozenset[int]:
        return frozenset(m.volume_id for m in self.mounts if m.lock)


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
        # Runs that have picked their folders but are not in `_live` yet, as (volume ids, task id, title). They count as
        # using their folders already, so there is no moment between "chosen" and "running" when a folder looks free.
        self._starting: list[tuple[frozenset[int], int, str]] = []
        self._renaming: set[int] = set()  # folders being renamed: no run starts on them until that is done
        self._loop_task: asyncio.Task | None = None
        self._wake = asyncio.Event()
        self._last_prune = float("-inf")
        self.workflows = None  # the WorkflowRunner, set by the app; plays the workflows of tasks that run one
        self.cells_ready = True  # False while Docker cannot run cells: set by the app's preflight check

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
        return sum(1 for live in self._live.values() if live.cell)

    def runs_using(self, volume_id: int) -> list[tuple[int, str]]:
        """The runs (task id, title) that have a folder mounted, read only or not. While there are any, the Files page
        leaves the folder alone: a change from outside could break what an agent is in the middle of."""
        live = [
            (x.spec.task_id, x.spec.title)
            for x in self._live.values()
            if x.spec and any(m.volume_id == volume_id for m in x.spec.mounts)
        ]
        return live + [(task_id, title) for ids, task_id, title in self._starting if volume_id in ids]

    @contextlib.contextmanager
    def renaming(self, volume_id: int):
        """Held while a folder is renamed (its directory moves, then the database follows). A run planned meanwhile would
        mount the old path and make a fresh empty folder there, so none starts on this folder until it is done."""
        self._renaming.add(volume_id)
        try:
            yield
        finally:
            self._renaming.discard(volume_id)

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
                attempt.log += "\n[Themis restarted while this attempt was running]\n"
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
        """Start cells for due tasks while they fit the resource budget. Returns how many were started."""
        self._starting = []  # whatever an interrupted earlier tick left behind
        async with self.maker() as s:
            cfg = await load_settings(s)
            playing = len(self._live) - self.active_cells
            now = utcnow()
            ready = (
                Task.status == TaskStatus.READY,
                (Task.next_run_at.is_(None)) | (Task.next_run_at <= now),
            )
            order = (Task.next_run_at.asc().nulls_first(), Task.id)
            budget = cfg.budget.as_cost()
            waiting = []
            if (
                self.cells_ready
            ):  # without Docker nothing can start, so tasks stay READY instead of failing (see preflight.py)
                waiting = (
                    await s.scalars(
                        select(Task)
                        .where(*ready, Task.harness != "workflow")
                        .order_by(*order)
                        .limit(MAX_WAITING)
                    )
                ).all()
            playing_workflows = []
            if playing < MAX_PLAYING:  # workflows only have a cap, since they wait on other tasks' cells
                playing_workflows = (
                    await s.scalars(
                        select(Task)
                        .where(*ready, Task.harness == "workflow")
                        .order_by(*order)
                        .limit(MAX_PLAYING - playing)
                    )
                ).all()
            cells = await self._plans(s, list(waiting), cfg)
            workflows = await self._plans(s, list(playing_workflows), cfg)

            # what cannot run at all fails now, with the reason, instead of waiting forever
            broken = [p for p in cells if p.error or never_fits(budget, p.cost)]
            for plan in broken:
                await self._fail(s, plan, budget, cfg, now)
            cells = [p for p in cells if p not in broken]

            # a folder that writers must take turns on is held by one run at a time; a task that wants a busy one
            # lets the next task go first, so it never sits on budget while it waits
            claimed: set[int] = set().union(*(live.locks for live in self._live.values()))
            eligible = []
            for plan in cells:
                if plan.locks & claimed or any(m.volume_id in self._renaming for m in plan.mounts):
                    continue
                claimed |= plan.locks
                eligible.append(plan)

            running = [
                Cost(live.spec.cpus, live.spec.memory_mb)
                for live in self._live.values()
                if live.cell and live.spec
            ]
            due = [*eligible[: admit(budget, running, [p.cost for p in eligible])], *workflows]
            if not due:
                if broken:
                    await s.commit()
                return 0
            # the awaits below (flush, commit) happen before the runs are in `_live`: these folders already count as in
            # use meanwhile (see runs_using), so nothing renames or changes them in that gap
            self._starting = [
                (frozenset(m.volume_id for m in p.mounts), p.task.id, p.task.title) for p in due
            ]
            started: list[tuple[int, CellSpec, frozenset[int]]] = []
            for plan in due:
                task = plan.task
                attempt = Attempt(task_id=task.id, started_at=now)
                s.add(attempt)
                await s.flush()
                task.status = TaskStatus.RUNNING
                task.next_run_at = None
                task.last_run_at = now
                started.append((attempt.id, self._spec(attempt.id, plan, cfg), plan.locks))
            await s.commit()
        for attempt_id, spec, locks in started:
            live = _Live(
                task=asyncio.create_task(self._execute(attempt_id, spec, cfg.timezone)),
                spec=spec,
                cell=spec.harness != "workflow",
                locks=locks,
            )
            self._live[attempt_id] = live
            live.task.add_done_callback(lambda _t, aid=attempt_id: self._live.pop(aid, None))
        self._starting = []
        return len(started)

    async def _plans(self, s: AsyncSession, tasks: list[Task], cfg: AppSettings) -> list[_Plan]:
        """For each task: its agent, the cell it gets and the folders it mounts."""
        if not tasks:
            return []
        projects = {
            p.id: p
            for p in await s.scalars(select(Project).where(Project.id.in_({t.project_id for t in tasks})))
        }
        agent_ids = {t.agent_id for t in tasks if t.agent_id}
        for project_id in {t.project_id for t in tasks if t.agent_id}:
            # a run is planned from what the agent's file says right now (it may have been edited since the last look)
            await sync_project(s, project_id)
        agents = (
            {a.id: a for a in await s.scalars(select(Agent).where(Agent.id.in_(agent_ids)))}
            if agent_ids
            else {}
        )
        plans = []
        for task in tasks:
            if (project := projects.get(task.project_id)) is not None:
                plans.append(await self._plan(s, task, project, agents.get(task.agent_id or 0), cfg))
        return plans

    @staticmethod
    async def _plan(
        s: AsyncSession, task: Task, project: Project, agent: Agent | None, cfg: AppSettings
    ) -> _Plan:
        harness = agent.harness if agent else task.harness
        skills, mcp, keys, error = await Scheduler._capabilities(s, project, agent)
        hp = plan_for(
            harness,
            cfg,
            model=agent.model if agent else "",
            effort=agent.reasoning_effort if agent else "",
            key_envs=sorted(keys.values()),
        )
        extra = task.run_options or {}
        profile = resolve_profile(
            cfg,
            hp.image if hp else cfg.cell_image,
            project.cell_profile,
            agent.cell_profile if agent else None,
            extra.get("profile"),
        )
        plan = _Plan(task, project, agent, profile, hp, [], error=error, skills=skills, mcp=mcp, keys=keys)
        if (
            harness != "workflow" and not plan.error
        ):  # a task that plays a workflow starts no cell, so it mounts nothing
            try:
                refs = [*(agent.mounts if agent else []), *extra.get("mounts", [])]
                plan.mounts = await plan_mounts(s, project.id, refs, cfg)
            except MountError as e:
                plan.error = str(e)
        return plan

    @staticmethod
    async def _capabilities(
        s: AsyncSession, project: Project, agent: Agent | None
    ) -> tuple[list[str], list[McpSpec], dict[int, str], str]:
        """What an agent is given besides its words: skills, tool servers and keys. Anything that was deleted since
        the agent was set up stops the run with a reason, instead of running without it."""
        if agent is not None and agent.config_error:
            return [], [], {}, f"The agent's file in the config folder has a problem: {agent.config_error}"
        if agent is None or not (agent.skills or agent.mcp_servers or agent.secrets):
            return [], [], {}, ""
        if gone := missing_skills(project.id, agent.skills):
            return [], [], {}, f"The skill '{gone[0]}' no longer exists. Check the agent's Skills."
        rows = []
        if agent.mcp_servers:
            rows = list(
                await s.scalars(
                    select(McpServer).where(
                        McpServer.project_id == project.id, McpServer.id.in_(agent.mcp_servers)
                    )
                )
            )
            if len(rows) != len(set(agent.mcp_servers)):
                return [], [], {}, "A tool server this agent uses no longer exists. Check the agent's Tools."
        specs = [
            McpSpec(
                name=r.name,
                kind=r.kind,
                command=r.command,
                args=tuple(r.args),
                url=r.url,
                env=dict(r.env),
                secret_env=dict(r.secret_env),
                bearer_secret_id=r.bearer_secret_id,
            )
            for r in rows
        ]
        wanted = set(agent.secrets) | {spec.bearer_secret_id for spec in specs if spec.bearer_secret_id}
        every = wanted | {i for spec in specs for i in spec.key_ids}
        found = (
            {x.id: x for x in await s.scalars(select(Secret).where(Secret.id.in_(every)))} if every else {}
        )
        if gone_keys := every - set(found):
            return (
                [],
                [],
                {},
                f"A key this agent uses no longer exists (key {min(gone_keys)}). Check its Keys and Tools.",
            )
        names = unique_env_names([(i, found[i].name) for i in sorted(every)])
        return list(agent.skills), specs, {i: names[i] for i in sorted(wanted)}, ""

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
            )
        )
        plan.task.last_run_at = now
        finish_task(plan.task, AttemptStatus.FAILED, cfg.timezone, now)

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
    def _spec(attempt_id: int, plan: _Plan, cfg: AppSettings) -> CellSpec:
        task, project, agent, hp, profile = plan.task, plan.project, plan.agent, plan.harness, plan.profile
        prompt = ""
        if hp:
            prompt = build_prompt(
                task.title,
                task.description,
                task.properties,
                preamble=agent_preamble(agent.name, agent.role, agent.instructions) if agent else "",
                folders=[(m.name, m.read_only) for m in plan.mounts],
            )
        return CellSpec(
            attempt_id=attempt_id,
            task_id=task.id,
            project_id=project.id,
            title=task.title,
            description=task.description,
            properties=task.properties,
            owner_id=project.owner_id,
            harness=agent.harness if agent else task.harness,
            workflow_id=task.workflow_id,
            image=profile.image,
            script=hp.script if hp else None,
            writeback=hp.writeback if hp else (),
            prompt=prompt,
            cpus=profile.cpus,
            memory_mb=profile.memory_mb,
            timeout_seconds=profile.timeout_seconds,
            docker_host=cfg.docker_host,
            mounts=plan.mounts,
            skills=plan.skills,
            keys=plan.keys,
            mcp=plan.mcp,
        )

    # running a cell

    async def _execute(self, attempt_id: int, spec: CellSpec, tz: str) -> None:
        buf = _LogBuffer(self.maker, attempt_id)
        outcome, exit_code, result = AttemptStatus.FAILED, None, ""
        redact = Redactor(
            []
        )  # replaces the values of the keys this run was given, in everything that is stored
        try:
            async with AsyncExitStack() as stack:
                lease = None
                if spec.harness == "codex":
                    if lease_is_busy(spec.owner_id):
                        await buf.write("[Waiting for another Codex run of the same user to finish]\n")
                    lease = await stack.enter_async_context(lease_codex(self.maker, spec.owner_id))
                    spec.secret_files[CODEX_AUTH] = lease.auth_json
                    if spec.keys or spec.mcp:
                        values = await self._key_values(spec)
                        for key_id, env in spec.keys.items():
                            spec.secret_files[key_path(env)] = values[key_id]
                        if spec.mcp:
                            spec.secret_files[CONFIG_PATH] = config_toml(spec.mcp, values, spec.keys)
                        redact = Redactor(list(values.values()))
                renderer = renderer_for(spec.harness)

                async def sink(chunk: str) -> None:
                    if renderer is None:
                        await buf.write(redact(chunk))
                    elif text := renderer.feed(chunk):
                        await buf.write(redact(text))

                res = await self._play_or_run(spec, attempt_id, sink)
                if renderer is not None and (tail := renderer.flush()):
                    await buf.write(redact(tail))
                if (
                    lease is not None
                    and (fresh := res.writeback.get(CODEX_AUTH))
                    and fresh != lease.auth_json
                ):
                    try:
                        await lease.save_back(fresh)
                    except CodexError as e:
                        await buf.write(f"\n[The refreshed Codex login was not stored: {e}]\n")
            exit_code, result = res.exit_code, redact(res.result)
            outcome = AttemptStatus.SUCCEEDED if res.exit_code == 0 else AttemptStatus.FAILED
        except asyncio.CancelledError:
            reason = self._live[attempt_id].cancel_reason if attempt_id in self._live else None
            if reason == "shutdown":
                await buf.write("\n[Themis shut down while this attempt was running]\n")
            else:
                outcome = AttemptStatus.CANCELLED
                await buf.write("\n[Cancelled]\n")
        except (CellError, CodexError) as e:
            await buf.write(f"\n[Cell error] {e}\n")
        except Exception as e:
            log.exception("attempt %s crashed", attempt_id)
            await buf.write(f"\n[Unexpected error] {e}\n")
        await self._finish(attempt_id, spec.task_id, buf, outcome, exit_code, result, tz)

    async def _key_values(self, spec: CellSpec) -> dict[int, str]:
        """The readable values of the keys this run uses, by id."""
        need = set(spec.keys) | {i for server in spec.mcp for i in server.key_ids}
        async with self.maker() as s:
            rows = (await s.scalars(select(Secret).where(Secret.id.in_(need)))).all()
        values: dict[int, str] = {}
        for row in rows:
            value = decrypt(row.value_encrypted)
            if value is None:
                raise CellError(
                    "A stored key could not be read. If THEMIS_SECRET_KEY changed, add the keys again."
                )
            values[row.id] = value
        if set(values) != need:
            raise CellError("A key this agent uses was removed before its run started")
        return values

    async def _play_or_run(self, spec: CellSpec, attempt_id: int, sink) -> CellResult:
        """A task that plays a workflow hands it to the workflow engine; everything else runs in a cell."""
        if spec.harness != "workflow":
            return await self.cells.run(spec, sink)
        if self.workflows is None:
            raise CellError("Workflows are not available")
        ok, result = await self.workflows.run_for_task(
            spec.project_id, spec.task_id, spec.workflow_id, attempt_id, sink
        )
        return CellResult(exit_code=0 if ok else 1, result=result)

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
