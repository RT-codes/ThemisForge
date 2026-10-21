import asyncio
import contextlib
from dataclasses import dataclass

from app.execution.budget import Cost, admit
from app.execution.cells.contract import CellSpec
from app.execution.planning import RunPlan as _Plan


@dataclass
class _Live:
    task: asyncio.Task
    spec: CellSpec | None = None
    cancel_reason: str | None = None  # "user" | "shutdown"
    cell: bool = True  # False for a task that plays a workflow: it orchestrates, so it holds no cell slot
    locks: frozenset[int] = frozenset()  # volumes this run holds while it writes (writers take turns)


class ActiveRuns:
    """Own all live and reserved folders, including the commit-to-launch gap."""

    def __init__(self) -> None:
        self.live: dict[int, _Live] = {}
        self.starting: list[tuple[frozenset[int], int, str]] = []
        self.renaming_ids: set[int] = set()

    @property
    def active_cells(self) -> int:
        return sum(1 for live in self.live.values() if live.cell)

    def runs_using(self, volume_id: int) -> list[tuple[int, str]]:
        """The runs (task id, title) that have a folder mounted, read only or not. While there are any, the Files page
        leaves the folder alone: a change from outside could break what an agent is in the middle of."""
        live = [
            (x.spec.task_id, x.spec.title)
            for x in self.live.values()
            if x.spec and any(m.volume_id == volume_id for m in x.spec.mounts)
        ]
        return live + [(task_id, title) for ids, task_id, title in self.starting if volume_id in ids]

    @contextlib.contextmanager
    def renaming(self, volume_id: int):
        """Held while a folder is renamed (its directory moves, then the database follows). A run planned meanwhile would
        mount the old path and make a fresh empty folder there, so none starts on this folder until it is done."""
        self.renaming_ids.add(volume_id)
        try:
            yield
        finally:
            self.renaming_ids.discard(volume_id)

    def admit(self, budget: Cost, cells: list[_Plan]) -> list[_Plan]:
        """The planned cells that start now: in order, those whose folders are free, as far as the budget reaches."""
        # a folder that writers must take turns on is held by one run at a time; a task that wants a busy one
        # lets the next task go first, so it never sits on budget while it waits
        claimed: set[int] = set().union(*(live.locks for live in self.live.values()))
        eligible = []
        for plan in cells:
            if plan.locks & claimed or any(m.volume_id in self.renaming_ids for m in plan.mounts):
                continue
            claimed |= plan.locks
            eligible.append(plan)
        running = [
            Cost(live.spec.cpus, live.spec.memory_mb)
            for live in self.live.values()
            if live.cell and live.spec
        ]
        return eligible[: admit(budget, running, [p.cost for p in eligible])]
