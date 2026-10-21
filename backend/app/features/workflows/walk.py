"""Where a run has got to: what each node produced, and which node runs next.

Pure bookkeeping over a `Graph`, with no database and no waiting. `workflows.WorkflowRunner._run` asks the walk what is
ready, runs it, and tells the walk how it ended."""

import re
from collections import defaultdict, deque
from dataclasses import dataclass, field

from app.features.workflows.graph import MOUNT, START_KINDS, Graph, GraphNode


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
class Lane:
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
class MergeIn:
    """One branch arriving at a Merger."""

    number: int  # which branch point of the Merger it came in at
    name: str  # what the branch is called: the Merger's setting for that point, or the node that sent it
    mark: _Mark


@dataclass
class Gate:
    """An approval gate that was waiting when Themis stopped."""

    node_id: str
    nr_id: int  # its WorkflowNodeRun row, which the resumed gate keeps using
    prev: Prev | None


@dataclass
class Resume:
    """What it takes to pick a run up again at its approval gates after a restart (see WorkflowRunner.resume_parked).
    Only the path below the gates carries on: the walker's other state lived in memory and is gone."""

    gates: list[Gate]
    ran: set[str]  # the nodes that already ran in this run, so nothing runs twice
    seq: int  # the last sequence number of the run's records
    failure: str  # why the run is bound to end as failed, when something in it already failed ("" if not)


def prev_from(data: dict | None) -> Prev | None:
    """A Prev read back from the JSON an approval gate stored it as (`asdict`, with the paths as a list)."""
    return Prev(**{**data, "only": tuple(data.get("only", ()))}) if data else None


def _file_patterns(text: str) -> tuple[str, ...]:
    """A Splitter's file rule ("src, docs/**, *.md") as patterns: a bare folder name means everything in it."""
    out = []
    for part in re.split(r"[,\n]", text):
        part = part.strip().lstrip("./").strip("/")
        if part:
            out.append(part)
    return tuple(out)


class Walk:
    """Where a run has got to: which lines carried a result into each node, which can carry nothing any more, and the
    lanes the nodes run in. It only decides what runs next; `WorkflowRunner._run` runs it.

    A node runs when a line carries a result into it; the first to arrive wins, and later ones are ignored (which is
    also what stops a loop). A Merger is the exception: it waits until every line into it is settled. A line is settled
    when its node finished (carrying a result, or failed), or when it is certain that node will never run: the
    condition went the other way, or every line into that node is itself dead. That is what lets a Merger sit behind
    the two sides of a Condition without waiting for the side that was never taken."""

    def __init__(self, graph: Graph, starts: list[str] | None, resume: Resume | None = None) -> None:
        self.nodes = {n.id: n for n in graph.nodes}
        self.edges = [e for e in graph.edges if e.sourceHandle != MOUNT]  # a folder handed over is not a step
        self.into: dict[str, list[int]] = defaultdict(list)
        self.out: dict[str, list[int]] = defaultdict(list)
        for i, e in enumerate(self.edges):
            self.into[e.target].append(i)
            self.out[e.source].append(i)
        self.lanes: dict[int, Lane] = {0: Lane(0)}
        self._branch_lanes: dict[tuple[str, str], int] = {}
        self.marks: dict[str, dict[int, _Mark]] = defaultdict(dict)
        self.queued: set[str] = set()
        self.dead: set[str] = set()
        if resume:
            self._resume_at(resume)
            return
        begin = [n.id for n in graph.start_nodes if starts is None or n.id in starts]
        for node_id in begin:
            self._queue(node_id, None, self.lanes[0])
        for n in graph.nodes:  # nothing leads here, so nothing can: whatever waits on it must not wait
            if n.kind != "volume" and n.id not in begin and (n.kind in START_KINDS or not self.into[n.id]):
                self.kill(n.id)

    def _resume_at(self, resume: Resume) -> None:
        """Start from the approval gates a run was parked at. The first gate plays in the run's own lane; each further
        one gets a lane beside it, as parallel branches had. Whatever already ran counts as queued, so a loop cannot
        run it again, and every node that is neither a gate nor below one is dead, so that a Merger below the gates
        waits for the gates and not for branches that no longer exist."""
        for i, gate in enumerate(resume.gates):
            if i:
                self.lanes[i] = Lane(i, 0)
            self._queue(gate.node_id, gate.prev, self.lanes[i])
        self.queued |= resume.ran
        below, todo = set(), [g.node_id for g in resume.gates]
        while todo:
            for i in self.out[todo.pop()]:
                if (target := self.edges[i].target) not in below:
                    below.add(target)
                    todo.append(target)
        gates = {g.node_id for g in resume.gates}
        for n in self.nodes.values():
            if n.kind != "volume" and n.id not in gates and (n.id in resume.ran or n.id not in below):
                self._abandon(n.id)

    def _abandon(self, node_id: str) -> None:
        """Nothing more comes of this node: it ran before the gates, or is not below them. Its lines are dead."""
        if node_id in self.dead:
            return
        self.dead.add(node_id)
        for i in self.out[node_id]:
            self.settle(i, _Mark("dead"))

    def _queue(
        self, node_id: str, prev: Prev | None, lane: Lane, inputs: list[MergeIn] | None = None
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
            self.kill(node_id)
            return
        inputs = []
        for i in self.into[node_id]:
            if i not in marks or marks[i].state == "dead":
                continue
            number = int(self.edges[i].targetHandle[1:])  # "i2" -> 2 (the graph is validated)
            config = self.nodes[node_id].config
            named = config.get(f"name{number}", "").strip()
            inputs.append(MergeIn(number, named or marks[i].source or f"Branch {number}", marks[i]))
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
        lane: Lane,
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
                    branch = Lane(len(self.lanes), lane.id)
                    self.lanes[branch.id] = branch
                    self._branch_lanes[key] = branch.id
                only = _file_patterns(node.config.get(f"files{handle[1:]}", ""))
                shared = Prev(label, outcome.status, outcome.result, here, here is not None, only)
                self.settle(i, _Mark("delivered", shared, self._branch_lanes[key], source=label))
            else:
                self.settle(i, _Mark("delivered", out, lane.id, source=label))
