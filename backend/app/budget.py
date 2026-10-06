"""The resource budget: how much of the machine ThemisForge may use for cells at the same time.

Plain functions with no I/O, so the rules are easy to read and test. The scheduler asks `admit` which waiting cells
fit next to the running ones; Settings shows `recommend_budget` and `cells_that_fit`.
"""

import math
from dataclasses import dataclass

_EPS = 1e-9  # float slack, so three 0.1 CPU cells fit in a 0.3 CPU budget

CPU_RESERVE_MIN = 1.0  # CPUs always left for the machine itself...
CPU_RESERVE_SHARE = 0.20  # ...or this share of them, whichever is more
MEMORY_SHARE = 0.75  # of the RAM may go to cells


@dataclass(frozen=True)
class Cost:
    """What one cell reserves while it runs."""

    cpus: float
    memory_mb: int


def total(costs: list[Cost]) -> Cost:
    return Cost(sum(c.cpus for c in costs), sum(c.memory_mb for c in costs))


def fits(budget: Cost, used: Cost, cost: Cost) -> bool:
    return used.cpus + cost.cpus <= budget.cpus + _EPS and used.memory_mb + cost.memory_mb <= budget.memory_mb


def never_fits(budget: Cost, cost: Cost) -> bool:
    """A cell bigger than the whole budget could wait forever, so it is rejected instead."""
    return not fits(budget, Cost(0, 0), cost)


def admit(budget: Cost, running: list[Cost], waiting: list[Cost]) -> int:
    """How many of the waiting cells (in order) may start now.

    Strictly in order: when one does not fit yet, nothing behind it jumps ahead, so a big cell is never starved by
    a stream of small ones. Cells that can never fit must be taken out of `waiting` first (see `never_fits`).
    """
    used = total(running)
    started = 0
    for cost in waiting:
        if not fits(budget, used, cost):
            break
        used = Cost(used.cpus + cost.cpus, used.memory_mb + cost.memory_mb)
        started += 1
    return started


def cells_that_fit(budget: Cost, cost: Cost) -> int:
    """How many cells of this size fit in the budget at once."""
    return max(0, int(min(budget.cpus / cost.cpus + _EPS, budget.memory_mb // cost.memory_mb)))


def recommend_budget(host_cpus: int, host_memory_mb: int) -> Cost:
    """A budget that leaves the machine itself room: a CPU (or a fifth of them) and a quarter of the memory."""
    reserve = max(CPU_RESERVE_MIN, host_cpus * CPU_RESERVE_SHARE)
    return Cost(float(max(1, math.floor(host_cpus - reserve))), max(64, int(host_memory_mb * MEMORY_SHARE)))
