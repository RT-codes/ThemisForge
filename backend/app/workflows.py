"""Workflows: a graph of nodes drawn in the editor, and the engine that runs it.

A run starts from every Start (or Trigger) node and follows the edges. Nodes run one at a time, in order, until a
Splitter sends the run down several branches: those run side by side (each branch is a lane, see `_Lane`), and a Merger
waits for all its branches before it carries on:

- Start / Trigger: begin the run. A Trigger set to "a task moves into a status" starts a run by itself, whenever a task
  of the project moves into that status (see `WorkflowRunner._fire`). The run remembers that task.
- Task: create, update or run a task of the project, or move the task that started the run. A task that becomes READY runs through the normal scheduler,
  and the node waits for it and takes over its log and result.
- Agent: a task handed to a Codex agent, with the node's instructions (and the previous result) as its description.
- Condition: checks the previous node's result or status and follows the `yes` or the `no` edges.
- Splitter: sends the run down its branches, each with its own copy of the working folder. A branch can have a rule
  (the result must contain some text; only some files go along).
- Merger: waits until every branch has finished or can no longer arrive, then merges their results into one text and
  their working folders into one, each branch in a folder named after it.
- End: records how the run ended.

A node that fails stops its branch (an Agent node can be told to carry on). Every node that did run gets a record
with its output and error; nodes that did not run get a record saying why.
"""

import asyncio
import logging
import os
import re
import shutil
import time
from collections import defaultdict, deque
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Annotated, Literal, get_args

from pydantic import BaseModel, Field, ValidationError, model_validator
from sqlalchemy import event, func, inspect, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import Session, selectinload

from . import automation, boards, halt
from .app_settings import load_settings
from .cells import workdir_path
from .harness import Effort, clean_model_name, log_tail
from .models import (
    Agent,
    Attempt,
    AttemptStatus,
    Board,
    NodeStatus,
    Project,
    RunStatus,
    Task,
    TaskStage,
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

Kind = Literal["start", "trigger", "task", "agent", "condition", "end", "volume", "split", "merge"]

MAX_BRANCHES = (
    4  # the branch points of a Splitter (its outputs, "o1"...) and of a Merger (its inputs, "i1"...)
)
QUEUE_PATIENCE_SECONDS = 6 * 3600  # how long a node waits for a task that no cell has picked up yet


def branch_count(config: dict[str, str]) -> int:
    """How many branches a Splitter sends out or a Merger waits for: its "branches" setting, 2 to MAX_BRANCHES."""
    raw = config.get("branches", "2")
    return min(MAX_BRANCHES, max(2, int(raw))) if raw.isdigit() else 2


def branch_name(config: dict[str, str], number: int) -> str:
    return config.get(f"name{number}", "").strip() or f"Branch {number}"


# A "mount" line joins a Folder (volume) node to an Agent node: it hands that folder to the agent. It is not a step, so
# the run never follows it.
MOUNT = "mount"
START_KINDS = ("start", "trigger")


# a node's settings: plain text values, whatever the kind (the editor's fields are defined in the frontend)
NodeConfig = dict[str, Annotated[str, Field(max_length=20_000)]]


class Position(BaseModel):
    x: float = 0
    y: float = 0


class GraphNode(BaseModel):
    id: str = Field(min_length=1, max_length=64, pattern=r"^[\w-]+$")
    kind: Kind
    label: str = Field(default="", max_length=100)
    config: NodeConfig = Field(default_factory=dict)
    position: Position = Field(default_factory=Position)


class GraphEdge(BaseModel):
    id: str = Field(min_length=1, max_length=100)
    source: str
    target: str
    sourceHandle: str | None = Field(
        default=None, max_length=20
    )  # "yes" / "no" on a condition, "mount" on a folder
    targetHandle: str | None = Field(default=None, max_length=20)  # "mount" where a folder joins an agent
    # how the editor draws the line; only the canvas cares, a run ignores it. None is the editor's default (organic)
    curve: Literal["organic", "angular"] | None = None


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
            if source.kind == "split" and not re.fullmatch(rf"o[1-{MAX_BRANCHES}]", e.sourceHandle or ""):
                raise ValueError("A line out of a Splitter must leave from one of its branch points")
            if target.kind == "merge" and not re.fullmatch(rf"i[1-{MAX_BRANCHES}]", e.targetHandle or ""):
                raise ValueError("A line into a Merger must arrive at one of its branch points")
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

    def status_triggers(self, status: str | None = None, board: Board | None = None) -> list[GraphNode]:
        """The Trigger nodes that start a run when a task moves into a status (into `status`, or any when None). With
        a `board`, only those whose "where" covers it: anywhere (empty), one workspace ("w:<id>") or one board ("b:<id>")."""
        return [
            n
            for n in self.nodes
            if n.kind == "trigger"
            and n.config.get("type") == "task_status"
            and (status is None or n.config.get("status") == status)
            and (board is None or _covers(n.config.get("where", ""), board))
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
    # The working folder (an attempt id, see Attempt.workdir_id) the run is in after that node. Steps that do not work
    # in a folder (a condition, an end) hand on the one they were given, so a later step can still continue in it.
    workdir_id: int | None = None
    # The folder is shared with the sibling branches of a Splitter: a step that continues in it works on a copy of its
    # own instead (see `_continue_in`), so parallel branches never write into the same files.
    fork: bool = False
    # The paths of that copy (a branch's file rule); empty means everything.
    only: tuple[str, ...] = ()


@dataclass
class Outcome:
    status: str  # NodeStatus.SUCCEEDED or FAILED
    result: str = ""
    log: str = ""
    error: str = ""
    branch: str | None = None  # a Condition's answer, "yes" or "no"
    workdir_id: int | None = None  # the working folder the node's cell used, when it ran one
    taken: frozenset[str] | None = None  # a Splitter's branch points that send something on ("o1"...)


@dataclass
class _Lane:
    """A row of nodes that run one after another. The run starts in one lane; every branch a Splitter sends out is a lane
    of its own, and lanes run at the same time. Nothing else runs in parallel, so a workflow with no Splitter runs
    exactly one node at a time, in the order its lines lead."""

    id: int
    parent: int | None = None
    queue: deque = field(default_factory=deque)  # of (node id, Prev | None, merge inputs | None)
    busy: bool = False


@dataclass
class _Mark:
    """What reached one line into a node: a result, or the news that nothing will come."""

    state: str  # "delivered", "dead" (not taken, or its node can no longer run) or "failed"
    prev: Prev | None = None
    lane: int = 0
    error: str = ""
    source: str = ""  # the label of the node the line comes from


@dataclass
class _MergeIn:
    """One branch arriving at a Merger."""

    number: int  # which branch point of the Merger it came in at
    name: str  # what the branch is called: the Merger's setting for that point, or the node that sent it
    mark: _Mark


def _slug(text: str, fallback: str) -> str:
    """A name that is safe and easy to read as a folder name: "Research A" becomes "research-a"."""
    slug = re.sub(r"[^a-z0-9._-]+", "-", text.casefold()).strip("-._")
    return slug[:40] or fallback


def _file_patterns(text: str) -> tuple[str, ...]:
    """A Splitter's file rule ("src, docs/**, *.md") as patterns: a bare folder name means everything in it."""
    out = []
    for part in re.split(r"[,\n]", text):
        part = part.strip().lstrip("./").strip("/")
        if part:
            out.append(part)
    return tuple(out)


def _copy_folder(source: Path, target: Path, only: tuple[str, ...] = ()) -> None:
    """Copy a working folder (or the paths of it that match `only`) to a new place. Blocking: call it from a thread.
    `.agents` is left out: it is only the mountpoint of the agent's skills."""
    target.mkdir(parents=True, exist_ok=True)
    patterns = [p + "/**" if not any(c in p for c in "*?[") and (source / p).is_dir() else p for p in only]
    for base, dirs, files in os.walk(source):
        rel_base = Path(base).relative_to(source)
        dirs[:] = [d for d in dirs if not (rel_base == Path(".") and d == ".agents")]
        if not patterns:
            (target / rel_base).mkdir(parents=True, exist_ok=True)
        for name in files:
            rel = (rel_base / name).as_posix()
            if patterns and not any(PurePosixPath(rel).full_match(p) for p in patterns):
                continue
            dest = target / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            if (source / rel).is_symlink():
                os.symlink(os.readlink(source / rel), dest)
            else:
                shutil.copy2(source / rel, dest)


class _Walk:
    """Where a run has got to: which lines carried a result into each node, which can carry nothing any more, and the
    lanes the nodes run in. It only decides what runs next; `WorkflowRunner._run` runs it.

    A node runs when a line carries a result into it; the first to arrive wins, and later ones are ignored (which is
    also what stops a loop). A Merger is the exception: it waits until every line into it is settled. A line is settled
    when its node finished (carrying a result, or failed), or when it is certain that node will never run: the
    condition went the other way, or every line into that node is itself dead. That is what lets a Merger sit behind
    the two sides of a Condition without waiting for the side that was never taken."""

    def __init__(self, graph: Graph, starts: list[str] | None) -> None:
        self.nodes = {n.id: n for n in graph.nodes}
        self.edges = [e for e in graph.edges if e.sourceHandle != MOUNT]  # a folder handed over is not a step
        self.into: dict[str, list[int]] = defaultdict(list)
        self.out: dict[str, list[int]] = defaultdict(list)
        for i, e in enumerate(self.edges):
            self.into[e.target].append(i)
            self.out[e.source].append(i)
        self.lanes: dict[int, _Lane] = {0: _Lane(0)}
        self._branch_lanes: dict[tuple[str, str], int] = {}
        self.marks: dict[str, dict[int, _Mark]] = defaultdict(dict)
        self.queued: set[str] = set()
        self.dead: set[str] = set()
        begin = [n.id for n in graph.start_nodes if starts is None or n.id in starts]
        for node_id in begin:
            self._queue(node_id, None, self.lanes[0])
        for n in graph.nodes:  # nothing leads here, so nothing can: whatever waits on it must not wait
            if n.kind != "volume" and n.id not in begin and (n.kind in START_KINDS or not self.into[n.id]):
                self.kill(n.id)

    def _queue(
        self, node_id: str, prev: Prev | None, lane: _Lane, inputs: list[_MergeIn] | None = None
    ) -> None:
        if node_id not in self.queued:
            self.queued.add(node_id)
            lane.queue.append((node_id, prev, inputs))

    def kill(self, node_id: str) -> None:
        """This node will never run: the lines out of it are dead."""
        if node_id in self.dead or node_id in self.queued:
            return
        self.dead.add(node_id)
        for i in self.out[node_id]:
            self.settle(i, _Mark("dead"))

    def settle(self, index: int, mark: _Mark) -> None:
        target = self.edges[index].target
        if target in self.queued or target in self.dead:
            return
        marks = self.marks[target]
        marks[index] = mark
        if self.nodes[target].kind == "merge":
            if len(marks) == len(self.into[target]):
                self._merge_ready(target, marks)
        elif mark.state == "delivered":
            self._queue(target, mark.prev, self.lanes[mark.lane])
        elif len(marks) == len(self.into[target]):
            self.kill(target)  # every line in is settled and none of them carried anything

    def _merge_ready(self, node_id: str, marks: dict[int, _Mark]) -> None:
        arrived = [m for m in marks.values() if m.state != "dead"]
        if not arrived:
            return self.kill(node_id)
        inputs = []
        for i in self.into[node_id]:
            if i not in marks or marks[i].state == "dead":
                continue
            number = int(self.edges[i].targetHandle[1:])  # "i2" -> 2 (the graph is validated)
            config = self.nodes[node_id].config
            named = config.get(f"name{number}", "").strip()
            inputs.append(_MergeIn(number, named or marks[i].source or f"Branch {number}", marks[i]))
        # it carries on where the branches came from: the lane the last of them ran in, one level up
        last = next((m for m in reversed(list(marks.values())) if m.state == "delivered"), arrived[-1])
        lane = self.lanes.get(last.lane, self.lanes[0])
        if lane.parent is not None:
            lane = self.lanes[lane.parent]
        self._queue(node_id, None, lane, sorted(inputs, key=lambda m: m.number))

    def finish(
        self,
        node: GraphNode,
        outcome: Outcome,
        prev: Prev | None,
        lane: _Lane,
        failed: bool,
        start: int | None,
    ) -> None:
        """A node ended: hand its result along every line out of it that is taken, and settle the rest."""
        label = node.label or node.kind
        here = outcome.workdir_id or (prev.workdir_id if prev else start)
        # a folder handed on as it was keeps what it carried (shared with sibling branches, cut down to some paths)
        carried = outcome.workdir_id is None and prev is not None and prev.workdir_id == here
        out = Prev(
            label, outcome.status, outcome.result, here, carried and prev.fork, prev.only if carried else ()
        )
        for i in self.out[node.id]:
            line = self.edges[i]
            if failed:
                self.settle(i, _Mark("failed", error=outcome.error, source=label))
            elif node.kind == "condition" and (line.sourceHandle or "yes") != outcome.branch:
                self.settle(i, _Mark("dead"))
            elif node.kind == "split":
                handle = line.sourceHandle or ""
                if handle not in (outcome.taken or ()):
                    self.settle(i, _Mark("dead"))
                    continue
                key = (node.id, handle)
                if (
                    key not in self._branch_lanes
                ):  # each branch point is a lane of its own, running beside the others
                    branch = _Lane(len(self.lanes), lane.id)
                    self.lanes[branch.id] = branch
                    self._branch_lanes[key] = branch.id
                only = _file_patterns(node.config.get(f"files{handle[1:]}", ""))
                shared = Prev(label, outcome.status, outcome.result, here, here is not None, only)
                self.settle(i, _Mark("delivered", shared, self._branch_lanes[key], source=label))
            else:
                self.settle(i, _Mark("delivered", out, lane.id, source=label))


def _covers(where: str, board: Board) -> bool:
    """Is the board in the part of the project a Trigger watches?"""
    kind, _, ident = where.partition(":")
    if kind == "b":
        return ident == str(board.id)
    if kind == "w":
        return ident == str(board.workspace_id)
    return True


async def task_workdir(s: AsyncSession, task: Task) -> int | None:
    """The working folder a task worked in last (its latest attempt's), or the one it was made to continue in. A
    workflow started by the task begins there, so steps that ask to continue pick up its files."""
    latest = await s.scalar(
        select(Attempt.workdir_id)
        .where(Attempt.task_id == task.id, Attempt.workdir_id.is_not(None))
        .order_by(Attempt.id.desc())
        .limit(1)
    )
    return latest or (task.run_options or {}).get("workdir") or None


@dataclass
class _Ctx:
    run_id: int
    project_id: int
    graph: Graph
    trigger_task_id: int | None = None  # the task whose move into a status started this run
    # the task this run is a stage of: it is the brief for the run (what to focus on), see `_brief`
    stage_task_id: int | None = None
    # the working folder the run starts in (from the stage before it, or the task that started it): the first step
    # that asks to continue works there. Every step otherwise gets a fresh folder.
    workdir_id: int | None = None


class _Step:
    """What a Task step needs to know before it moves or makes a task: who it acts as, the board it was told to use,
    and how many times in a row automation has already handled the task that started this run (the loop guard)."""

    def __init__(
        self,
        s: AsyncSession,
        ctx: _Ctx,
        node: GraphNode,
        actor: str,
        trigger: Task | None,
        chosen_board: Board | None,
        limit: int,
    ) -> None:
        self.s, self.ctx, self.node, self.actor, self.trigger, self.chosen_board = (
            s, ctx, node, actor, trigger, chosen_board,
        )  # fmt: skip
        self.cause = f"run:{ctx.run_id}:{node.id}"
        self.hops = (
            trigger.hops if trigger else 0
        ) + 1  # this step would be one more handling of the same chain
        self.limit = limit

    @classmethod
    async def open(cls, s: AsyncSession, ctx: _Ctx, node: GraphNode) -> "_Step":
        run = await s.get(WorkflowRun, ctx.run_id)
        workflow = await s.get(Workflow, run.workflow_id) if run else None
        trigger = await s.get(Task, ctx.trigger_task_id) if ctx.trigger_task_id else None
        project = await s.get(Project, ctx.project_id)
        chosen: Board | None = None
        if wanted := node.config.get("boardId", "").strip():
            chosen = await s.get(Board, int(wanted)) if wanted.isdigit() else None
            if chosen is None or chosen.project_id != ctx.project_id:
                raise NodeError("The board of this step no longer exists. Open the step and choose another.")
        actor = f"Workflow {workflow.name}" if workflow else "A workflow"
        limit = automation.hop_limit(await load_settings(s), project, trigger)
        return cls(s, ctx, node, actor, trigger, chosen, limit)

    async def guard_hops(self) -> None:
        """Stop, with the reason in the run and in the project's history, when this would be one handling too many."""
        if self.hops <= self.limit:
            return
        reason = (
            f"Stopped to keep automation from looping: this task has been moved or made by workflows "
            f"{self.hops - 1} times in a row (the limit is {self.limit}). Move it by hand to carry on, or raise the "
            f"limit for the project or the task."
        )
        board = await self.s.get(Board, self.trigger.board_id) if self.trigger else None
        boards.record(
            self.s, "automation_stopped", self.ctx.project_id, self.trigger.title if self.trigger else self.actor,
            self.actor, workspace_id=board.workspace_id if board else None, board_id=board.id if board else None,
            task_id=self.trigger.id if self.trigger else None, cause=self.cause,
            data={"reason": reason, "limit": self.limit, "step": self.node.label or self.node.kind},
        )  # fmt: skip
        await self.s.commit()
        raise NodeError(reason)


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


def _changed(obj: Task, attribute: str) -> bool:
    """Did this flush give the attribute a new value (or its first one, for a new row)?"""
    history = inspect(obj).attrs[attribute].history
    return bool(history.added) and history.added != history.deleted


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
        task = asyncio.create_task(
            self._run(
                _Ctx(run_id, project_id, graph, trigger_task_id, stage_task_id, workdir_id), graph, starts
            ),
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

    # the run

    async def _run(self, ctx: _Ctx, graph: Graph, starts: list[str] | None = None) -> None:
        walk = _Walk(graph, starts)
        done: dict[str, Outcome] = {}
        carried_on: set[str] = set()  # failed nodes the workflow continued after
        running: dict[asyncio.Task, tuple[GraphNode, Prev | None, _Lane, int]] = {}
        seq = 0
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
                        seq += 1
                        node = walk.nodes[node_id]
                        task = asyncio.create_task(self._execute_node(ctx, node, seq, prev, inputs))
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
            await self._record_unreached(ctx, graph, done, carried_on, seq, stopped=hard_fail)
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
        self, ctx: _Ctx, node: GraphNode, seq: int, prev: Prev | None, inputs: list[_MergeIn] | None = None
    ) -> Outcome:
        label = node.label or node.kind.capitalize()
        async with self.maker() as s:
            row = WorkflowNodeRun(
                run_id=ctx.run_id, node_id=node.id, kind=node.kind, label=label, seq=seq, started_at=utcnow()
            )
            s.add(row)
            await s.commit()
            nr_id = row.id
        cancelled = False
        try:
            outcome = await self._dispatch(ctx, nr_id, node, prev, inputs)
        except NodeError as e:
            outcome = Outcome(NodeStatus.FAILED, error=str(e))
        except asyncio.CancelledError:
            cancelled = True  # recorded below, outside this block (see there)
        except Exception as e:
            log.exception("workflow node %s crashed", node.id)
            outcome = Outcome(NodeStatus.FAILED, error=f"Unexpected error: {e}")
        if cancelled:
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

    async def _dispatch(
        self, ctx: _Ctx, nr_id: int, node: GraphNode, prev: Prev | None, inputs: list[_MergeIn] | None = None
    ) -> Outcome:
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
        if node.kind == "split":
            return self._split(node, prev)
        if node.kind == "merge":
            return await self._merge(ctx, node, inputs or [])
        if node.kind == "agent":
            return await self._agent(ctx, nr_id, node, prev)
        return await self._task(ctx, nr_id, node, prev)

    # splitter, merger and the folders they hand on

    @staticmethod
    def _split(node: GraphNode, prev: Prev | None) -> Outcome:
        """Sends the run down its branches. Every branch gets the result of the step before; a branch whose rule is
        not met (the result must contain some text) is not sent anything, so a Splitter can also pick between ways."""
        c = node.config
        result = prev.result if prev else ""
        taken: set[str] = set()
        lines = []
        for number in range(1, branch_count(c) + 1):
            name, need, files = (
                branch_name(c, number),
                c.get(f"contains{number}", "").strip(),
                c.get(f"files{number}", "").strip(),
            )
            if not need or need.casefold() in result.casefold():
                taken.add(f"o{number}")
                lines.append(f"{name}: sent" + (f", only {files}" if files else ""))
            else:
                lines.append(f"{name}: not sent, the result does not contain {need!r}")
        if not taken:
            lines.append("No branch was sent anything.")
        return Outcome(
            NodeStatus.SUCCEEDED, result=result, log="\n".join(lines) + "\n", taken=frozenset(taken)
        )

    async def _merge(self, ctx: _Ctx, node: GraphNode, inputs: list[_MergeIn]) -> Outcome:
        """Waits for its branches (the run only gets here once every one is settled) and carries on with all of them:
        their results in one text, and their working folders side by side, each in a folder named after its branch."""
        c = node.config
        good = [i for i in inputs if i.mark.state == "delivered"]
        bad = [i for i in inputs if i.mark.state == "failed"]
        if bad and (c.get("onFailure") != "continue" or not good):
            names = ", ".join(f"'{i.mark.source}'" for i in bad)
            raise NodeError(
                f"{'Branch' if len(bad) == 1 else 'Branches'} {names} failed, so there is nothing to merge. "
                f"{bad[0].mark.error}".strip()
            )
        taken: set[str] = set()
        sections, folders, lines = [], [], []
        for i in good:
            prev = i.mark.prev
            folder = ""
            if prev and prev.workdir_id:
                base = _slug(i.name, f"branch-{i.number}")
                folder, n = base, 2
                while folder in taken:
                    folder, n = f"{base}-{n}", n + 1
                taken.add(folder)
                folders.append((i, folder))
            text = (prev.result if prev else "").strip()
            heading = f"## {i.name}" + (f" (files in {folder}/)" if folder else "")
            sections.append(f"{heading}\n{text}".rstrip() if text else heading)
            how = "failed, carried on" if prev and prev.status == NodeStatus.FAILED else "arrived"
            lines.append(f"{i.name}: {how}" + (f", files in {folder}/" if folder else ""))
        for i in bad:
            lines.append(f"{i.name}: failed ({i.mark.error}), left out")
        workdir_id = None
        if folders:
            summary = "Combined the work of " + ", ".join(f"{i.name} (in {f}/)" for i, f in folders) + "."
            workdir_id = await self._folder_record(
                ctx, f"{node.label or 'Merger'}: combined folder", summary, [f"{f}/" for _, f in folders]
            )
            target = workdir_path(ctx.project_id, workdir_id)
            try:
                for i, f in folders:
                    source = workdir_path(ctx.project_id, i.mark.prev.workdir_id)
                    if await asyncio.to_thread(source.is_dir):
                        await asyncio.to_thread(_copy_folder, source, target / f, i.mark.prev.only)
            except OSError as e:
                raise NodeError(f"Could not combine the working folders: {e}") from None
        return Outcome(
            NodeStatus.SUCCEEDED,
            result="\n\n".join(sections),
            log="\n".join(lines) + "\n",
            workdir_id=workdir_id,
        )

    async def _folder_record(self, ctx: _Ctx, title: str, result: str, added: list[str] | None = None) -> int:
        """A working folder made by the workflow itself (a branch's copy, a merged folder) has to be named by an
        attempt, like every other one: that is how the scheduler finds it, tells the next agent what is in it, and
        removes it after the retention period. This makes the finished, hidden step that owns it."""
        now = utcnow()
        async with self.maker() as s:
            board = await boards.default_board(s, ctx.project_id)
            task = Task(
                project_id=ctx.project_id, board_id=board.id, title=title[:200], status=TaskStatus.DONE,
                internal=True, position=await boards.next_position(s, board.id, TaskStatus.DONE),
            )  # fmt: skip
            s.add(task)
            await s.flush()
            attempt = Attempt(
                task_id=task.id, status=AttemptStatus.SUCCEEDED, started_at=now, finished_at=now, exit_code=0,
                result=result, changes={"added": added or [], "changed": [], "removed": [], "more": 0},
            )  # fmt: skip
            s.add(attempt)
            await s.flush()
            attempt.workdir_id = attempt.id
            await s.commit()
            return attempt.id

    async def _continue_in(self, ctx: _Ctx, node: GraphNode, prev: Prev | None) -> int | None:
        """The working folder a step that asked to continue starts in: the one the step before left, or the run's own.
        When that folder is shared with the sibling branches of a Splitter, the step gets a copy of its own (or just
        the paths its branch was given), so parallel branches never write into the same files."""
        source = prev.workdir_id if prev else ctx.workdir_id
        if not source or prev is None or not prev.fork:
            return source
        folder = workdir_path(ctx.project_id, source)
        if not await asyncio.to_thread(folder.is_dir):
            return source  # gone: the scheduler tells the agent so, as for any folder that was removed
        name = node.label or node.kind.capitalize()
        note = f"A copy of the working folder as it was after '{prev.label}', made for the branch that leads to '{name}'."
        if prev.only:
            note += f" Only {', '.join(prev.only)} was copied."
        copy = await self._folder_record(ctx, f"{name}: copy of the folder", note)
        try:
            await asyncio.to_thread(_copy_folder, folder, workdir_path(ctx.project_id, copy), prev.only)
        except OSError as e:
            raise NodeError(f"Could not copy the working folder for this branch: {e}") from None
        return copy

    # task and agent nodes

    async def _agent(self, ctx: _Ctx, nr_id: int, node: GraphNode, prev: Prev | None) -> Outcome:
        c = node.config
        instructions = c.get("instructions", "").strip()
        if not instructions:
            raise NodeError("This agent has no instructions. Open the node and tell it what to do.")
        # a step opts out of the brief when the task's focus is not its business: a step that only does housekeeping
        # (syncing a clone, publishing) would otherwise take the focus as its own job and go and do the whole task
        brief = ""
        if c.get("brief") != "off":
            async with self.maker() as s:
                brief = await self._brief(s, ctx)
        # the order is the method (the node), the focus (the task), then what the step before it produced
        if brief:
            instructions += f"\n\n{brief}"
        if prev and prev.result.strip():
            instructions += f"\n\nResult of the previous step ({prev.label}):\n{prev.result.strip()}"
        title = node.label or "Agent"
        # "Continue" works in the folder the step before left (or the one the run started in); with none yet, or by
        # default, the agent gets a fresh folder like any other run
        workdir = await self._continue_in(ctx, node, prev) if c.get("workdir") == "inherit" else None
        run_options = self._run_options(c, ctx.graph.mounts_for(node.id), workdir)
        async with self.maker() as s:
            agent = None
            if agent_id := c.get("agentId", "").strip():
                agent = await s.get(Agent, int(agent_id)) if agent_id.isdigit() else None
                if agent is None or agent.project_id != ctx.project_id:
                    raise NodeError(
                        "The agent of this node no longer exists. Open the node and choose another."
                    )
            board = await boards.default_board(
                s, ctx.project_id
            )  # a task needs a board, but this one is internal: it only shows when asked for
            task = Task(
                project_id=ctx.project_id, board_id=board.id, title=title, description=instructions,
                status=TaskStatus.READY, harness=agent.harness if agent else c.get("harness", "codex"),
                agent_id=agent.id if agent else None, run_options=run_options, internal=True,
                position=await boards.next_position(s, board.id, TaskStatus.READY),
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
    async def _brief(s: AsyncSession, ctx: _Ctx) -> str:
        """What a step is told about the task behind its run. This is the steering wheel: a workflow says how to do
        the work, and the task's own description says what this run should focus on, so the same workflow can be
        pointed somewhere else by editing the ticket. A task that moved into a status started the run, or the run is
        a stage of the task; a test run has no task."""
        if ctx.trigger_task_id and (task := await s.get(Task, ctx.trigger_task_id)):
            return (
                f'This workflow was started by the task "{task.title}":\n'
                f"{task.description.strip() or '(no description)'}"
            )
        if ctx.stage_task_id and (task := await s.get(Task, ctx.stage_task_id)):
            if text := task.description.strip():
                return f'This is a stage of the task "{task.title}". What the task asks for:\n{text}'
            return f'This is a stage of the task "{task.title}".'
        return ""

    @staticmethod
    def _run_options(c: dict, attached: list[dict] | None = None, workdir: int | None = None) -> dict | None:
        """The model, cell size and shared folders set on an Agent node, for this run only. Node settings are plain
        text: the model and effort are `model` and `reasoningEffort` (empty: the agent's own, or Settings), the cell
        fields are separate keys, the folders one string like "3:rw,5:ro" (volume id and mode). Folders handed
        over by lines from Folder nodes (`attached`) come first; one named in the node's own list wins for that folder.
        `workdir` is the earlier attempt whose working folder this step continues in (see Attempt.workdir_id)."""
        try:
            fields = {
                "cellImage": "image",
                "cellCpus": "cpus",
                "cellMemory": "memory_mb",
                "cellTimeout": "timeout_seconds",
            }
            asked = {name: c[key].strip() for key, name in fields.items() if c.get(key, "").strip()}
            profile = ProfileOverrides.model_validate(asked).clean() if asked else None
            model = clean_model_name(c.get("model", ""))
            effort = c.get("reasoningEffort", "").strip()
            if effort and effort not in get_args(Effort):
                raise ValueError(effort)
            mounts = [MountRef.model_validate(m).model_dump() for m in attached or []]
            for part in filter(None, (p.strip() for p in c.get("mounts", "").split(","))):
                volume_id, _, mode = part.partition(":")
                mounts.append(MountRef(volume_id=int(volume_id), mode=mode or "rw").model_dump())
        except (ValidationError, ValueError):
            raise NodeError("The model, cell or folder settings of this agent node are not valid") from None
        extras = {"profile": profile, "mounts": mounts, "workdir": workdir, "model": model, "effort": effort}
        return {k: v for k, v in extras.items() if v} or None

    async def _task(self, ctx: _Ctx, nr_id: int, node: GraphNode, prev: Prev | None = None) -> Outcome:
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
        link = action == "create" and c.get("link") == "1"
        if link and ctx.trigger_task_id is None:
            raise NodeError(
                "No task started this run, so there is nothing to follow up. Use a Trigger set to "
                "'A task moves into a status', or turn off 'Follow up the task that started this run'."
            )
        target = c.get("status", "backlog")
        if target == TaskStatus.RUNNING or (
            target not in {s.value for s in TaskStatus} and boards.custom_id(target) is None
        ):
            raise NodeError(f"'{target}' is not a status a workflow can move a task to")
        async with self.maker() as s:
            step = await _Step.open(s, ctx, node)
            before = 0
            if action == "create":
                workdir = await self._continue_in(ctx, node, prev) if c.get("workdir") == "inherit" else None
                task = await self._create(s, step, c, title, target, link, workdir)
                note = (
                    f'Created task "{title}" on {(await s.get_one(Board, task.board_id)).name} in {target}.'
                )
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
                    note = await self._relocate(s, step, task, c, target)
            await s.flush()
            await s.execute(
                update(WorkflowNodeRun).where(WorkflowNodeRun.id == nr_id).values(task_id=task.id)
            )
            await s.commit()
            task_id, becomes_ready = task.id, task.status == TaskStatus.READY
        if becomes_ready:
            return await self._wait_for_task(nr_id, task_id, before)
        return Outcome(NodeStatus.SUCCEEDED, log=note + "\n", result=note)

    async def _create(
        self,
        s: AsyncSession,
        step: "_Step",
        c: dict[str, str],
        title: str,
        target: str,
        link: bool,
        workdir: int | None = None,
    ) -> Task:
        """Make the task of a Create step: on the chosen board, linked to the task that started the run when asked.
        A step makes its task once, whatever happens: running it again finds the one it made. `workdir` is the working
        folder the task continues in; the task (or its first stage) starts there instead of in a fresh one."""
        key = f"run:{step.ctx.run_id}:{step.node.id}"
        if made := await s.scalar(select(Task).where(Task.origin_key == key)):
            return made
        await step.guard_hops()
        try:
            board = step.chosen_board or await boards.board_for_status(s, step.ctx.project_id, target)
            if link:
                assert step.trigger is not None
                task = await boards.spawn_task(
                    s, step.trigger, board, step.actor, title, c.get("description", ""), target,
                    step.cause, key, step.hops,
                )  # fmt: skip
                if workdir:
                    task.run_options = {**(task.run_options or {}), "workdir": workdir}
                return task
            boards.check_status(board, target)
            task = Task(
                project_id=step.ctx.project_id, board_id=board.id, title=title,
                description=c.get("description", ""), status=target, origin_key=key, hops=step.hops,
                run_options={"workdir": workdir} if workdir else None,
                position=await boards.next_position(s, board.id, target),
            )  # fmt: skip
        except boards.BoardError as e:
            raise NodeError(str(e)) from None
        s.add(task)
        await s.flush()
        boards.record_new_task(s, task, board, step.actor, step.cause)
        return task

    async def _relocate(
        self, s: AsyncSession, step: "_Step", task: Task, c: dict[str, str], target: str
    ) -> str:
        """Move a task to a status, and to another board when the step names one."""
        await step.guard_hops()
        board = step.chosen_board or await s.get_one(Board, task.board_id)
        try:
            if (board.id, target) != (task.board_id, task.status):  # lands at the bottom of its new column
                await boards.move_task(s, task, board, step.actor, target, None, step.cause)
        except boards.BoardError as e:
            raise NodeError(str(e)) from None
        task.next_run_at = None
        task.hops = step.hops
        if c.get("description", "").strip():
            task.description = c["description"]
        return f'Updated task "{task.title}": now {target} on {board.name}.'

    async def _wait_for_task(self, nr_id: int, task_id: int, before: int) -> Outcome:
        """Let the scheduler run the task, mirror its log into the node, and report how the attempt ended."""
        self._scheduler().wake()  # type: ignore[attr-defined]
        async with self.maker() as s:
            cfg = await load_settings(s)
        # Two clocks. A task that no cell has picked up is queued behind the others (several branches may want cells at
        # once, and the resource budget lets them in turn), so it is waited for patiently. The time limit only starts
        # once its attempt does, so a branch is never failed for waiting its turn.
        queued_at = time.monotonic()
        started_at: float | None = None
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
                started_at = started_at or time.monotonic()
                if (attempt.id, attempt.log) != shown:
                    shown = (attempt.id, attempt.log)
                    await self._update_node(
                        nr_id, attempt_id=attempt.id, log=attempt.log, result=attempt.result
                    )
                if attempt.status != AttemptStatus.RUNNING:
                    here = attempt.workdir_id
                    if attempt.status == AttemptStatus.SUCCEEDED:
                        return Outcome(
                            NodeStatus.SUCCEEDED, result=attempt.result, log=attempt.log, workdir_id=here
                        )
                    # the attempt knows why it failed (see Attempt.failure); the exit code is the fallback
                    why = (
                        "The task was cancelled."
                        if attempt.status == AttemptStatus.CANCELLED
                        else (attempt.failure or {}).get("reason") or _failed_message(attempt.exit_code)
                    )
                    return Outcome(
                        NodeStatus.FAILED, result=attempt.result, log=attempt.log, error=why, workdir_id=here
                    )
            elif task is None:
                raise NodeError("The task was deleted while the workflow was waiting for it.")
            elif task.status not in (TaskStatus.READY, TaskStatus.RUNNING):
                raise NodeError(f"The task was moved to {task.status} before it could run.")
            now = time.monotonic()
            if started_at is None and now - queued_at > QUEUE_PATIENCE_SECONDS:
                raise NodeError("Timed out waiting for a free cell to start the task.")
            if started_at is not None and now - started_at > cfg.cell_timeout_seconds + 600:
                raise NodeError("Timed out waiting for the task to run.")

    # records

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
                .where(WorkflowNodeRun.run_id == run_id, WorkflowNodeRun.status == NodeStatus.RUNNING)
                .values(status=NodeStatus.CANCELLED, finished_at=utcnow(), error="The run was cancelled")
            )
            await s.execute(
                update(WorkflowRun)
                .where(WorkflowRun.id == run_id)
                .values(status=RunStatus.CANCELLED, finished_at=utcnow(), outcome="Cancelled")
            )
            await s.commit()
