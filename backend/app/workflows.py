"""Workflows: a graph of nodes drawn in the editor, and the engine that runs it.

A run starts from every Start (or Trigger) node and follows the edges. Nodes run one at a time, in order:

- Start / Trigger: begin the run. A Trigger set to "a task moves into a status" starts a run by itself, whenever a task
  of the project moves into that status (see `WorkflowRunner._fire`). The run remembers that task.
- Task: create, update or run a task of the project, or move the task that started the run. A task that becomes READY runs through the normal scheduler,
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

from pydantic import BaseModel, Field, ValidationError, model_validator
from sqlalchemy import event, func, inspect, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import Session, selectinload

from .app_settings import load_settings
from .models import (
    Agent,
    Attempt,
    AttemptStatus,
    NodeStatus,
    RunStatus,
    Task,
    TaskStatus,
    Workflow,
    WorkflowNodeRun,
    WorkflowRun,
    utcnow,
)
from .profiles import ProfileOverrides
from .volumes import MountRef

log = logging.getLogger("themis.workflows")

MAX_NESTING = 5  # workflows playing tasks that play workflows...

Kind = Literal["start", "trigger", "task", "agent", "condition", "end", "volume"]

# A "mount" line joins a Folder (volume) node to an Agent node: it hands that folder to the agent. It is not a step, so
# the run never follows it.
MOUNT = "mount"
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
    sourceHandle: str | None = Field(
        default=None, max_length=20
    )  # "yes" / "no" on a condition, "mount" on a folder
    targetHandle: str | None = Field(default=None, max_length=20)  # "mount" where a folder joins an agent


class Graph(BaseModel):
    nodes: list[GraphNode] = Field(default_factory=list, max_length=200)
    edges: list[GraphEdge] = Field(default_factory=list, max_length=500)

    @model_validator(mode="after")
    def consistent(self) -> "Graph":
        ids = [n.id for n in self.nodes]
        if len(set(ids)) != len(ids):
            raise ValueError("Node ids must be unique")
        known = {n.id: n for n in self.nodes}
        for e in self.edges:
            if e.source not in known or e.target not in known:
                raise ValueError("An edge points at a node that does not exist")
            source, target = known[e.source], known[e.target]
            if e.sourceHandle == MOUNT:
                if source.kind != "volume" or target.kind != "agent":
                    raise ValueError("A folder can only be handed to an Agent node")
            elif "volume" in (source.kind, target.kind):
                raise ValueError("A Folder node is not a step: join it to an Agent node's folder point")
        return self

    def mounts_for(self, node_id: str) -> list[dict]:
        """The folders handed to an agent node by lines from Folder nodes, as {"volume_id", "mode"}."""
        nodes = {n.id: n for n in self.nodes}
        out = []
        for e in self.edges:
            if e.target != node_id or e.sourceHandle != MOUNT:
                continue
            folder = nodes[e.source]
            raw = folder.config.get("volumeId", "").strip()
            if not raw.isdigit():
                raise NodeError(
                    f"The folder '{folder.label or 'Folder'}' has no folder chosen. Open it and pick one."
                )
            mode = folder.config.get("mode", "rw")
            out.append({"volume_id": int(raw), "mode": mode if mode in ("ro", "rw") else "rw"})
        return out

    def status_triggers(self, status: str | None = None) -> list[GraphNode]:
        """The Trigger nodes that start a run when a task moves into a status (into `status`, or any when None)."""
        return [
            n
            for n in self.nodes
            if n.kind == "trigger"
            and n.config.get("type") == "task_status"
            and (status is None or n.config.get("status") == status)
        ]

    @property
    def start_nodes(self) -> list[GraphNode]:
        return [n for n in self.nodes if n.kind in START_KINDS]


class NodeError(Exception):
    """A node could not do its job; the message is shown to the user as the reason."""


class LoopError(Exception):
    """A workflow would start itself again through the tasks it plays, or nests too deep."""


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
    graph: Graph
    trigger_task_id: int | None = None  # the task whose move into a status started this run


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
        self._firing: set[asyncio.Task] = set()
        # Every task that moves into a status is noticed where it is saved, so the board, the API, the scheduler and
        # workflow nodes all count, without each of them having to report it.
        event.listen(Session, "after_flush", self._note_moves)
        event.listen(Session, "after_commit", self._fire_moves)
        event.listen(Session, "after_rollback", self._drop_moves)

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
                    error="Themis restarted while this node was running",
                )
            )
            await s.execute(
                update(WorkflowRun)
                .where(WorkflowRun.status == RunStatus.RUNNING)
                .values(
                    status=RunStatus.FAILED,
                    finished_at=now,
                    outcome="Themis restarted while this run was in progress",
                )
            )
            await s.commit()

    async def shutdown(self) -> None:
        self._stopping = True
        event.remove(Session, "after_flush", self._note_moves)
        event.remove(Session, "after_commit", self._fire_moves)
        event.remove(Session, "after_rollback", self._drop_moves)
        for firing in self._firing:
            firing.cancel()
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
    ) -> int:
        """`starts` limits the run to those start/trigger nodes (a status trigger must not also fire the others)."""
        async with self.maker() as s:
            await self._check_chain(s, workflow_id, parent_run_id)
            run = WorkflowRun(
                project_id=project_id,
                workflow_id=workflow_id,
                parent_run_id=parent_run_id,
                trigger=trigger,
                trigger_task_id=trigger_task_id,
                graph=graph.model_dump(),
            )
            s.add(run)
            await s.commit()
            run_id = run.id
        task = asyncio.create_task(
            self._run(_Ctx(run_id, project_id, graph, trigger_task_id), graph, starts),
            name=f"workflow-run-{run_id}",
        )
        self._live[run_id] = task
        task.add_done_callback(lambda _t, rid=run_id: self._live.pop(rid, None))
        return run_id

    # runs started by a task moving into a status

    def _ours(self, session: Session) -> bool:
        return session.get_bind() is self.maker.kw["bind"].sync_engine

    def _note_moves(self, session: Session, _ctx) -> None:
        """Remember the tasks this flush moved into a status (or created in one); they count once the commit succeeds."""
        if not self._ours(session):
            return
        for obj in (*session.new, *session.dirty):
            if (
                isinstance(obj, Task)
                and (h := inspect(obj).attrs.status.history).added
                and h.added != h.deleted
            ):
                session.info.setdefault("status_moves", []).append((obj.project_id, obj.id, h.added[0]))

    def _drop_moves(self, session: Session) -> None:
        if self._ours(session):
            session.info.pop("status_moves", None)

    def _fire_moves(self, session: Session) -> None:
        if not self._ours(session):  # another runner's session (several exist in tests): leave its list alone
            return
        moves = session.info.pop("status_moves", None)
        if moves and not self._stopping:
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
                    if await self._belongs_to_agent_node(s, task_id):
                        continue  # the task an Agent node made for itself is part of that workflow, not board work
                    workflows = (
                        await s.scalars(select(Workflow).where(Workflow.project_id == project_id))
                    ).all()
                    for wf in workflows:
                        graph = Graph.model_validate(wf.graph)
                        starts = [n.id for n in graph.status_triggers(status)]
                        if not starts or await self._recently_started(
                            s, wf.id, task_id, cfg.start_cooldown_seconds
                        ):
                            continue
                        try:
                            await self.start(
                                project_id,
                                wf.id,
                                graph,
                                trigger="status",
                                trigger_task_id=task_id,
                                starts=starts,
                            )
                        except LoopError:
                            log.warning("workflow %s not started by task %s: it would loop", wf.id, task_id)
        except Exception:
            log.exception("starting workflows for moved tasks failed")

    @staticmethod
    async def _belongs_to_agent_node(s: AsyncSession, task_id: int) -> bool:
        return bool(
            await s.scalar(
                select(WorkflowNodeRun.id)
                .where(WorkflowNodeRun.task_id == task_id, WorkflowNodeRun.kind == "agent")
                .limit(1)
            )
        )

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

    async def cancel(self, run_id: int) -> bool:
        task = self._live.get(run_id)
        if task is None:
            return False
        async with self.maker() as s:  # stop the cell the current node is waiting for
            node = (
                await s.execute(
                    select(WorkflowNodeRun.task_id, WorkflowNodeRun.attempt_id).where(
                        WorkflowNodeRun.run_id == run_id, WorkflowNodeRun.status == NodeStatus.RUNNING
                    )
                )
            ).first()
            attempt_id = node.attempt_id if node else None
            if node and attempt_id is None and node.task_id:  # the engine has not noticed the attempt yet
                attempt_id = await s.scalar(
                    select(Attempt.id)
                    .where(Attempt.task_id == node.task_id, Attempt.status == AttemptStatus.RUNNING)
                    .order_by(Attempt.id.desc())
                    .limit(1)
                )
        if attempt_id:
            await self._scheduler().cancel(attempt_id)  # type: ignore[attr-defined]
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        return True

    async def run_for_task(
        self, project_id: int, task_id: int, workflow_id: int | None, attempt_id: int, write
    ) -> tuple[bool, str]:
        """Play a task's workflow for one attempt of that task. Progress goes into the attempt's log as it happens.
        Returns whether the run succeeded, and what it concluded."""
        async with self.maker() as s:
            wf = await s.get(Workflow, workflow_id) if workflow_id else None
            if wf is None or wf.project_id != project_id:
                await write(
                    "[Cell error] The workflow this task plays no longer exists. Pick another one in the task.\n"
                )
                return False, ""
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
            return False, ""
        try:
            run_id = await self.start(project_id, wf.id, graph, trigger="task", parent_run_id=parent)
        except LoopError as e:
            await write(f"[Cell error] {e}\n")
            return False, ""
        async with self.maker() as s:
            await s.execute(update(Attempt).where(Attempt.id == attempt_id).values(workflow_run_id=run_id))
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
        return run.status == RunStatus.SUCCEEDED, run.outcome

    # the run

    async def _run(self, ctx: _Ctx, graph: Graph, starts: list[str] | None = None) -> None:
        nodes = {n.id: n for n in graph.nodes}
        outgoing: dict[str, list[GraphEdge]] = {}
        for e in graph.edges:
            if e.sourceHandle != MOUNT:  # a folder handed to an agent is not a step to follow
                outgoing.setdefault(e.source, []).append(e)
        queue: deque[tuple[str, Prev | None]] = deque(
            (n.id, None) for n in graph.start_nodes if starts is None or n.id in starts
        )
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
        run_options = self._run_options(c, ctx.graph.mounts_for(node.id))
        async with self.maker() as s:
            if ctx.trigger_task_id and (started_by := await s.get(Task, ctx.trigger_task_id)):
                instructions += (
                    f'\n\nThis workflow was started by the task "{started_by.title}":\n'
                    f"{started_by.description.strip() or '(no description)'}"
                )
            agent = None
            if agent_id := c.get("agentId", "").strip():
                agent = await s.get(Agent, int(agent_id)) if agent_id.isdigit() else None
                if agent is None or agent.project_id != ctx.project_id:
                    raise NodeError(
                        "The agent of this node no longer exists. Open the node and choose another."
                    )
            task = Task(
                project_id=ctx.project_id, title=title, description=instructions, status=TaskStatus.READY,
                harness=agent.harness if agent else c.get("harness", "codex"),
                agent_id=agent.id if agent else None, run_options=run_options,
                position=await self._next_position(s, ctx.project_id, TaskStatus.READY),
            )  # fmt: skip
            s.add(task)
            await s.flush()
            # linked before the task can be picked up, so a workflow it plays can tell which run is waiting for it
            await s.execute(
                update(WorkflowNodeRun).where(WorkflowNodeRun.id == nr_id).values(task_id=task.id)
            )
            await s.commit()
            task_id = task.id
        return await self._wait_for_task(nr_id, task_id, before=0)

    @staticmethod
    def _run_options(c: dict, attached: list[dict] | None = None) -> dict | None:
        """The cell size and shared folders set on an Agent node, for this run only. Node settings are plain text:
        the cell fields are separate keys, the folders one string like "3:rw,5:ro" (volume id and mode). Folders handed
        over by lines from Folder nodes (`attached`) come first; one named in the node's own list wins for that folder."""
        try:
            fields = {
                "cellImage": "image",
                "cellCpus": "cpus",
                "cellMemory": "memory_mb",
                "cellTimeout": "timeout_seconds",
            }
            asked = {name: c[key].strip() for key, name in fields.items() if c.get(key, "").strip()}
            profile = ProfileOverrides.model_validate(asked).clean() if asked else None
            mounts = [MountRef.model_validate(m).model_dump() for m in attached or []]
            for part in filter(None, (p.strip() for p in c.get("mounts", "").split(","))):
                volume_id, _, mode = part.partition(":")
                mounts.append(MountRef(volume_id=int(volume_id), mode=mode or "rw").model_dump())
        except (ValidationError, ValueError):
            raise NodeError("The cell or folder settings of this agent node are not valid") from None
        return {k: v for k, v in {"profile": profile, "mounts": mounts}.items() if v} or None

    async def _task(self, ctx: _Ctx, nr_id: int, node: GraphNode) -> Outcome:
        c = node.config
        action = c.get("action", "create")
        title = c.get("title", "").strip()
        if action != "move_trigger" and not title:
            raise NodeError("The task title is empty. Open the node and fill it in.")
        if action == "move_trigger" and ctx.trigger_task_id is None:
            raise NodeError(
                "No task started this run, so there is nothing to move. Use a Trigger set to "
                "'A task moves into a status' to start the workflow."
            )
        target = c.get("status", "backlog")
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
                if action == "move_trigger":
                    task = await s.get(Task, ctx.trigger_task_id)
                    if task is None:
                        raise NodeError("The task that started this run was deleted.")
                    title = task.title
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
                    if (
                        task.status != target
                    ):  # lands at the bottom of its new column, like a card dropped there
                        task.position = await self._next_position(s, ctx.project_id, target)
                    task.status = target
                    task.next_run_at = None
                    if c.get("description", "").strip():
                        task.description = c["description"]
                    note = f'Updated task "{title}": now {target}.'
            await s.flush()
            await s.execute(
                update(WorkflowNodeRun).where(WorkflowNodeRun.id == nr_id).values(task_id=task.id)
            )
            await s.commit()
            task_id, becomes_ready = task.id, task.status == TaskStatus.READY
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
            if n.id in done or n.kind == "volume":  # a Folder node is never a step, so it is never "not run"
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
