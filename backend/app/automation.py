"""The automation guard: what keeps workflows from chasing a task around the boards for ever.

Two numbers, each with the same three layers as a cell profile (see profiles.py): the global Settings, then the
project, then a single task. Only what differs is stored, so a changed default still reaches everything that did not
override it.

- the start cooldown: a task starts, and a workflow starts for it, only this many seconds after the task last changed
- the hop limit: how many times automation may move or make the same task in a row. Every move or creation by a
  workflow step counts one more (`Task.hops`), a person acting on the task starts the count again, and past the limit
  the step stops with a reason.
"""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import Integer, cast, func

from .app_settings import AppSettings
from .models import Project, Task


class AutomationOverrides(BaseModel):
    """The guard settings a project may change. Empty fields are not overridden."""

    model_config = ConfigDict(extra="forbid")

    start_cooldown_seconds: int | None = Field(default=None, ge=0, le=3600)
    max_hops: int | None = Field(default=None, ge=1, le=100)

    def clean(self) -> dict[str, Any] | None:
        """What is stored: only the fields that are set, or None when nothing is overridden."""
        return self.model_dump(exclude_none=True) or None


def _layered(task_value: int | None, project: dict[str, Any] | None, key: str, default: int) -> int:
    if task_value is not None:
        return task_value
    value = (project or {}).get(key)
    return default if value is None else int(value)


def start_cooldown(cfg: AppSettings, project: Project | None, task: Task) -> int:
    return _layered(
        task.cooldown_seconds,
        project.automation if project else None,
        "start_cooldown_seconds",
        cfg.start_cooldown_seconds,
    )


def hop_limit(cfg: AppSettings, project: Project | None, task: Task | None) -> int:
    return _layered(
        task.max_hops if task else None,
        project.automation if project else None,
        "max_hops",
        cfg.max_automation_hops,
    )


def cooled_down(cfg: AppSettings, now_epoch: int):
    """The same cooldown as an SQL condition for the scheduler (Task and Project must both be in the query): the task
    last changed at least its cooldown ago. Whole seconds on purpose, so no floating point decides a tie."""
    cooldown = func.coalesce(
        Task.cooldown_seconds,
        cast(func.json_extract(Project.automation, "$.start_cooldown_seconds"), Integer),
        cfg.start_cooldown_seconds,
    )
    return cast(func.strftime("%s", Task.updated_at), Integer) + cooldown <= now_epoch
