"""Workflows: a graph of nodes drawn in the editor, and the engine that runs it.

A run starts from every Start (or Trigger) node and follows the edges. Nodes run one at a time, in order:

- Start / Trigger: begin the run.
- Task: create, update or run a task of the project. A task that becomes READY runs through the normal scheduler,
  and the node waits for it and takes over its log and result.
- Agent: a task handed to a Codex agent, with the node's instructions (and the previous result) as its description.
- Condition: checks the previous node's result or status and follows the `yes` or the `no` edges.
- End: records how the run ended.

A node that fails stops its branch (an Agent node can be told to carry on). Every node that did run gets a record
with its output and error; nodes that did not run get a record saying why.
"""

import asyncio
import logging
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from typing import Annotated, Literal

from pydantic import BaseModel, Field, model_validator
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from .app_settings import load_settings
from .models import (
    Attempt,
    AttemptStatus,
    NodeStatus,
    RunStatus,
    Task,
    TaskStatus,
    WorkflowNodeRun,
    WorkflowRun,
    utcnow,
)

log = logging.getLogger("themis.workflows")

Kind = Literal["start", "trigger", "task", "agent", "condition", "end"]
START_KINDS = ("start", "trigger")


class Position(BaseModel):
    x: float = 0
    y: float = 0


class GraphNode(BaseModel):
    id: str = Field(min_length=1, max_length=64, pattern=r"^[\w-]+$")
    kind: Kind
    label: str = Field(default="", max_length=100)
    config: dict[str, Annotated[str, Field(max_length=20_000)]] = Field(default_factory=dict)
    position: Position = Field(default_factory=Position)


class GraphEdge(BaseModel):
    id: str = Field(min_length=1, max_length=100)
    source: str
    target: str
    sourceHandle: str | None = Field(default=None, max_length=20)  # "yes" / "no" on a condition


class Graph(BaseModel):
    nodes: list[GraphNode] = Field(default_factory=list, max_length=200)
    edges: list[GraphEdge] = Field(default_factory=list, max_length=500)

    @model_validator(mode="after")
    def consistent(self) -> "Graph":
        ids = [n.id for n in self.nodes]
        if len(set(ids)) != len(ids):
            raise ValueError("Node ids must be unique")
        known = set(ids)
        for e in self.edges:
            if e.source not in known or e.target not in known:
                raise ValueError("An edge points at a node that does not exist")
        return self

    @property
    def start_nodes(self) -> list[GraphNode]:
        return [n for n in self.nodes if n.kind in START_KINDS]


class NodeError(Exception):
    """A node could not do its job; the message is shown to the user as the reason."""


@dataclass
class Prev:
    """What the node before this one produced (what a Condition checks)."""

    label: str
    status: str
    result: str


@dataclass
class Outcome:
    status: str  # NodeStatus.SUCCEEDED or FAILED
    result: str = ""
    log: str = ""
    error: str = ""
    branch: str | None = None  # a Condition's answer, "yes" or "no"


@dataclass
class _Ctx:
    run_id: int
    project_id: int


def evaluate_condition(config: dict[str, str], prev: Prev | None) -> tuple[bool, str]:
    """The answer, and a sentence explaining it for the log."""
    if prev is None:
        raise NodeError("This condition has nothing before it to check. Connect it after another node.")
    source = config.get("source", "result")
    operator = config.get("operator", "contains")
    value = config.get("value", "")
    actual = prev.result if source == "result" else prev.status
    a, v = actual.strip().casefold(), value.strip().casefold()
    answer = {
        "contains": v in a,
        "equals": a == v,
        "not_equals": a != v,
        "empty": not a,
    }.get(operator)
    if answer is None:
        raise NodeError(f"Unknown operator '{operator}'")
    shown = actual.strip().replace("\n", " ")
    shown = shown if len(shown) <= 120 else shown[:117] + "..."
    what = "previous result" if source == "result" else "previous status"
    return (
        answer,
        f"The {what} from '{prev.label}' is: {shown or '(empty)'}\nCheck: {operator.replace('_', ' ')} {value!r} -> {'yes' if answer else 'no'}",
    )


def _failed_message(exit_code: int | None) -> str:
    how = f"with exit code {exit_code}" if exit_code is not None else "before it could finish"
    return f"The task failed {how}. The log shows what happened."


class WorkflowRunner:
    """Runs workflows in the background and records every node of every run."""

    POLL_SECONDS = 0.5  # how often a node waiting for a task looks at it

    def __init__(self, maker: async_sessionmaker[AsyncSession], scheduler: Callable[[], object]) -> None:
        self.maker = maker
        self._scheduler = scheduler  # a getter, so the current scheduler is always the one used
        self._live: dict[int, asyncio.Task] = {}
        self._stopping = False

    # lifecycle

    async def reconcile(self) -> None:
        """After a restart nothing is running: close dangling runs and nodes."""
        async with self.maker() as s:
            now = utcnow()
            await s.execute(
                update(WorkflowNodeRun)
                .where(WorkflowNodeRun.status == NodeStatus.RUNNING)
                .values(
                    status=NodeStatus.FAILED,
                    finished_at=now,
                    error="ThemisForge restarted while this node was running",
                )
            )
            await s.execute(
                update(WorkflowRun)
                .where(WorkflowRun.status == RunStatus.RUNNING)
                .values(
                    status=RunStatus.FAILED,
                    finished_at=now,
                    outcome="ThemisForge restarted while this run was in progress",
                )
            )
            await s.commit()

    async def shutdown(self) -> None:
        self._stopping = True
        for task in self._live.values():
            task.cancel()
        await asyncio.gather(*self._live.values(), return_exceptions=True)

    @property
    def active_runs(self) -> int:
        return len(self._live)

    async def start(self, project_id: int, graph: Graph, trigger: str = "test") -> int:
        async with self.maker() as s:
            run = WorkflowRun(project_id=project_id, trigger=trigger, graph=graph.model_dump())
            s.add(run)
            await s.commit()
            run_id = run.id
        task = asyncio.create_task(self._run(_Ctx(run_id, project_id), graph), name=f"workflow-run-{run_id}")
        self._live[run_id] = task
        task.add_done_callback(lambda _t, rid=run_id: self._live.pop(rid, None))
        return run_id

    async def cancel(self, run_id: int) -> bool:
        task = self._live.get(run_id)
        if task is None:
            return False
        async with self.maker() as s:  # stop the cell the current node is waiting for
            attempt_id = await s.scalar(
                select(WorkflowNodeRun.attempt_id).where(
                    WorkflowNodeRun.run_id == run_id, WorkflowNodeRun.status == NodeStatus.RUNNING
                )
            )
        if attempt_id:
            await self._scheduler().cancel(attempt_id)  # type: ignore[attr-defined]
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        return True

    # the run

    async def _run(self, ctx: _Ctx, graph: Graph) -> None:
        nodes = {n.id: n for n in graph.nodes}
        outgoing: dict[str, list[GraphEdge]] = {}
        for e in graph.edges:
            outgoing.setdefault(e.source, []).append(e)
        queue: deque[tuple[str, Prev | None]] = deque((n.id, None) for n in graph.start_nodes)
        done: dict[str, Outcome] = {}
        carried_on: set[str] = set()  # failed nodes the workflow continued after
        seq = 0
        hard_fail, note = False, ""
        try:
            while queue:
                node_id, prev = queue.popleft()
                if node_id in done:
                    continue
                node = nodes[node_id]
                seq += 1
                outcome = await self._execute_node(ctx, node, seq, prev)
                done[node_id] = outcome
                if node.kind == "end":
                    ended = node.config.get("outcome", "success")
                    note = node.config.get("note", "").strip() or {
                        "success": "Finished",
                        "failed": "Ended as failed",
                        "review": "Needs review",
                    }.get(ended, ended)
                    hard_fail = hard_fail or ended == "failed"
                if outcome.status == NodeStatus.FAILED:
                    if node.kind == "agent" and node.config.get("onFailure") == "continue":
                        carried_on.add(node_id)
                    else:
                        hard_fail = True
                        note = note or f"'{node.label or node.kind}' failed: {outcome.error}"
                        continue
                for e in outgoing.get(node_id, []):
                    if node.kind == "condition" and (e.sourceHandle or "yes") != outcome.branch:
                        continue
                    queue.append((e.target, Prev(node.label or node.kind, outcome.status, outcome.result)))
            await self._record_unreached(ctx, graph, done, carried_on, seq)
            await self._finish(ctx.run_id, RunStatus.FAILED if hard_fail else RunStatus.SUCCEEDED, note)
        except asyncio.CancelledError:
            if not self._stopping:
                await self._cancelled(ctx.run_id)
            raise
        except Exception as e:
            log.exception("workflow run %s crashed", ctx.run_id)
            await self._finish(ctx.run_id, RunStatus.FAILED, f"Unexpected error: {e}")

    async def _execute_node(self, ctx: _Ctx, node: GraphNode, seq: int, prev: Prev | None) -> Outcome:
        label = node.label or node.kind.capitalize()
        async with self.maker() as s:
            row = WorkflowNodeRun(
                run_id=ctx.run_id, node_id=node.id, kind=node.kind, label=label, seq=seq, started_at=utcnow()
            )
            s.add(row)
            await s.commit()
            nr_id = row.id
        try:
            outcome = await self._dispatch(ctx, nr_id, node, prev)
        except NodeError as e:
            outcome = Outcome(NodeStatus.FAILED, error=str(e))
        except asyncio.CancelledError:
            await self._update_node(
                nr_id, status=NodeStatus.CANCELLED, finished_at=utcnow(), error="The run was cancelled"
            )
            raise
        except Exception as e:
            log.exception("workflow node %s crashed", node.id)
            outcome = Outcome(NodeStatus.FAILED, error=f"Unexpected error: {e}")
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

    async def _dispatch(self, ctx: _Ctx, nr_id: int, node: GraphNode, prev: Prev | None) -> Outcome:
        c = node.config
        if node.kind in START_KINDS:
            return Outcome(NodeStatus.SUCCEEDED, log="Run started.\n")
        if node.kind == "end":
            return Outcome(
                NodeStatus.SUCCEEDED,
                log=f"Workflow ended: {c.get('outcome', 'success')}.\n{c.get('note', '')}".strip() + "\n",
            )
        if node.kind == "condition":
            answer, text = evaluate_condition(c, prev)
            return Outcome(
                NodeStatus.SUCCEEDED,
                log=text + "\n",
                result="yes" if answer else "no",
                branch="yes" if answer else "no",
            )
        if node.kind == "agent":
            return await self._agent(ctx, nr_id, node, prev)
        return await self._task(ctx, nr_id, node)

    # task and agent nodes

    async def _agent(self, ctx: _Ctx, nr_id: int, node: GraphNode, prev: Prev | None) -> Outcome:
        c = node.config
        instructions = c.get("instructions", "").strip()
        if not instructions:
            raise NodeError("This agent has no instructions. Open the node and tell it what to do.")
        if prev and prev.result.strip():
            instructions += f"\n\nResult of the previous step ({prev.label}):\n{prev.result.strip()}"
        title = node.label or "Agent"
        async with self.maker() as s:
            task = Task(
                project_id=ctx.project_id, title=title, description=instructions, status=TaskStatus.READY,
                harness=c.get("harness", "codex"), position=await self._next_position(s, ctx.project_id, TaskStatus.READY),
            )  # fmt: skip
            s.add(task)
            await s.commit()
            task_id = task.id
        await self._update_node(nr_id, task_id=task_id)
        return await self._wait_for_task(nr_id, task_id, before=0)

    async def _task(self, ctx: _Ctx, nr_id: int, node: GraphNode) -> Outcome:
        c = node.config
        action = c.get("action", "create")
        title = c.get("title", "").strip()
        if not title:
            raise NodeError("The task title is empty. Open the node and fill it in.")
        target = c.get("status", "inbox")
        if target not in {s.value for s in TaskStatus} or target == TaskStatus.RUNNING:
            raise NodeError(f"'{target}' is not a status a workflow can move a task to")
        async with self.maker() as s:
            before = 0
            if action == "create":
                task = Task(
                    project_id=ctx.project_id, title=title, description=c.get("description", ""), status=target,
                    position=await self._next_position(s, ctx.project_id, target),
                )  # fmt: skip
                s.add(task)
                note = f'Created task "{title}" in {target}.'
            else:
                task = await s.scalar(
                    select(Task)
                    .where(Task.project_id == ctx.project_id, Task.title == title)
                    .order_by(Task.id.desc())
                    .limit(1)
                )
                if task is None:
                    raise NodeError(f'There is no task titled "{title}" in this project.')
                if task.status == TaskStatus.RUNNING:
                    raise NodeError(f'The task "{title}" is already running.')
                before = (
                    await s.scalar(
                        select(func.coalesce(func.max(Attempt.id), 0)).where(Attempt.task_id == task.id)
                    )
                    or 0
                )
                if action == "run":
                    task.status, task.next_run_at = TaskStatus.READY, None
                    note = f'Started task "{title}".'
                else:
                    task.status = target
                    task.next_run_at = None
                    if c.get("description", "").strip():
                        task.description = c["description"]
                    note = f'Updated task "{title}": now {target}.'
            await s.commit()
            task_id, becomes_ready = task.id, task.status == TaskStatus.READY
        await self._update_node(nr_id, task_id=task_id)
        if becomes_ready:
            return await self._wait_for_task(nr_id, task_id, before)
        return Outcome(NodeStatus.SUCCEEDED, log=note + "\n", result=note)

    async def _wait_for_task(self, nr_id: int, task_id: int, before: int) -> Outcome:
        """Let the scheduler run the task, mirror its log into the node, and report how the attempt ended."""
        self._scheduler().wake()  # type: ignore[attr-defined]
        async with self.maker() as s:
            cfg = await load_settings(s)
        deadline = time.monotonic() + cfg.cell_timeout_seconds + 600
        shown: tuple[int, str] = (0, "")
        while True:
            await asyncio.sleep(self.POLL_SECONDS)
            async with self.maker() as s:
                attempt = await s.scalar(
                    select(Attempt)
                    .where(Attempt.task_id == task_id, Attempt.id > before)
                    .order_by(Attempt.id.desc())
                    .limit(1)
                )
                task = await s.get(Task, task_id)
            if attempt is not None:
                if (attempt.id, attempt.log) != shown:
                    shown = (attempt.id, attempt.log)
                    await self._update_node(
                        nr_id, attempt_id=attempt.id, log=attempt.log, result=attempt.result
                    )
                if attempt.status != AttemptStatus.RUNNING:
                    if attempt.status == AttemptStatus.SUCCEEDED:
                        return Outcome(NodeStatus.SUCCEEDED, result=attempt.result, log=attempt.log)
                    why = (
                        "The task was cancelled."
                        if attempt.status == AttemptStatus.CANCELLED
                        else _failed_message(attempt.exit_code)
                    )
                    return Outcome(NodeStatus.FAILED, result=attempt.result, log=attempt.log, error=why)
            elif task is None:
                raise NodeError("The task was deleted while the workflow was waiting for it.")
            elif task.status not in (TaskStatus.READY, TaskStatus.RUNNING):
                raise NodeError(f"The task was moved to {task.status} before it could run.")
            if time.monotonic() > deadline:
                raise NodeError("Timed out waiting for the task to run.")

    # records

    @staticmethod
    async def _next_position(s: AsyncSession, project_id: int, status: str) -> float:
        top = await s.scalar(
            select(func.max(Task.position)).where(Task.project_id == project_id, Task.status == status)
        )
        return (top or 0.0) + 1.0

    async def _update_node(self, nr_id: int, **fields) -> None:
        async with self.maker() as s:
            await s.execute(update(WorkflowNodeRun).where(WorkflowNodeRun.id == nr_id).values(**fields))
            await s.commit()

    async def _record_unreached(
        self, ctx: _Ctx, graph: Graph, done: dict[str, Outcome], carried_on: set[str], seq: int
    ) -> None:
        """A record for every node that never ran, saying why (so a missing checkmark is never a mystery)."""
        nodes = {n.id: n for n in graph.nodes}
        rows = []
        for n in graph.nodes:
            if n.id in done:
                continue
            seq += 1
            rows.append(
                WorkflowNodeRun(
                    run_id=ctx.run_id, node_id=n.id, kind=n.kind, label=n.label or n.kind.capitalize(), seq=seq,
                    status=NodeStatus.SKIPPED, error=self._why_skipped(n, graph, nodes, done, carried_on),
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
    ) -> str:
        incoming = [e for e in graph.edges if e.target == node.id]
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
        return "Not run: the run never reached a node that leads here."

    async def _finish(self, run_id: int, status: str, outcome: str) -> None:
        async with self.maker() as s:
            await s.execute(
                update(WorkflowRun)
                .where(WorkflowRun.id == run_id)
                .values(status=status, finished_at=utcnow(), outcome=outcome)
            )
            await s.commit()

    async def _cancelled(self, run_id: int) -> None:
        async with self.maker() as s:
            await s.execute(
                update(WorkflowNodeRun)
                .where(WorkflowNodeRun.run_id == run_id, WorkflowNodeRun.status == NodeStatus.RUNNING)
                .values(status=NodeStatus.CANCELLED, finished_at=utcnow(), error="The run was cancelled")
            )
            await s.execute(
                update(WorkflowRun)
                .where(WorkflowRun.id == run_id)
                .values(status=RunStatus.CANCELLED, finished_at=utcnow(), outcome="Cancelled")
            )
            await s.commit()
