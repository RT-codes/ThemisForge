from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Dialect,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    TypeDecorator,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def utcnow() -> datetime:
    return datetime.now(UTC)


class UtcDateTime(TypeDecorator):
    """SQLite drops tzinfo; this stores UTC and hands back timezone-aware datetimes."""

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("naive datetime: use timezone-aware values")
        return value.astimezone(UTC)

    def process_result_value(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(100))
    password_hash: Mapped[str] = mapped_column(String(255))
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    created_at: Mapped[datetime] = mapped_column(UtcDateTime(), default=utcnow)


class TaskStatus(StrEnum):
    BACKLOG = "backlog"
    READY = "ready"
    RUNNING = "running"
    REVIEW = "review"
    DONE = "done"
    BLOCKED = "blocked"
    FAILED = "failed"


class ScheduleKind(StrEnum):
    NONE = "none"
    ONCE = "once"
    CRON = "cron"


class AttemptStatus(StrEnum):
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(Text, default="")
    # Custom Kanban properties: [{"key", "name", "type", "options"}], see app/properties.py.
    properties: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    # Overrides of the global cell defaults for this project's cells: {"image", "cpus", "memory_mb", "timeout_seconds"},
    # only the fields that differ (see app/profiles.py). None = use the global defaults.
    cell_profile: Mapped[dict[str, Any] | None] = mapped_column(JSON, default=None)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime(), default=utcnow)

    tasks: Mapped[list["Task"]] = relationship(back_populates="project", cascade="all, delete-orphan")


class ProjectEvent(Base):
    """One line of a project's history: something was done to it. Kept when the thing itself is gone, so it holds its
    own copy: the title, who did it, and in `data` whatever is needed to look at the thing again."""

    __tablename__ = "project_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(30))  # "task_deleted"
    title: Mapped[str] = mapped_column(String(200), default="")
    actor: Mapped[str] = mapped_column(String(100), default="")  # the user's name at the time
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


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    # The board the task lives on. Boards with tasks are never deleted outright (the API moves the tasks first), the
    # cascade only serves deleting a whole project.
    board_id: Mapped[int] = mapped_column(ForeignKey("boards.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    # A built-in status ("backlog"...) or a custom one of its board ("custom:<id>", see BoardStatus).
    status: Mapped[str] = mapped_column(String(20), default=TaskStatus.BACKLOG, index=True)
    position: Mapped[float] = mapped_column(Float, default=0.0)
    properties: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    schedule_kind: Mapped[str] = mapped_column(String(10), default=ScheduleKind.NONE)
    cron: Mapped[str | None] = mapped_column(String(100), default=None)
    run_at: Mapped[datetime | None] = mapped_column(UtcDateTime(), default=None)
    # The scheduler picks up READY tasks whose next_run_at is empty or in the past.
    next_run_at: Mapped[datetime | None] = mapped_column(UtcDateTime(), default=None, index=True)
    last_run_at: Mapped[datetime | None] = mapped_column(UtcDateTime(), default=None)
    review_on_success: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    # What runs: "" = the placeholder program in a cell, "codex" = Codex in a cell (see app/harness.py),
    # "workflow" = play the workflow below instead of running a cell.
    harness: Mapped[str] = mapped_column(String(20), default="", server_default="")
    workflow_id: Mapped[int | None] = mapped_column(
        ForeignKey("workflows.id", ondelete="SET NULL"), default=None
    )
    # The agent that does this task (its instructions, model, cell and folders), see Agent below.
    agent_id: Mapped[int | None] = mapped_column(ForeignKey("agents.id", ondelete="SET NULL"), default=None)
    # Extras for this one run, set by a workflow's Agent node: {"profile": {...}, "mounts": [{"volume_id", "mode"}]}.
    run_options: Mapped[dict[str, Any] | None] = mapped_column(JSON, default=None)

    created_at: Mapped[datetime] = mapped_column(UtcDateTime(), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UtcDateTime(), default=utcnow, onupdate=utcnow)

    project: Mapped[Project] = relationship(back_populates="tasks")
    attempts: Mapped[list["Attempt"]] = relationship(
        back_populates="task", cascade="all, delete-orphan", order_by="Attempt.id.desc()"
    )


class Attempt(Base):
    """One execution of a task inside a cell: when it ran, what it logged, how it ended."""

    __tablename__ = "attempts"

    id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(20), default=AttemptStatus.RUNNING)
    started_at: Mapped[datetime] = mapped_column(UtcDateTime(), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(UtcDateTime(), default=None)
    exit_code: Mapped[int | None] = mapped_column(Integer, default=None)
    log: Mapped[str] = mapped_column(Text, default="")
    result: Mapped[str] = mapped_column(Text, default="")
    # set when the task played a workflow: the run that did the work
    workflow_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("workflow_runs.id", ondelete="SET NULL"), default=None
    )

    task: Mapped[Task] = relationship(back_populates="attempts")


class RequestStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    DENIED = "denied"


class AccessRequest(Base):
    """Someone without an account asking the administrator for access."""

    __tablename__ = "access_requests"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    email: Mapped[str] = mapped_column(String(320), index=True)
    reason: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(10), default=RequestStatus.PENDING, index=True)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime(), default=utcnow)
    decided_at: Mapped[datetime | None] = mapped_column(UtcDateTime(), default=None)


class Invite(Base):
    """A single-use link that lets one email address create an account. Only a hash of the token is stored."""

    __tablename__ = "invites"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(320), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), default=None)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime(), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(UtcDateTime())
    used_at: Mapped[datetime | None] = mapped_column(UtcDateTime(), default=None)


class Secret(Base):
    """A named credential. The value is encrypted at rest (see app/crypto.py)."""

    __tablename__ = "secrets"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    kind: Mapped[str] = mapped_column(String(50), default="custom")
    value_encrypted: Mapped[str] = mapped_column(Text)
    hint: Mapped[str] = mapped_column(String(20), default="")
    created_at: Mapped[datetime] = mapped_column(UtcDateTime(), default=utcnow)


class CodexConnection(Base):
    """One user's Codex login (ChatGPT plan). The whole auth.json is encrypted at rest (see app/codex.py)."""

    __tablename__ = "codex_connections"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True)
    auth_encrypted: Mapped[str] = mapped_column(Text)
    account: Mapped[str] = mapped_column(String(320), default="")
    connected_at: Mapped[datetime] = mapped_column(UtcDateTime(), default=utcnow)
    refreshed_at: Mapped[datetime | None] = mapped_column(UtcDateTime(), default=None)


class RunStatus(StrEnum):
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class NodeStatus(StrEnum):
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"
    CANCELLED = "cancelled"


class Workflow(Base):
    """A workflow in a project's library: nodes and edges as JSON (see app/workflows.py)."""

    __tablename__ = "workflows"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(100), default="Workflow")
    description: Mapped[str] = mapped_column(Text, default="")
    graph: Mapped[dict[str, Any]] = mapped_column(JSON, default=lambda: {"nodes": [], "edges": []})
    created_at: Mapped[datetime] = mapped_column(UtcDateTime(), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UtcDateTime(), default=utcnow, onupdate=utcnow)


class WorkflowRun(Base):
    """One execution of a workflow, with the graph as it was when the run began."""

    __tablename__ = "workflow_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    workflow_id: Mapped[int] = mapped_column(ForeignKey("workflows.id", ondelete="CASCADE"), index=True)
    # the run that is waiting for the task that started this one (a workflow played from a task inside a workflow)
    parent_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("workflow_runs.id", ondelete="SET NULL"), default=None
    )
    status: Mapped[str] = mapped_column(String(20), default=RunStatus.RUNNING)
    trigger: Mapped[str] = mapped_column(String(20), default="test")  # test | task | status
    # the task whose move into a status started this run (trigger "status"); its nodes can work with it
    trigger_task_id: Mapped[int | None] = mapped_column(
        ForeignKey("tasks.id", ondelete="SET NULL"), default=None
    )
    outcome: Mapped[str] = mapped_column(Text, default="")  # what the End node said, or why the run failed
    started_at: Mapped[datetime] = mapped_column(UtcDateTime(), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(UtcDateTime(), default=None)
    graph: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    nodes: Mapped[list["WorkflowNodeRun"]] = relationship(
        back_populates="run", cascade="all, delete-orphan", order_by="WorkflowNodeRun.seq"
    )


class WorkflowNodeRun(Base):
    """What happened at one node during a run: when, how it ended, its output and any error."""

    __tablename__ = "workflow_node_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("workflow_runs.id", ondelete="CASCADE"), index=True)
    node_id: Mapped[str] = mapped_column(String(64))
    kind: Mapped[str] = mapped_column(String(20))
    label: Mapped[str] = mapped_column(String(100))
    seq: Mapped[int] = mapped_column(Integer)  # chronological order within the run
    status: Mapped[str] = mapped_column(String(20), default=NodeStatus.RUNNING)
    started_at: Mapped[datetime | None] = mapped_column(UtcDateTime(), default=None)
    finished_at: Mapped[datetime | None] = mapped_column(UtcDateTime(), default=None)
    log: Mapped[str] = mapped_column(Text, default="")
    result: Mapped[str] = mapped_column(Text, default="")
    error: Mapped[str] = mapped_column(Text, default="")
    task_id: Mapped[int | None] = mapped_column(ForeignKey("tasks.id", ondelete="SET NULL"), default=None)
    attempt_id: Mapped[int | None] = mapped_column(
        ForeignKey("attempts.id", ondelete="SET NULL"), default=None
    )

    run: Mapped[WorkflowRun] = relationship(back_populates="nodes")


class AppSetting(Base):
    """Key/value store for operator settings edited from the Settings page."""

    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[Any] = mapped_column(JSON)


class Volume(Base):
    """A folder that outlives a run and can be mounted into cells at /workspace/NAME (see app/volumes.py)."""

    __tablename__ = "volumes"
    # ids are never reused (SQLite would hand a deleted newest id to the next row): workflow nodes refer to a folder by
    # id, and a stale one must never quietly point at a different folder
    __table_args__ = (
        UniqueConstraint("project_id", "name", name="uq_volumes_project_id_name"),
        {"sqlite_autoincrement": True},
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(40))  # a slug: it becomes the folder name inside the cell
    kind: Mapped[str] = mapped_column(String(10), default="managed")  # "managed" (ThemisForge's own) | "host"
    host_path: Mapped[str] = mapped_column(Text, default="")  # kind "host": the folder on this machine
    mode: Mapped[str] = mapped_column(String(2), default="rw")  # the most a cell may do: "ro" | "rw"
    exclusive_write: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="0"
    )  # writers take turns
    created_at: Mapped[datetime] = mapped_column(UtcDateTime(), default=utcnow)


class Agent(Base):
    """A configured worker of a project: who it is, what it was told, how it runs (see app/harness.py)."""

    __tablename__ = "agents"
    # never reuse an id: workflow nodes name their agent by id, and an agent can hold keys
    __table_args__ = (
        UniqueConstraint("project_id", "name", name="uq_agents_project_id_name"),
        {"sqlite_autoincrement": True},
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(100))
    role: Mapped[str] = mapped_column(String(200), default="")  # one line: what it is responsible for
    description: Mapped[str] = mapped_column(Text, default="")  # for people: what this agent is for
    instructions: Mapped[str] = mapped_column(
        Text, default=""
    )  # for the agent: always put in front of its task
    harness: Mapped[str] = mapped_column(String(20), default="codex")
    model: Mapped[str] = mapped_column(String(100), default="")  # empty = the model in Settings
    reasoning_effort: Mapped[str] = mapped_column(String(10), default="")  # empty = the effort in Settings
    cell_profile: Mapped[dict[str, Any] | None] = mapped_column(
        JSON, default=None
    )  # overrides, like a project's
    mounts: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)  # [{"volume_id", "mode"}]
    skills: Mapped[list[str]] = mapped_column(
        JSON, default=list, server_default="[]"
    )  # names, see app/skills.py
    mcp_servers: Mapped[list[int]] = mapped_column(JSON, default=list, server_default="[]")  # McpServer ids
    secrets: Mapped[list[int]] = mapped_column(
        JSON, default=list, server_default="[]"
    )  # Secret ids, see app/keys.py
    # The agent's file in the project's config folder is the source of truth (see app/project_config.py); this row is
    # its identity (tasks and workflows point at the id) and a parsed copy for fast lists and for planning runs.
    path: Mapped[str] = mapped_column(
        String(300), default="", server_default=""
    )  # relative to the config folder
    config_error: Mapped[str] = mapped_column(
        Text, default="", server_default=""
    )  # why the file cannot be read
    created_at: Mapped[datetime] = mapped_column(UtcDateTime(), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UtcDateTime(), default=utcnow, onupdate=utcnow)


class McpServer(Base):
    """A tool server (MCP) a project's agents can be given, written into the harness config for each run."""

    __tablename__ = "mcp_servers"
    __table_args__ = (
        UniqueConstraint("project_id", "name", name="uq_mcp_servers_project_id_name"),
        {"sqlite_autoincrement": True},
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(40))  # a slug: it is the server's name in the agent's config
    kind: Mapped[str] = mapped_column(String(10), default="stdio")  # "stdio" (a command) | "http"
    command: Mapped[str] = mapped_column(Text, default="")
    args: Mapped[list[str]] = mapped_column(JSON, default=list)
    url: Mapped[str] = mapped_column(Text, default="")
    env: Mapped[dict[str, str]] = mapped_column(
        JSON, default=dict
    )  # plain settings for the server's environment
    secret_env: Mapped[dict[str, int]] = mapped_column(
        JSON, default=dict
    )  # environment variable -> Secret id
    bearer_secret_id: Mapped[int | None] = mapped_column(
        Integer, default=None
    )  # http: the key sent as a bearer token
    description: Mapped[str] = mapped_column(Text, default="", server_default="")  # for people
    # like Agent.path: the file in the config folder is the truth, this row is its identity and a parsed copy
    path: Mapped[str] = mapped_column(String(300), default="", server_default="")
    config_error: Mapped[str] = mapped_column(Text, default="", server_default="")
    last_test: Mapped[dict[str, Any] | None] = mapped_column(
        JSON, default=None
    )  # the latest connection test: {"ok", "message", "tools", "at"}
    created_at: Mapped[datetime] = mapped_column(UtcDateTime(), default=utcnow)
