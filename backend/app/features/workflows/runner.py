import asyncio
import logging
from collections.abc import Callable

from sqlalchemy import and_, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload

from app.execution.harnesses.prompts import log_tail
from app.features.workflows.approvals import ApprovalGates
from app.features.workflows.context import _Ctx
from app.features.workflows.folders import WorkflowFolders
from app.features.workflows.graph import (
    MOUNT,
    Graph,
    GraphNode,
    LoopError,
    NodeError,
)
from app.features.workflows.nodes import NodeHandlers
from app.features.workflows.triggers import StatusTriggers
from app.features.workflows.walk import Gate, Lane, MergeIn, Outcome, Prev, Resume, Walk, prev_from
from app.persistence.models import (
    Attempt,
    AttemptStatus,
    NodeStatus,
    RunStatus,
    Task,
    TaskStage,
    Workflow,
    WorkflowNodeRun,
    WorkflowRun,
    utcnow,
)

log = logging.getLogger("themis.workflows")

MAX_NESTING = 5  # workflows playing tasks that play workflows...


class WorkflowRunner:
    """Own run traversal, recovery, cancellation and recorded outcomes."""

    POLL_SECONDS = 0.5
    GATE_POLL_SECONDS = 5
    RESTARTED = "Themis restarted while this node was running"

    def __init__(self, maker: async_sessionmaker[AsyncSession], scheduler: Callable[[], object]) -> None:
        self.maker = maker
        self._scheduler = scheduler  # a getter, so the current scheduler is always the one used
        self._live: dict[int, asyncio.Task] = {}
        self._parked: list[int] = []  # runs reconcile() kept alive for resume_parked() to pick up
        self._stopping = False
        self.approvals = ApprovalGates(maker, lambda: self.GATE_POLL_SECONDS)
        self.folders = WorkflowFolders(maker)
        self.nodes = NodeHandlers(
            maker, scheduler, self.folders, self.approvals, self._update_node, lambda: self.POLL_SECONDS
        )
        self.triggers = StatusTriggers(maker, self.start, lambda: self._stopping)

    async def reconcile(self) -> None:
        """After a restart nothing is running: close dangling runs and nodes. The exception is a run parked at an
        approval gate: a person may take days to answer, so it stays open for `resume_parked`. Only a top-level run can
        stay: one that a task plays dies with that task's attempt, which the scheduler closes on its own restart."""
        async with self.maker() as s:
            now = utcnow()
            keep = list(
                await s.scalars(
                    select(WorkflowRun.id)
                    .where(
                        WorkflowRun.status == RunStatus.RUNNING,
                        WorkflowRun.parent_run_id.is_(None),
                        WorkflowRun.trigger != "task",
                        WorkflowRun.id.in_(
                            select(WorkflowNodeRun.run_id).where(WorkflowNodeRun.status == NodeStatus.WAITING)
                        ),
                    )
                    .order_by(WorkflowRun.id)
                )
            )
            await s.execute(
                update(WorkflowNodeRun)
                .where(
                    or_(
                        WorkflowNodeRun.status == NodeStatus.RUNNING,
                        and_(
                            WorkflowNodeRun.status == NodeStatus.WAITING, WorkflowNodeRun.run_id.not_in(keep)
                        ),
                        # a graceful stop records the nodes it cut off as cancelled; in a run that carries on after
                        # the restart that is what happened to them: they were interrupted, and they failed
                        and_(
                            WorkflowNodeRun.status == NodeStatus.CANCELLED, WorkflowNodeRun.run_id.in_(keep)
                        ),
                    )
                )
                .values(status=NodeStatus.FAILED, finished_at=now, error=self.RESTARTED)
            )
            await s.execute(
                update(WorkflowRun)
                .where(WorkflowRun.status == RunStatus.RUNNING, WorkflowRun.id.not_in(keep))
                .values(
                    status=RunStatus.FAILED,
                    finished_at=now,
                    outcome="Themis restarted while this run was in progress",
                )
            )
            await s.commit()
        self._parked = keep

    async def shutdown(self) -> None:
        self._stopping = True
        self.triggers.close()
        for task in self._live.values():
            task.cancel()
        await asyncio.gather(*self._live.values(), return_exceptions=True)

    @property
    def active_runs(self) -> int:
        return len(self._live)

    async def _check_chain(self, s: AsyncSession, workflow_id: int, parent_run_id: int | None) -> None:
        """Refuse a run that is already running further up the chain of runs that led here."""
        depth = 0
        parent = parent_run_id
        while parent is not None:
            row = await s.get(WorkflowRun, parent)
            if row is None:
                break
            if row.workflow_id == workflow_id:
                raise LoopError(
                    "This workflow is already running further up the chain that led here, so it would loop."
                )
            depth += 1
            if depth >= MAX_NESTING:
                raise LoopError(f"Workflows are nested more than {MAX_NESTING} levels deep.")
            parent = row.parent_run_id

    async def start(
        self,
        project_id: int,
        workflow_id: int,
        graph: Graph,
        trigger: str = "test",
        parent_run_id: int | None = None,
        trigger_task_id: int | None = None,
        starts: list[str] | None = None,
        workdir_id: int | None = None,
        stage_task_id: int | None = None,
    ) -> int:
        """`starts` limits the run to those start/trigger nodes (a status trigger must not also fire the others).
        `workdir_id` is the working folder the run begins in, for steps that ask to continue in it. `stage_task_id`
        is the task this run is a stage of, whose title and description its agents are given."""
        async with self.maker() as s:
            await self._check_chain(s, workflow_id, parent_run_id)
            run = WorkflowRun(
                project_id=project_id,
                workflow_id=workflow_id,
                parent_run_id=parent_run_id,
                trigger=trigger,
                trigger_task_id=trigger_task_id,
                workdir_id=workdir_id,
                graph=graph.model_dump(),
            )
            s.add(run)
            await s.commit()
            run_id = run.id
        self._spawn(
            _Ctx(run_id, project_id, graph, trigger_task_id, stage_task_id, workdir_id), graph, starts
        )
        return run_id

    def _spawn(
        self, ctx: _Ctx, graph: Graph, starts: list[str] | None = None, resume: Resume | None = None
    ) -> None:
        task = asyncio.create_task(self._run(ctx, graph, starts, resume), name=f"workflow-run-{ctx.run_id}")
        self._live[ctx.run_id] = task
        task.add_done_callback(lambda _t, rid=ctx.run_id: self._live.pop(rid, None))

    async def resume_parked(self) -> None:
        """Pick up the runs `reconcile` kept open, at the approval gates they were parked at. Called once the scheduler
        is up, because the steps below a gate need it."""
        parked, self._parked = self._parked, []
        for run_id in parked:
            try:
                await self._resume(run_id)
            except Exception:  # one unreadable run must not keep the others parked: fail it and go on
                log.exception("could not resume workflow run %s", run_id)
                await self._finish(run_id, RunStatus.FAILED, "Themis could not pick this run up again")

    async def _resume(self, run_id: int) -> None:
        async with self.maker() as s:
            run = await s.get(WorkflowRun, run_id)
            rows = (
                await s.scalars(
                    select(WorkflowNodeRun)
                    .where(WorkflowNodeRun.run_id == run_id)
                    .order_by(WorkflowNodeRun.seq)
                )
            ).all()
        if run is None:
            return
        graph = Graph.model_validate(run.graph)
        waiting = [n for n in rows if n.status == NodeStatus.WAITING]
        gates = [Gate(n.node_id, n.id, prev_from((n.gate or {}).get("previous"))) for n in waiting]
        by_id = {n.id: n for n in graph.nodes}
        # what already failed: the run will end as failed, as it would have had it never stopped (a node that a restart
        # caught running is one of them)
        failed = [
            n
            for n in rows
            if n.status == NodeStatus.FAILED
            and not (n.kind == "agent" and by_id[n.node_id].config.get("onFailure") == "continue")
        ]
        failure = f"'{failed[0].label}' failed: {failed[0].error}" if failed else ""
        resume = Resume(
            gates=gates,
            ran={n.node_id for n in rows if n.status != NodeStatus.WAITING},
            seq=max((n.seq for n in rows), default=0),
            failure=failure,
        )
        ctx = _Ctx(run.id, run.project_id, graph, run.trigger_task_id, None, run.workdir_id)
        self._spawn(ctx, graph, None, resume)

    async def cancel_runs(self, project_id: int, board_id: int | None = None) -> int:
        """Cancel the runs going in a project, or those started by a task of one board (a halt). Returns how many."""
        async with self.maker() as s:
            query = select(WorkflowRun.id).where(
                WorkflowRun.project_id == project_id, WorkflowRun.status == RunStatus.RUNNING
            )
            if board_id is not None:
                query = query.join(Task, Task.id == WorkflowRun.trigger_task_id).where(
                    Task.board_id == board_id
                )
            ids = list(await s.scalars(query))
        return sum([await self.cancel(run_id) for run_id in ids])

    async def cancel(self, run_id: int) -> bool:
        task = self._live.get(run_id)
        if task is None:
            return False
        attempt_ids: list[int] = []
        async with (
            self.maker() as s
        ):  # stop the cells the running nodes are waiting for (branches run side by side)
            nodes = (
                await s.execute(
                    select(WorkflowNodeRun.task_id, WorkflowNodeRun.attempt_id).where(
                        WorkflowNodeRun.run_id == run_id, WorkflowNodeRun.status == NodeStatus.RUNNING
                    )
                )
            ).all()
            for node in nodes:
                attempt_id = node.attempt_id
                if attempt_id is None and node.task_id:  # the engine has not noticed the attempt yet
                    attempt_id = await s.scalar(
                        select(Attempt.id)
                        .where(Attempt.task_id == node.task_id, Attempt.status == AttemptStatus.RUNNING)
                        .order_by(Attempt.id.desc())
                        .limit(1)
                    )
                if attempt_id:
                    attempt_ids.append(attempt_id)
        # The run and its nodes first, then their cells. The other way round, a node that is waiting for its attempt
        # sees it cancelled before it is cancelled itself, and records the cancel as a failure ("The task was
        # cancelled.") instead of as cancelled.
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        for attempt_id in attempt_ids:
            await self._scheduler().cancel(attempt_id)  # type: ignore[attr-defined]
        return True

    async def run_for_task(self, project_id: int, task_id: int, attempt_id: int, write) -> tuple[bool, str]:
        """Play a task's workflows (its stages) one after the other for one attempt of that task. Progress goes into the
        attempt's log as it happens. A stage that fails ends the attempt and the stages after it stay not started.
        Returns whether every stage succeeded, and the task's result: what each stage that ran concluded (see
        `_stage_report`), one section per stage when there are several.

        Each stage's run starts with the working folder the stage before it ended in (the first one with the folder
        the task was made to continue in, if any). Whether a step really works there is up to the step: only one that
        asks to continue does, so stages are connected without any of them losing its fresh folder by default."""
        async with self.maker() as s:
            task = await s.get(Task, task_id)
            workdir = ((task.run_options or {}).get("workdir") or None) if task else None
            plan = [
                (stage_id, workflow_id, name)
                for stage_id, workflow_id, name in (
                    await s.execute(
                        select(TaskStage.id, TaskStage.workflow_id, Workflow.name)
                        .join(Workflow, Workflow.id == TaskStage.workflow_id)
                        .where(TaskStage.task_id == task_id)
                        .order_by(TaskStage.position)
                    )
                ).all()
            ]
            # what a task's stages show is always its latest attempt, so this one starts them all over
            await s.execute(
                update(TaskStage).where(TaskStage.task_id == task_id).values(workflow_run_id=None)
            )
            await s.commit()
        if not plan:
            await write(
                "[Cell error] The workflow this task plays no longer exists. Pick another one in the task.\n"
            )
            return False, ""
        ok = True
        reports: list[tuple[str, str]] = []
        for i, (stage_id, workflow_id, name) in enumerate(plan, start=1):
            if len(plan) > 1:
                await write(f"Stage {i} of {len(plan)}\n")
            ok, report, ended_in = await self._play_stage(
                project_id, task_id, workflow_id, stage_id, attempt_id, write, workdir
            )
            reports.append((name, report))
            if ended_in:
                # kept on the attempt as it goes, so whatever waits for this task can continue where it got to
                workdir = ended_in
                async with self.maker() as s:
                    await s.execute(
                        update(Attempt).where(Attempt.id == attempt_id).values(workdir_id=workdir)
                    )
                    await s.commit()
            if not ok:
                break
        # the result is what the stages produced (a PR link, a summary), so it is on the task without opening a run
        if len(reports) == 1:
            return ok, reports[0][1]
        return ok, "\n\n".join(f"## {name}\n{report}".rstrip() for name, report in reports)

    async def _play_stage(
        self,
        project_id: int,
        task_id: int,
        workflow_id: int,
        stage_id: int,
        attempt_id: int,
        write,
        workdir_id: int | None = None,
    ) -> tuple[bool, str, int | None]:
        """Play one stage's workflow, starting in the working folder `workdir_id`, and wait for its run to end.
        Returns whether it succeeded, its outcome and the working folder it ended in."""
        async with self.maker() as s:
            wf = await s.get(Workflow, workflow_id)
            if wf is None or wf.project_id != project_id:
                await write(
                    "[Cell error] The workflow this task plays no longer exists. Pick another one in the task.\n"
                )
                return False, "", workdir_id
            # a workflow node waiting for this task is the parent of the run we are about to start
            parent = await s.scalar(
                select(WorkflowNodeRun.run_id)
                .where(WorkflowNodeRun.task_id == task_id, WorkflowNodeRun.status == NodeStatus.RUNNING)
                .order_by(WorkflowNodeRun.id.desc())
                .limit(1)
            )
        graph = Graph.model_validate(wf.graph)
        if not graph.start_nodes:
            await write(
                f'[Cell error] The workflow "{wf.name}" has no Start node, so there is nowhere to begin.\n'
            )
            return False, "", workdir_id
        try:
            run_id = await self.start(
                project_id,
                wf.id,
                graph,
                trigger="task",
                parent_run_id=parent,
                workdir_id=workdir_id,
                stage_task_id=task_id,
            )
        except LoopError as e:
            await write(f"[Cell error] {e}\n")
            return False, "", workdir_id
        async with self.maker() as s:
            await s.execute(update(Attempt).where(Attempt.id == attempt_id).values(workflow_run_id=run_id))
            await s.execute(update(TaskStage).where(TaskStage.id == stage_id).values(workflow_run_id=run_id))
            await s.commit()
        await write(f'Playing the workflow "{wf.name}" (run #{run_id})\n')
        seen: dict[int, str] = {}
        try:
            while True:
                await asyncio.sleep(self.POLL_SECONDS)
                async with self.maker() as s:
                    run = await s.scalar(
                        select(WorkflowRun)
                        .where(WorkflowRun.id == run_id)
                        .options(selectinload(WorkflowRun.nodes))
                        .execution_options(populate_existing=True)
                    )
                assert run is not None
                for n in run.nodes:
                    if n.status == NodeStatus.SKIPPED or seen.get(n.id) == n.status:
                        continue
                    if n.id not in seen:
                        await write(f"[{n.seq}] {n.label} ({n.kind})\n")
                    if n.status != NodeStatus.RUNNING:
                        await write(f"    {n.status}{': ' + n.error if n.error else ''}\n")
                    seen[n.id] = n.status
                if run.status != RunStatus.RUNNING:
                    break
        except asyncio.CancelledError:
            await self.cancel(run_id)  # the task was cancelled: stop what it started
            raise
        skipped = [n for n in run.nodes if n.status == NodeStatus.SKIPPED]
        if skipped:
            await write("Did not run: " + ", ".join(n.label for n in skipped) + "\n")
        await write(f"Workflow {run.status}{': ' + run.outcome if run.outcome else ''}\n")
        return run.status == RunStatus.SUCCEEDED, self._stage_report(run), run.workdir_id or workdir_id

    async def failure_for_attempt(self, attempt_id: int) -> dict | None:
        """Why a task that played workflows failed, for its ticket: the first step of the run it was playing that
        failed, with that step's own reason and log tail when the step ran a task. None when no step failed (the run
        was cancelled, or could not start), so the caller keeps what it knows."""
        async with self.maker() as s:
            attempt = await s.get(Attempt, attempt_id)
            if attempt is None or attempt.workflow_run_id is None:
                return None
            node = await s.scalar(
                select(WorkflowNodeRun)
                .where(
                    WorkflowNodeRun.run_id == attempt.workflow_run_id,
                    WorkflowNodeRun.status == NodeStatus.FAILED,
                )
                .order_by(WorkflowNodeRun.seq)
                .limit(1)
            )
            if node is None:
                return None
            step = await s.get(Attempt, node.attempt_id) if node.attempt_id else None
        step_failure = (step.failure if step is not None else None) or {}
        reason = step_failure.get("reason") or node.error or "The step failed."
        return {
            "source": step_failure.get("source", "themis"),
            "reason": f"Step '{node.label}' failed: {reason}",
            "action": step_failure.get("action", ""),
            "tail": step_failure.get("tail") or log_tail(node.log),
        }

    @staticmethod
    def _stage_report(run: WorkflowRun) -> str:
        """What a finished stage has to show: why it failed, or what its last agent or task reported. A workflow whose
        steps produce nothing falls back to what its End node said."""
        if run.status == RunStatus.SUCCEEDED:
            for n in reversed(run.nodes):
                if n.kind in ("agent", "task") and n.status == NodeStatus.SUCCEEDED and n.result.strip():
                    return n.result.strip()
        return run.outcome

    async def _run(
        self, ctx: _Ctx, graph: Graph, starts: list[str] | None = None, resume: Resume | None = None
    ) -> None:
        walk = Walk(graph, starts, resume)
        gate_rows = {g.node_id: g.nr_id for g in resume.gates} if resume else {}
        done: dict[str, Outcome] = {}
        carried_on: set[str] = set()  # failed nodes the workflow continued after
        running: dict[asyncio.Task, tuple[GraphNode, Prev | None, Lane, int]] = {}
        seq = resume.seq if resume else 0
        hard_fail, note = False, ""
        workdir = (
            ctx.workdir_id
        )  # where the run's last step worked: what the next stage of a task starts with
        cancelled = False
        try:
            while True:
                # every lane that is idle starts its next node; the lanes are what run at the same time
                for lane in list(walk.lanes.values()):
                    while not lane.busy and lane.queue:
                        node_id, prev, inputs = lane.queue.popleft()
                        if hard_fail and lane.parent is not None:
                            # a branch failed: the other branches finish what they are doing and start nothing new
                            lane.queue.clear()
                            break
                        node = walk.nodes[node_id]
                        # a gate picked up again keeps its record (and its place in the run's order)
                        reuse = gate_rows.get(node_id)
                        if reuse is None:
                            seq += 1
                        task = asyncio.create_task(self._execute_node(ctx, node, seq, prev, inputs, reuse))
                        running[task] = (node, prev, lane, seq)
                        lane.busy = True
                if not running:
                    break
                finished, _ = await asyncio.wait(list(running), return_when=asyncio.FIRST_COMPLETED)
                for task in sorted(finished, key=lambda t: running[t][3]):
                    node, prev, lane, _seq = running.pop(task)
                    lane.busy = False
                    outcome = task.result()
                    done[node.id] = outcome
                    workdir = outcome.workdir_id or workdir
                    if node.kind == "end":
                        ended = node.config.get("outcome", "success")
                        note = node.config.get("note", "").strip() or {
                            "success": "Finished",
                            "failed": "Ended as failed",
                            "review": "Needs review",
                        }.get(ended, ended)
                        hard_fail = hard_fail or ended == "failed"
                    failed = False
                    if outcome.status == NodeStatus.FAILED:
                        if node.kind == "agent" and node.config.get("onFailure") == "continue":
                            carried_on.add(node.id)
                        else:
                            failed = hard_fail = True
                            note = note or f"'{node.label or node.kind}' failed: {outcome.error}"
                    walk.finish(node, outcome, prev, lane, failed, ctx.workdir_id)
            await self._record_unreached(
                ctx, graph, done, carried_on, seq, stopped=hard_fail, ran=resume.ran if resume else set()
            )
            if resume and resume.failure and not hard_fail:
                hard_fail, note = (
                    True,
                    resume.failure,
                )  # something failed before the restart: the run still fails
            await self._finish(
                ctx.run_id, RunStatus.FAILED if hard_fail else RunStatus.SUCCEEDED, note, workdir
            )
        except asyncio.CancelledError:
            cancelled = True
        except Exception as e:
            await self._stop_nodes(running)
            log.exception("workflow run %s crashed", ctx.run_id)
            await self._finish(ctx.run_id, RunStatus.FAILED, f"Unexpected error: {e}", workdir)
        if cancelled:
            # outside the `except`, for the reason given in _execute_node
            await self._stop_nodes(running)
            if not self._stopping:
                await self._cancelled(ctx.run_id)
            raise asyncio.CancelledError

    @staticmethod
    async def _stop_nodes(running: dict) -> None:
        """The run ended early: stop the nodes still going. Each marks its own record as cancelled."""
        for task in running:
            task.cancel()
        await asyncio.gather(*running, return_exceptions=True)

    async def _execute_node(
        self,
        ctx: _Ctx,
        node: GraphNode,
        seq: int,
        prev: Prev | None,
        inputs: list[MergeIn] | None = None,
        reuse: int | None = None,
    ) -> Outcome:
        """Run one node and record it. `reuse` is the record of an approval gate that is being picked up again."""
        label = node.label or node.kind.capitalize()
        if reuse is not None:
            nr_id = reuse
        else:
            async with self.maker() as s:
                row = WorkflowNodeRun(
                    run_id=ctx.run_id,
                    node_id=node.id,
                    kind=node.kind,
                    label=label,
                    seq=seq,
                    started_at=utcnow(),
                )
                s.add(row)
                await s.commit()
                nr_id = row.id
        cancelled = False
        try:
            outcome = await self.nodes.dispatch(ctx, nr_id, node, prev, inputs)
        except NodeError as e:
            outcome = Outcome(NodeStatus.FAILED, error=str(e))
        except asyncio.CancelledError:
            cancelled = True  # recorded below, outside this block (see there)
        except Exception as e:
            log.exception("workflow node %s crashed", node.id)
            outcome = Outcome(NodeStatus.FAILED, error=f"Unexpected error: {e}")
        if cancelled:
            if self._stopping and node.kind == "approval":
                raise asyncio.CancelledError  # Themis is stopping, not the run: the gate stays parked for the restart
            # Not inside the `except`: while it runs, the exception's traceback keeps alive whatever the cut-off work was
            # holding. A statement that was executing when the cancel arrived (an INSERT of a task, say) is finished by
            # its worker thread but never read, and SQLite keeps its write lock until that cursor is released. Writing
            # from inside the handler would wait for a lock this very task still holds.
            await self._update_node(
                nr_id, status=NodeStatus.CANCELLED, finished_at=utcnow(), error="The run was cancelled"
            )
            raise asyncio.CancelledError
        fields: dict = {
            "status": outcome.status,
            "finished_at": utcnow(),
            "result": outcome.result,
            "error": outcome.error,
        }
        if outcome.log:
            fields["log"] = outcome.log
        await self._update_node(nr_id, **fields)
        return outcome

    def is_live(self, run_id: int) -> bool:
        return run_id in self._live

    async def _update_node(self, nr_id: int, **fields) -> None:
        async with self.maker() as s:
            await s.execute(update(WorkflowNodeRun).where(WorkflowNodeRun.id == nr_id).values(**fields))
            await s.commit()

    async def _record_unreached(
        self,
        ctx: _Ctx,
        graph: Graph,
        done: dict[str, Outcome],
        carried_on: set[str],
        seq: int,
        stopped: bool = False,
        ran: set[str] | None = None,
    ) -> None:
        """A record for every node that never ran, saying why (so a missing checkmark is never a mystery). `ran` is what
        a resumed run did before it was picked up again: those nodes have their records already."""
        nodes = {n.id: n for n in graph.nodes}
        rows = []
        for n in graph.nodes:
            if (
                n.id in done or n.id in (ran or ()) or n.kind == "volume"
            ):  # a Folder is never a step: never "not run"
                continue
            seq += 1
            rows.append(
                WorkflowNodeRun(
                    run_id=ctx.run_id, node_id=n.id, kind=n.kind, label=n.label or n.kind.capitalize(), seq=seq,
                    status=NodeStatus.SKIPPED, error=self._why_skipped(n, graph, nodes, done, carried_on, stopped),
                )
            )  # fmt: skip
        if rows:
            async with self.maker() as s:
                s.add_all(rows)
                await s.commit()

    @staticmethod
    def _why_skipped(
        node: GraphNode,
        graph: Graph,
        nodes: dict[str, GraphNode],
        done: dict[str, Outcome],
        carried_on: set[str],
        stopped: bool = False,
    ) -> str:
        incoming = [e for e in graph.edges if e.target == node.id and e.sourceHandle != MOUNT]
        if not incoming:
            return "Not run: nothing leads to this node, so no Start node reaches it."
        for e in incoming:
            src = nodes[e.source]
            outcome = done.get(e.source)
            if outcome is None:
                continue
            name = src.label or src.kind
            if outcome.status == NodeStatus.FAILED and e.source not in carried_on:
                return f"Not run: '{name}' failed before this node."
            if src.kind == "condition" and (e.sourceHandle or "yes") != outcome.branch:
                return f"Not run: the condition '{name}' answered {outcome.branch}, which leads elsewhere."
        if stopped and any(e.source in done for e in incoming):
            return "Not run: a branch failed, so the branches still going started nothing new."
        return "Not run: the run never reached a node that leads here."

    async def _finish(self, run_id: int, status: str, outcome: str, workdir_id: int | None = None) -> None:
        async with self.maker() as s:
            await s.execute(
                update(WorkflowRun)
                .where(WorkflowRun.id == run_id)
                .values(status=status, finished_at=utcnow(), outcome=outcome, workdir_id=workdir_id)
            )
            await s.commit()

    async def _cancelled(self, run_id: int) -> None:
        async with self.maker() as s:
            await s.execute(
                update(WorkflowNodeRun)
                .where(
                    WorkflowNodeRun.run_id == run_id,
                    WorkflowNodeRun.status.in_([NodeStatus.RUNNING, NodeStatus.WAITING]),
                )
                .values(status=NodeStatus.CANCELLED, finished_at=utcnow(), error="The run was cancelled")
            )
            await s.execute(
                update(WorkflowRun)
                .where(WorkflowRun.id == run_id)
                .values(status=RunStatus.CANCELLED, finished_at=utcnow(), outcome="Cancelled")
            )
            await s.commit()

    async def decide(self, nr_id: int, approved: bool, note: str, by: str) -> bool:
        return await self.approvals.decide(nr_id, approved, note, by)
