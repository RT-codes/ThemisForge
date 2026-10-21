from pydantic import BaseModel


class HaltIn(BaseModel):
    stop_running: bool = (
        True  # also stop what is running now; off lets it finish and only holds back what is next
    )


import re
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.execution.profiles import ProfileOverrides
from app.features.projects.automation import AutomationOverrides
from app.features.projects.properties import HEX_COLOR, PropertyDef

_ICON_NAME = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


def _icon(v: str | None) -> str | None:
    """A Lucide icon name such as "folder-kanban", or empty for the default. Whether the name exists is up to the
    interface, which falls back to the default icon for one it does not know."""
    if v is None:
        return None
    if v and not _ICON_NAME.match(v):
        raise ValueError("An icon is named like 'folder-kanban'")
    return v


class ProjectIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    purpose: str = Field(default="", max_length=200)
    description: str = Field(default="", max_length=2000)
    icon: str = Field(default="", max_length=40)
    cell_profile: ProfileOverrides | None = None  # overrides of the global cell defaults
    automation: AutomationOverrides | None = None  # overrides of the global automation guard

    @field_validator("name")
    @classmethod
    def strip_name(cls, v: str) -> str:
        if not (v := v.strip()):
            raise ValueError("Name cannot be empty")
        return v

    _check_icon = field_validator("icon")(_icon)


class ProjectPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    purpose: str | None = Field(default=None, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    icon: str | None = Field(default=None, max_length=40)
    properties: list[PropertyDef] | None = None
    cell_profile: ProfileOverrides | None = None  # sent as null: back to the global defaults
    automation: AutomationOverrides | None = None  # sent as null: back to the global guard

    _check_icon = field_validator("icon")(_icon)


class ProjectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    purpose: str
    description: str
    icon: str
    properties: list[PropertyDef]
    cell_profile: dict[str, Any] | None
    automation: dict[str, Any] | None
    halted_at: (
        datetime | None
    )  # set while nothing in the project may start (see app/features/projects/halt.py)
    created_at: datetime


class ProjectSummary(ProjectOut):
    task_counts: dict[str, int]
    next_run_at: datetime | None


def _name(v: str) -> str:
    if not (v := v.strip()):
        raise ValueError("Name cannot be empty")
    return v


def _color(v: str | None) -> str | None:
    if v is not None and not HEX_COLOR.match(v):
        raise ValueError(f"'{v}' is not a colour like #3b82f6")
    return v.lower() if v else v


class WorkspaceIn(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    purpose: str = Field(default="", max_length=200)
    description: str = Field(default="", max_length=5000)
    icon: str = Field(default="", max_length=40)

    _strip_name = field_validator("name")(_name)
    _check_icon = field_validator("icon")(_icon)


class WorkspacePatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=60)
    purpose: str | None = Field(default=None, max_length=200)
    description: str | None = Field(default=None, max_length=5000)
    icon: str | None = Field(default=None, max_length=40)
    position: float | None = None

    _check_icon = field_validator("icon")(_icon)

    @field_validator("name")
    @classmethod
    def strip_name(cls, v: str | None) -> str | None:
        return None if v is None else _name(v)


class BoardIn(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    purpose: str = Field(default="", max_length=200)

    _strip_name = field_validator("name")(_name)


class BoardPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=60)
    purpose: str | None = Field(default=None, max_length=200)
    position: float | None = None
    workspace_id: int | None = None  # move the board to another workspace of the project

    @field_validator("name")
    @classmethod
    def strip_name(cls, v: str | None) -> str | None:
        return None if v is None else _name(v)


class StatusIn(BaseModel):
    """A new custom status for a board."""

    name: str = Field(min_length=1, max_length=40)
    color: str | None = None
    index: int | None = Field(default=None, ge=0)  # where among the columns; left out: at the end
    icon: str = Field(default="box", max_length=40)
    description: str = Field(default="", max_length=300)  # what it is for, shown in its tooltip

    _strip_name = field_validator("name")(_name)
    _check_color = field_validator("color")(_color)
    _check_icon = field_validator("icon")(_icon)


class StatusPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=40)
    color: str | None = None  # sent as null: no colour
    index: int | None = Field(default=None, ge=0)
    icon: str | None = Field(default=None, max_length=40)  # empty: the default icon
    description: str | None = Field(default=None, max_length=300)

    _check_icon = field_validator("icon")(_icon)

    @field_validator("name")
    @classmethod
    def strip_name(cls, v: str | None) -> str | None:
        return None if v is None else _name(v)

    _check_color = field_validator("color")(_color)


class ColumnOut(BaseModel):
    """One column of a board: a built-in status or a custom one (see app/boards.py)."""

    key: str  # "ready", or "custom:12"
    name: str
    builtin: bool
    color: str | None = None  # custom statuses only; built-ins have their own colors in the interface
    icon: str = ""  # custom statuses only: a Lucide icon name
    description: str = ""  # custom statuses only: what it is for


class BoardOut(BaseModel):
    id: int
    project_id: int
    workspace_id: int
    name: str
    purpose: str
    position: float
    columns: list[ColumnOut]
    task_counts: dict[str, int]  # tasks per status key, for summaries
    halted_at: datetime | None  # set while nothing on the board may start
    created_at: datetime


class WorkspaceOut(BaseModel):
    id: int
    project_id: int
    name: str
    purpose: str
    description: str
    icon: str
    position: float
    created_at: datetime
    boards: list[BoardOut]


class ProjectEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    kind: str
    title: str
    actor: str
    cause: str
    workspace_id: int | None
    board_id: int | None
    task_id: int | None
    data: dict[str, Any]
    created_at: datetime
