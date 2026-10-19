"""The shape of a workflow: nodes and the lines between them, with the rules that make a drawing a valid graph.

This is what the editor saves and what a run reads back. It knows nothing about running (see `workflow_walk` for where a
run has got to, and `workflows` for the engine)."""

import re
from typing import Annotated, Literal

from pydantic import BaseModel, Field, model_validator

from .models import Board

Kind = Literal[
    "start", "trigger", "task", "agent", "condition", "approval", "end", "volume", "split", "merge"
]

MAX_BRANCHES = (
    4  # the branch points of a Splitter (its outputs, "o1"...) and of a Merger (its inputs, "i1"...)
)


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


def _covers(where: str, board: Board) -> bool:
    """Is the board in the part of the project a Trigger watches?"""
    kind, _, ident = where.partition(":")
    if kind == "b":
        return ident == str(board.id)
    if kind == "w":
        return ident == str(board.workspace_id)
    return True
