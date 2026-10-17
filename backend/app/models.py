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
    purpose: Mapped[str] = mapped_column(
        String(200), default="", server_default=""
    )  # one line: what it is for
    description: Mapped[str] = mapped_column(Text, default="")
    # The name of a Lucide icon ("folder-kanban") shown beside the project; empty = the default icon.
    icon: Mapped[str] = mapped_column(String(40), default="", server_default="")
    # Custom Kanban properties: [{"key", "name", "type", "options"}], see app/properties.py.
    properties: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    # Overrides of the global cell defaults for this project's cells: {"image", "cpus", "memory_mb", "timeout_seconds"},
    # only the fields that differ (see app/profiles.py). None = use the global defaults.
    cell_profile: Mapped[dict[str, Any] | None] = mapped_column(JSON, default=None)
    # Overrides of the global automation guard for this project: {"start_cooldown_seconds", "max_hops"}, only the
    # fields that differ (see app/automation.py). None = use the global settings.
    automation: Mapped[dict[str, Any] | None] = mapped_column(JSON, default=None)
    # Set while the project is halted: nothing in it starts (tasks, workflow runs, triggers) until it is resumed. It is
    # a state of its own, not a task status, so resuming never has to remember what was where (see app/halt.py).
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
    # The task this one was spawned from (a follow-up made on another board); the link survives a move of either task.
    origin_task_id: Mapped[int | None] = mapped_column(
        ForeignKey("tasks.id", ondelete="SET NULL"), default=None, index=True
    )
    # Made by a workflow step: "run:<run id>:<node id>". Unique, so a step that runs again cannot make a second task.
    origin_key: Mapped[str | None] = mapped_column(String(80), default=None, unique=True)
    # Loop guard (see app/automation.py). `hops` counts how many times automation moved or made this task in a row; a
    # person acting on it starts the count again. The two overrides beat the project's and the global settings.
    hops: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    cooldown_seconds: Mapped[int | None] = mapped_column(Integer, default=None)
    max_hops: Mapped[int | None] = mapped_column(Integer, default=None)
    # What runs: "" = the placeholder program in a cell, "codex" = Codex in a cell (see app/harness.py),
    # "workflow" = play the workflows of its TaskStage rows, one after the other, instead of running a cell.
    harness: Mapped[str] = mapped_column(String(20), default="", server_default="")
    # The agent that does this task (its instructions, model, cell and folders), see Agent below.
    agent_id: Mapped[int | None] = mapped_column(ForeignKey("agents.id", ondelete="SET NULL"), default=None)
    # Extras for this one run, set by a workflow's Agent node:
    # {"profile": {...}, "mounts": [{"volume_id", "mode"}], "workdir": <attempt id>}.
    run_options: Mapped[dict[str, Any] | None] = mapped_column(JSON, default=None)
    # Made by a workflow's Agent node to run its step: a task only so the scheduler, the budget and the history work
    # on it. It is not board work, so it stays off the boards and out of the counts (unless asked for), never starts a
    # workflow by being moved, and does not wait out the start delay: the workflow is already waiting for it.
    internal: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")

    created_at: Mapped[datetime] = mapped_column(UtcDateTime(), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UtcDateTime(), default=utcnow, onupdate=utcnow)

    project: Mapped[Project] = relationship(back_populates="tasks")
    attempts: Mapped[list["Attempt"]] = relationship(
        back_populates="task", cascade="all, delete-orphan", order_by="Attempt.id.desc()"
    )


class TaskStage(Base):
    """One workflow a task plays, in order. Its progress is the run it started in the task's latest attempt.

    Read and written through queries (see the task router), not a relationship on Task: tasks are loaded and made in
    many async places, where an unloaded collection would fail on access.

    There is no status column on purpose: a stage with no run is "not started", otherwise it is whatever its run says,
    so the two can never disagree. A new attempt clears every `workflow_run_id` (see WorkflowRunner.run_for_task);
    the runs themselves, and the attempt that started them, stay as the history.
    """

    __tablename__ = "task_stages"

    id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), index=True)
    position: Mapped[int] = mapped_column(Integer)
    # deleting a workflow takes it out of the tasks that played it
    workflow_id: Mapped[int] = mapped_column(ForeignKey("workflows.id", ondelete="CASCADE"), index=True)
    workflow_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("workflow_runs.id", ondelete="SET NULL"), default=None
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
    # set when the task played workflows: the run of the stage playing now, or of the last one that did
    workflow_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("workflow_runs.id", ondelete="SET NULL"), default=None
    )
    # The working folder this attempt used, named by the attempt that made it (data/projects/<id>/workspaces/<n>).
    # Its own id unless the run continued in an earlier folder; a task that plays workflows gets the folder its last
    # stage ended in, so whatever waits for it can carry on there. Null on attempts from before folders were passed on.
    workdir_id: Mapped[int | None] = mapped_column(Integer, default=None, index=True)
    # What the cell changed in that folder: {"added": [...], "changed": [...], "removed": [...], "more": n}. It is what
    # the next run in the folder is told (see harness.workdir_note). Null for tasks that ran no cell.
    changes: Mapped[dict[str, Any] | None] = mapped_column(JSON, default=None)
    # Why a failed attempt failed, for the person looking at the ticket: {"source": "themis" | "agent", "reason",
    # "action", "tail"}. `source` says who worked it out (Themis from what it saw, or the agent that stopped and said so
    # in /cell/blocked.md); `action` is what to change, empty when nobody knows; `tail` is the last lines of the log.
    # Null on a run that did not fail, and on attempts from before reasons were kept.
    failure: Mapped[dict[str, Any] | None] = mapped_column(JSON, default=None)
    # What the attempt used, kept as the harness reported it and not as money: prices change, and a subscription has
    # none, so cost is worked out from these later. `harness`, `model` (the one really used, Settings' default filled
    # in) and `billing` ("subscription" | "api") are set when the attempt starts; the token counts when it ends,
    # added up over the runs it took (see Scheduler._execute). All null for attempts that ran no harness (the
    # placeholder program, a task that plays workflows) and for attempts from before usage was kept. The token counts
    # are also null when the harness reported none: a run that crashed or was cancelled before its turn ended.
    harness: Mapped[str | None] = mapped_column(String(20), default=None)
    model: Mapped[str | None] = mapped_column(String(100), default=None)
    billing: Mapped[str | None] = mapped_column(String(20), default=None)
    input_tokens: Mapped[int | None] = mapped_column(Integer, default=None)
    cached_input_tokens: Mapped[int | None] = mapped_column(Integer, default=None)  # part of input_tokens
    output_tokens: Mapped[int | None] = mapped_column(Integer, default=None)
    reasoning_output_tokens: Mapped[int | None] = mapped_column(
        Integer, default=None
    )  # part of output_tokens

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


class Connection(Base):
    """One user's sign in to an outside service (GitHub, ...). The credential is encrypted at rest (app/connections.py)."""

    __tablename__ = "connections"
    __table_args__ = (UniqueConstraint("user_id", "provider", "account", name="uq_connections_account"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    provider: Mapped[str] = mapped_column(String(40))  # a provider id, see app/connections.py
    method: Mapped[str] = mapped_column(String(10))  # how it was made: "token" | "oauth"
    credential_encrypted: Mapped[str] = mapped_column(Text)  # JSON, e.g. {"token": "..."}
    account: Mapped[str] = mapped_column(String(320), default="")  # who it is, shown in the UI ("octocat")
    settings: Mapped[dict[str, Any]] = mapped_column(
        JSON, default=dict
    )  # what the provider learned: no secrets
    connected_at: Mapped[datetime] = mapped_column(UtcDateTime(), default=utcnow)
    checked_at: Mapped[datetime | None] = mapped_column(UtcDateTime(), default=None)  # last successful test


class McpLogin(Base):
    """One user's sign in to a tool server that asks for one (see app/mcp_auth). It is the user's, not a project's: a
    project's tools use their owner's, found by the server's address, so signing in once covers every project and
    every tool that points at that server. The secret part is encrypted and owned by the auth scheme, so a scheme that
    keeps other things than tokens needs no new column."""

    __tablename__ = "mcp_logins"
    __table_args__ = (UniqueConstraint("user_id", "resource", name="uq_mcp_logins_resource"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    resource: Mapped[str] = mapped_column(String(2000))  # the server's address in its canonical form
    scheme: Mapped[str] = mapped_column(String(20))  # the auth scheme that made it
    status: Mapped[str] = mapped_column(String(20), default="active")  # "active" | "needs_sign_in"
    error: Mapped[str] = mapped_column(Text, default="")  # why it needs a new sign in, for people
    credential_encrypted: Mapped[str] = mapped_column(
        Text, default=""
    )  # JSON the scheme owns, see app/crypto.py
    account: Mapped[str] = mapped_column(String(320), default="")  # who it is, shown ("Acme workspace")
    settings: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)  # what the server said: no secrets
    expires_at: Mapped[datetime | None] = mapped_column(
        UtcDateTime(), default=None
    )  # when the token stops working
    refreshed_at: Mapped[datetime | None] = mapped_column(
        UtcDateTime(), default=None
    )  # last time it was renewed
    connected_at: Mapped[datetime] = mapped_column(UtcDateTime(), default=utcnow)


class ProjectConnection(Base):
    """The connection a project uses for a provider. Agents of the project can then opt in to it (Agent.connections)."""

    __tablename__ = "project_connections"
    __table_args__ = (UniqueConstraint("project_id", "provider", name="uq_project_connections_provider"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    provider: Mapped[str] = mapped_column(String(40))
    connection_id: Mapped[int] = mapped_column(ForeignKey("connections.id", ondelete="CASCADE"))
    config: Mapped[dict[str, Any]] = mapped_column(
        JSON, default=dict
    )  # per project, e.g. {"repo": "owner/name"}
    created_at: Mapped[datetime] = mapped_column(UtcDateTime(), default=utcnow)


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
    WAITING = "waiting"  # an approval gate, parked until a person decides (see WorkflowNodeRun.gate)


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


class NodePreset(Base):
    """A configured workflow node a project keeps in the editor's palette ("saved nodes"). It holds ids of the
    project's own agents, folders and boards, so it only makes sense inside that project."""

    __tablename__ = "node_presets"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(20))
    label: Mapped[str] = mapped_column(String(100), default="")
    config: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime(), default=utcnow)


class Webhook(Base):
    """An address other programs can post to, to make tasks in a project (see app/webhooks.py).

    The sender only provides what arrives (a message in any shape). Everything about the task that is made is set here,
    by the project's owner: where it lands, what runs it, which properties it has. Only a hash of the secret in the
    address is stored, like an invite's."""

    __tablename__ = "webhooks"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(60))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1")
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    token_hint: Mapped[str] = mapped_column(
        String(8), default=""
    )  # the last characters, to tell addresses apart
    # Where the tasks land. A deleted board leaves the webhook without one: deliveries are refused until another is chosen.
    board_id: Mapped[int | None] = mapped_column(ForeignKey("boards.id", ondelete="SET NULL"), default=None)
    status: Mapped[str] = mapped_column(String(20), default=TaskStatus.BACKLOG)  # as Task.status
    # How the message becomes a task: text with {{path.to.value}} holes filled from the message (see webhooks.render).
    # Empty means the message's own "title" / "description", else the webhook's name / the message as it came.
    title_template: Mapped[str] = mapped_column(String(200), default="", server_default="")
    description_template: Mapped[str] = mapped_column(Text, default="", server_default="")
    # Only messages that match make a task: [{"path", "equals": [...]}], all of them. Empty means every message.
    rules: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    # What the task is, as on Task: it is the same choice, made once for every task this webhook makes.
    harness: Mapped[str] = mapped_column(String(20), default="", server_default="")
    agent_id: Mapped[int | None] = mapped_column(ForeignKey("agents.id", ondelete="SET NULL"), default=None)
    workflow_ids: Mapped[list[int]] = mapped_column(JSON, default=list)
    properties: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    review_on_success: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    last_received_at: Mapped[datetime | None] = mapped_column(UtcDateTime(), default=None)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime(), default=utcnow)


class ControlToken(Base):
    """The key an outside agent (or, later, a run) holds to use Themis's MCP control plane (see app/control.py). It acts
    as its user. With a `project_id` it reaches that one project and nothing else; without one it reaches all of the
    user's projects and, for an administrator, the global settings. `scope` says what it may do: "read" looks, "write"
    also changes things.

    Unlike a webhook address it can be shown again: the secret is kept encrypted besides its hash, so the settings can
    always give the owner the full connect command instead of making them mint a new token."""

    __tablename__ = "control_tokens"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    project_id: Mapped[int | None] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True, default=None
    )  # None: every project of the user
    name: Mapped[str] = mapped_column(String(60))
    scope: Mapped[str] = mapped_column(String(10), default="read", server_default="read")
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)  # what a request is looked up by
    token_encrypted: Mapped[str] = mapped_column(Text)  # what the owner is shown again
    token_hint: Mapped[str] = mapped_column(
        String(8), default=""
    )  # the last characters, to tell tokens apart
    last_used_at: Mapped[datetime | None] = mapped_column(UtcDateTime(), default=None)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime(), default=utcnow)


class WebhookDelivery(Base):
    """One message that arrived at a webhook and what became of it. The newest few are kept, with the message itself,
    because the hard part of a webhook is knowing what the other side actually sent."""

    __tablename__ = "webhook_deliveries"

    id: Mapped[int] = mapped_column(primary_key=True)
    webhook_id: Mapped[int] = mapped_column(ForeignKey("webhooks.id", ondelete="CASCADE"), index=True)
    received_at: Mapped[datetime] = mapped_column(UtcDateTime(), default=utcnow)
    # "created" (a task was made), "skipped" (no rule matched, or the sender's ping), "duplicate" (the sender sent
    # the same delivery again) or "refused" (why is in `detail`)
    outcome: Mapped[str] = mapped_column(String(12))
    detail: Mapped[str] = mapped_column(String(300), default="")
    task_id: Mapped[int | None] = mapped_column(ForeignKey("tasks.id", ondelete="SET NULL"), default=None)
    event: Mapped[str] = mapped_column(String(60), default="")  # what the sender called it, e.g. "issues"
    delivery_key: Mapped[str] = mapped_column(String(120), default="")  # the sender's id for this delivery
    payload: Mapped[str] = mapped_column(Text, default="")  # the start of the message


class NotificationTarget(Base):
    """Somewhere Themis tells a project's owner that something happened: a Discord channel today (see
    app/notifications.py). `kind` names the adapter that knows how to talk to it; what that adapter needs (a channel
    address, a bot token) is kept in `config_encrypted`, like a stored key, and never returned by the API."""

    __tablename__ = "notification_targets"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(60))
    kind: Mapped[str] = mapped_column(String(20))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1")
    config_encrypted: Mapped[str] = mapped_column(Text)  # the adapter's fields as JSON, encrypted
    hint: Mapped[str] = mapped_column(String(20), default="")  # the end of the secret, to tell targets apart
    events: Mapped[list[str]] = mapped_column(
        JSON, default=list
    )  # which events it hears: app/notifications.EVENTS
    last_sent_at: Mapped[datetime | None] = mapped_column(UtcDateTime(), default=None)
    last_error: Mapped[str] = mapped_column(
        String(300), default=""
    )  # empty when the last message went through
    created_at: Mapped[datetime] = mapped_column(UtcDateTime(), default=utcnow)


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
    # The working folder (see Attempt.workdir_id) the last step of this run ended in. The next stage of a task
    # starts with it, so a node that asks to continue picks up where this run left off.
    workdir_id: Mapped[int | None] = mapped_column(Integer, default=None)
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
    # indexed because the open approvals (status "waiting") are looked up on every poll of the app
    status: Mapped[str] = mapped_column(String(20), default=NodeStatus.RUNNING, index=True)
    started_at: Mapped[datetime | None] = mapped_column(UtcDateTime(), default=None)
    finished_at: Mapped[datetime | None] = mapped_column(UtcDateTime(), default=None)
    log: Mapped[str] = mapped_column(Text, default="")
    result: Mapped[str] = mapped_column(Text, default="")
    error: Mapped[str] = mapped_column(Text, default="")
    # An approval gate keeps what it needs to be picked up again after a restart: what it asks ("prompt") and what the
    # node before it handed on ("previous", a Prev). The person's answer goes in the next three columns; the gate
    # polls them. `decision` is "" while open, then "approved" or "rejected" (written once, see decide_approval).
    gate: Mapped[dict[str, Any] | None] = mapped_column(JSON, default=None)
    decision: Mapped[str] = mapped_column(String(10), default="", server_default="")
    decision_note: Mapped[str] = mapped_column(Text, default="", server_default="")
    decided_by: Mapped[str] = mapped_column(String(100), default="", server_default="")
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
    connections: Mapped[list[str]] = mapped_column(
        JSON, default=list, server_default="[]"
    )  # provider ids this agent may use through the project's connections, see app/connections.py
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
    # http: how the server wants people to sign in, as the id of an auth scheme (app/mcp_auth), or "" for none. The
    # sign in itself is an McpLogin of the project's owner: a tool says how, never holds the credential.
    auth: Mapped[str] = mapped_column(String(20), default="", server_default="")
    description: Mapped[str] = mapped_column(Text, default="", server_default="")  # for people
    # like Agent.path: the file in the config folder is the truth, this row is its identity and a parsed copy
    path: Mapped[str] = mapped_column(String(300), default="", server_default="")
    config_error: Mapped[str] = mapped_column(Text, default="", server_default="")
    last_test: Mapped[dict[str, Any] | None] = mapped_column(
        JSON, default=None
    )  # the latest connection test: {"ok", "message", "tools", "at"}
    created_at: Mapped[datetime] = mapped_column(UtcDateTime(), default=utcnow)
