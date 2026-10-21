from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.persistence.models.tasks import Task
from typing import Any

from sqlalchemy import (
    JSON,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.persistence.db import Base
from app.persistence.models.common import TaskStatus, UtcDateTime, utcnow


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(100))
    purpose: Mapped[str] = mapped_column(
        String(200), default="", server_default=""
    )  # one line: what it is for
    description: Mapped[str] = mapped_column(Text, default="")
    # The name of a Lucide icon ("folder-kanban") shown beside the project; empty = the default icon.
    icon: Mapped[str] = mapped_column(String(40), default="", server_default="")
    # Custom Kanban properties: [{"key", "name", "type", "options"}], see app/features/projects/properties.py.
    properties: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    # Overrides of the global cell defaults for this project's cells: {"image", "cpus", "memory_mb", "timeout_seconds"},
    # only the fields that differ (see app/execution/profiles.py). None = use the global defaults.
    cell_profile: Mapped[dict[str, Any] | None] = mapped_column(JSON, default=None)
    # Overrides of the global automation guard for this project: {"start_cooldown_seconds", "max_hops"}, only the
    # fields that differ (see app/features/projects/automation.py). None = use the global settings.
    automation: Mapped[dict[str, Any] | None] = mapped_column(JSON, default=None)
    # Set while the project is halted: nothing in it starts (tasks, workflow runs, triggers) until it is resumed. It is
    # a state of its own, not a task status, so resuming never has to remember what was where (see app/features/projects/halt.py).
    halted_at: Mapped[datetime | None] = mapped_column(UtcDateTime(), default=None)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime(), default=utcnow)

    tasks: Mapped[list["Task"]] = relationship(back_populates="project", cascade="all, delete-orphan")


class ProjectEvent(Base):
    """One line of a project's history: something was done to it. Kept when the thing itself is gone, so it holds its
    own copy: the title, who did it, and in `data` whatever is needed to look at the thing again."""

    __tablename__ = "project_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(30))  # "task_deleted", "task_moved", "task_spawned"
    title: Mapped[str] = mapped_column(String(200), default="")
    actor: Mapped[str] = mapped_column(
        String(100), default=""
    )  # the user's name at the time, or "Workflow <name>"
    # What set it off when it was not a person: "run:<workflow run id>:<node id>". Empty for something a person did.
    cause: Mapped[str] = mapped_column(String(80), default="", server_default="")
    # Where it happened. Plain numbers, not foreign keys: the history outlives the task and the board it names.
    workspace_id: Mapped[int | None] = mapped_column(Integer, default=None, index=True)
    board_id: Mapped[int | None] = mapped_column(Integer, default=None, index=True)
    task_id: Mapped[int | None] = mapped_column(Integer, default=None, index=True)
    data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime(), default=utcnow)


class Workspace(Base):
    """A named, purposeful area of a project that holds boards (see app/boards.py).

    Organisation only: tasks, the scheduler, agents and cells stay project-wide. Not to be confused with the
    `/workspace` folder inside a cell."""

    __tablename__ = "workspaces"
    # ids are never reused: workflow nodes refer to workspaces and boards by id (same reasoning as Volume)
    __table_args__ = ({"sqlite_autoincrement": True},)

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(60))
    purpose: Mapped[str] = mapped_column(String(200), default="")  # one line: what this area is for
    description: Mapped[str] = mapped_column(Text, default="")
    icon: Mapped[str] = mapped_column(
        String(40), default="", server_default=""
    )  # a Lucide icon name, see Project
    position: Mapped[float] = mapped_column(Float, default=0.0)  # order among the project's workspaces
    created_at: Mapped[datetime] = mapped_column(UtcDateTime(), default=utcnow)


class Board(Base):
    """One Kanban of a workspace. Its columns are the seven built-in statuses plus any custom ones (BoardStatus)."""

    __tablename__ = "boards"
    __table_args__ = ({"sqlite_autoincrement": True},)

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(60))
    purpose: Mapped[str] = mapped_column(String(200), default="")
    position: Mapped[float] = mapped_column(Float, default=0.0)  # order within the workspace
    # The board's columns left to right, as status keys: built-in values ("backlog"...) and custom "custom:<id>"
    # keys. The built-ins are always all here, in their fixed order; only custom keys move around them.
    columns: Mapped[list[str]] = mapped_column(JSON, default=lambda: [s.value for s in TaskStatus])
    halted_at: Mapped[datetime | None] = mapped_column(UtcDateTime(), default=None)  # see Project.halted_at
    created_at: Mapped[datetime] = mapped_column(UtcDateTime(), default=utcnow)


class BoardStatus(Base):
    """A custom status: a column a board added to the seven built-in ones (see app/boards.py).

    A task in one is addressed by the key "custom:<id>", so renaming never touches tasks or workflow graphs. The
    scheduler only reacts to Ready and Running, so a task parked in a custom status is simply never started."""

    __tablename__ = "board_statuses"
    __table_args__ = (
        {"sqlite_autoincrement": True},
    )  # a deleted status's key must never come back as another

    id: Mapped[int] = mapped_column(primary_key=True)
    board_id: Mapped[int] = mapped_column(ForeignKey("boards.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(40))
    color: Mapped[str | None] = mapped_column(String(7), default=None)  # "#rrggbb"
    icon: Mapped[str] = mapped_column(String(40), default="box", server_default="box")  # a Lucide icon name
    # What the status is for, shown in the tooltip of its column: the owner's words, empty for a generic line
    description: Mapped[str] = mapped_column(String(300), default="", server_default="")
