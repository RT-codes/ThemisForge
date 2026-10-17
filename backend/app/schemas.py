import re
from datetime import datetime
from typing import Annotated, Any, Literal, Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

from .automation import AutomationOverrides
from .models import AttemptStatus, ScheduleKind, TaskStatus
from .profiles import ProfileOverrides
from .properties import HEX_COLOR, PropertyDef
from .scheduling import validate_cron

MAX_STAGES = 20  # workflows one task can play in a row


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    name: str
    is_admin: bool


class LoginIn(BaseModel):
    email: EmailStr
    password: str

    @field_validator("email")
    @classmethod
    def lower_email(cls, v: str) -> str:
        return v.lower()


class RegisterIn(LoginIn):
    name: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=8, max_length=128)


class SetupOut(BaseModel):
    needs_admin: bool  # no account exists yet: the next registration creates the administrator


# access requests and invites


class AccessRequestIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    email: EmailStr
    reason: str = Field(min_length=1, max_length=1000)

    @field_validator("email")
    @classmethod
    def lower_email(cls, v: str) -> str:
        return v.lower()

    @field_validator("name", "reason")
    @classmethod
    def strip_text(cls, v: str) -> str:
        if not (v := v.strip()):
            raise ValueError("This field cannot be empty")
        return v


class AccessRequestOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    email: str
    reason: str
    status: str
    created_at: datetime
    decided_at: datetime | None


class InviteIn(BaseModel):
    email: EmailStr

    @field_validator("email")
    @classmethod
    def lower_email(cls, v: str) -> str:
        return v.lower()


class InviteOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    created_at: datetime
    expires_at: datetime


class InviteCreated(InviteOut):
    token: str  # shown once: only its hash is stored


class InviteInfo(BaseModel):
    email: str


class AcceptInviteIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=8, max_length=128)


# projects

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
    halted_at: datetime | None  # set while nothing in the project may start (see app/halt.py)
    created_at: datetime


class ProjectSummary(ProjectOut):
    task_counts: dict[str, int]
    next_run_at: datetime | None


# workspaces and boards


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


# tasks


class _ScheduleFields(BaseModel):
    schedule_kind: ScheduleKind = ScheduleKind.NONE
    cron: str | None = None
    run_at: AwareDatetime | None = None


def check_schedule(
    kind: ScheduleKind, cron: str | None, run_at: datetime | None
) -> tuple[str | None, datetime | None]:
    if kind == ScheduleKind.CRON:
        if not cron:
            raise ValueError("A recurring schedule needs a cron expression")
        return validate_cron(cron), None
    if kind == ScheduleKind.ONCE:
        if run_at is None:
            raise ValueError("A one-off schedule needs a date and time")
        return None, run_at
    return None, None


class TaskIn(_ScheduleFields):
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=20_000)
    status: str = TaskStatus.BACKLOG  # a built-in status, or "custom:<id>" of the board (checked against it)
    board_id: int | None = None  # left out: the project's first board
    properties: dict[str, Any] = Field(default_factory=dict)
    review_on_success: bool = False
    harness: Literal["", "codex", "workflow"] = ""
    # the workflows to play, in order, when harness is "workflow" (each is a stage of the task)
    workflow_ids: list[int] = Field(default_factory=list, max_length=MAX_STAGES)
    agent_id: int | None = None  # the agent that does it; its harness replaces the one above
    # the automation guard for this task; left out: the project's (see app/automation.py)
    cooldown_seconds: int | None = Field(default=None, ge=0, le=3600)
    max_hops: int | None = Field(default=None, ge=1, le=100)

    @field_validator("title")
    @classmethod
    def strip_title(cls, v: str) -> str:
        if not (v := v.strip()):
            raise ValueError("Title cannot be empty")
        return v

    @field_validator("status")
    @classmethod
    def not_running(cls, v: str) -> str:
        if v == TaskStatus.RUNNING:
            raise ValueError("Tasks start running through the scheduler (use 'Run now')")
        return v

    @model_validator(mode="after")
    def validate_schedule(self) -> Self:
        self.cron, self.run_at = check_schedule(self.schedule_kind, self.cron, self.run_at)
        return self


class MoveIn(BaseModel):
    """Send a task to a board (and a status on it)."""

    board_id: int
    status: str | None = None  # left out: the same status when the board has it, else Backlog
    position: float | None = None  # left out: the end of the column


class SpawnIn(BaseModel):
    """Create a follow-up of a task on a board."""

    board_id: int
    title: str | None = Field(
        default=None, min_length=1, max_length=200
    )  # left out: "Follow-up: <its title>"
    description: str = Field(default="", max_length=20_000)
    status: str | None = None  # left out: Backlog


class TaskPatch(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=20_000)
    status: str | None = None
    position: float | None = None
    properties: dict[str, Any] | None = None
    schedule_kind: ScheduleKind | None = None
    cron: str | None = None
    run_at: AwareDatetime | None = None
    review_on_success: bool | None = None
    harness: Literal["", "codex", "workflow"] | None = None
    workflow_ids: list[int] | None = Field(default=None, max_length=MAX_STAGES)
    agent_id: int | None = None
    cooldown_seconds: int | None = Field(default=None, ge=0, le=3600)  # sent as null: the project's
    max_hops: int | None = Field(default=None, ge=1, le=100)

    @field_validator("status")
    @classmethod
    def not_running(cls, v: str | None) -> str | None:
        if v == TaskStatus.RUNNING:
            raise ValueError("Tasks start running through the scheduler (use 'Run now')")
        return v


class TaskSnapshot(BaseModel):
    """What is kept of a task that was deleted (see ProjectEvent)."""

    model_config = ConfigDict(from_attributes=True)

    title: str
    description: str
    status: str
    properties: dict[str, Any]
    schedule_kind: ScheduleKind
    cron: str | None
    run_at: datetime | None
    review_on_success: bool
    harness: str
    workflow_ids: list[int] = Field(default_factory=list)  # set by the router: they live in TaskStage rows
    agent_id: int | None


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


class TaskWorkflowRun(BaseModel):
    """A workflow run that this task started and that is still going (what the board shows on the card)."""

    run_id: int
    workflow_id: int
    workflow_name: str
    step: str  # the node it is working on right now ("" between nodes)


class TaskStageOut(BaseModel):
    """One workflow of a task, and how far its latest attempt got with it."""

    workflow_id: int
    workflow_name: str
    # "pending" until a run of this stage starts, then the run's own status
    status: Literal["pending", "running", "succeeded", "failed", "cancelled"]
    run_id: int | None


class TaskOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    board_id: int
    origin_task_id: int | None  # the task this one was spawned from
    title: str
    description: str
    status: str
    position: float
    properties: dict[str, Any]
    schedule_kind: ScheduleKind
    cron: str | None
    run_at: datetime | None
    next_run_at: datetime | None
    last_run_at: datetime | None
    review_on_success: bool
    harness: str
    agent_id: int | None
    internal: bool  # the step of a workflow's Agent node: shown on a board only when asked for
    hops: int  # how many times in a row automation moved or made this task
    cooldown_seconds: int | None
    max_hops: int | None
    created_at: datetime
    updated_at: datetime
    last_attempt_status: AttemptStatus | None = None
    last_failure_reason: str = ""  # why the latest attempt failed, for the card; empty when it did not
    workflow_run: TaskWorkflowRun | None = None
    stages: list[TaskStageOut] = Field(default_factory=list)  # filled in by the router, in play order


class AttemptOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    task_id: int
    status: AttemptStatus
    started_at: datetime
    finished_at: datetime | None
    exit_code: int | None
    workflow_run_id: int | None = None  # the run that did the work, when the task played a workflow
    # what it used, see Attempt.harness: null when it ran no harness or the harness reported nothing
    harness: str | None = None
    model: str | None = None
    billing: Literal["subscription", "api"] | None = None
    input_tokens: int | None = None
    cached_input_tokens: int | None = None
    output_tokens: int | None = None
    reasoning_output_tokens: int | None = None


class UsageRow(BaseModel):
    """What the attempts of one harness and model used, added up (see app/usage.py)."""

    harness: str
    model: str
    billing: Literal["subscription", "api"]
    attempts: int
    input_tokens: int
    cached_input_tokens: int  # part of input_tokens
    output_tokens: int
    reasoning_output_tokens: int  # part of output_tokens


class AttemptFailure(BaseModel):
    """Why an attempt failed, see Attempt.failure."""

    source: Literal[
        "themis", "agent"
    ]  # who worked it out: Themis from what it saw, or the agent that stopped
    reason: str
    action: str = ""  # what the person can change; empty when nobody knows
    tail: str = ""  # the last lines of the log of what failed


class AttemptDetail(AttemptOut):
    workflow_id: int | None = None  # the workflow behind workflow_run_id, so the UI can link to the run
    workdir_id: int | None = (
        None  # the attempt whose working folder this one used (its own id unless continued)
    )
    changes: dict | None = None  # what the cell added, changed and removed there, see Attempt.changes
    failure: AttemptFailure | None = None
    log: str
    result: str


class ScheduledRun(BaseModel):
    task_id: int
    title: str
    at: datetime
    recurring: bool


# secrets


class SecretIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    kind: str = Field(default="custom", min_length=1, max_length=50)
    value: str = Field(min_length=1, max_length=10_000)


class SecretOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    kind: str
    hint: str
    created_at: datetime


# webhooks (see app/webhooks.py)


class WebhookRule(BaseModel):
    """A condition on the message: the value at `path` must be one of `equals`, or merely present when none are listed."""

    model_config = ConfigDict(extra="forbid")

    path: str = Field(min_length=1, max_length=100)
    equals: list[Annotated[str, Field(max_length=100)]] = Field(default_factory=list, max_length=20)

    @field_validator("path")
    @classmethod
    def strip_path(cls, v: str) -> str:
        if not (v := v.strip()):
            raise ValueError("A rule needs the name of a value in the message")
        return v


class WebhookFields(BaseModel):
    """What the owner sets. The sender cannot change any of it: it only supplies the message."""

    name: str = Field(min_length=1, max_length=60)
    enabled: bool = True
    board_id: int | None = None  # left out: the project's first board
    status: str = TaskStatus.BACKLOG  # where the tasks land: a built-in status or "custom:<id>" of the board
    title_template: str = Field(default="", max_length=200)
    description_template: str = Field(default="", max_length=20_000)
    rules: list[WebhookRule] = Field(default_factory=list, max_length=10)
    harness: Literal["", "codex", "workflow"] = ""
    agent_id: int | None = None
    workflow_ids: list[int] = Field(default_factory=list, max_length=MAX_STAGES)
    properties: dict[str, Any] = Field(default_factory=dict)
    review_on_success: bool = False

    @field_validator("name")
    @classmethod
    def strip_name(cls, v: str) -> str:
        if not (v := v.strip()):
            raise ValueError("Name cannot be empty")
        return v

    @field_validator("status")
    @classmethod
    def not_running(cls, v: str) -> str:
        if v == TaskStatus.RUNNING:
            raise ValueError("Tasks start running through the scheduler: use Ready")
        return v


class WebhookIn(WebhookFields):
    pass


class WebhookPatch(BaseModel):
    """Only what is sent changes."""

    name: str | None = Field(default=None, min_length=1, max_length=60)
    enabled: bool | None = None
    board_id: int | None = None
    status: str | None = None
    title_template: str | None = Field(default=None, max_length=200)
    description_template: str | None = Field(default=None, max_length=20_000)
    rules: list[WebhookRule] | None = Field(default=None, max_length=10)
    harness: Literal["", "codex", "workflow"] | None = None
    agent_id: int | None = None
    workflow_ids: list[int] | None = Field(default=None, max_length=MAX_STAGES)
    properties: dict[str, Any] | None = None
    review_on_success: bool | None = None


class WebhookOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    name: str
    enabled: bool
    token_hint: str  # the last characters of the secret in the address; the rest is never shown again
    board_id: int | None
    status: str
    title_template: str
    description_template: str
    rules: list[WebhookRule]
    harness: str
    agent_id: int | None
    workflow_ids: list[int]
    properties: dict[str, Any]
    review_on_success: bool
    last_received_at: datetime | None
    created_at: datetime
    problem: str = (
        ""  # why a message would be refused right now (a board that is gone...), empty when all is well
    )


class WebhookCreated(WebhookOut):
    """A new address, or a new secret for one: the only time the whole path is shown."""

    path: str


class DeliveryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    received_at: datetime
    outcome: str
    detail: str
    task_id: int | None
    event: str
    payload: str


class DeliveryResult(BaseModel):
    """What the sender is told."""

    outcome: str
    detail: str = ""
    task_id: int | None = None


class WebhookTestIn(BaseModel):
    """A made-up message to try the webhook with. It makes a real task, like a message from outside."""

    payload: str = Field(
        default='{"title": "A test message", "description": "Sent from Themis."}', max_length=50_000
    )
    event: str = Field(default="test", max_length=60)


# notifications out


class NotificationIn(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    kind: str = Field(max_length=20)
    # what the kind needs (see notifications.KINDS), by field name; stored encrypted and never returned
    config: dict[str, str] = Field(default_factory=dict)
    events: list[str] = Field(default_factory=lambda: ["failed", "attention"], max_length=10)
    enabled: bool = True

    @field_validator("name")
    @classmethod
    def strip_name(cls, v: str) -> str:
        if not (v := v.strip()):
            raise ValueError("Name cannot be empty")
        return v


class NotificationPatch(BaseModel):
    """Only what is sent changes. `config` replaces the whole secret (it is never shown, so it cannot be edited)."""

    name: str | None = Field(default=None, min_length=1, max_length=60)
    config: dict[str, str] | None = None
    events: list[str] | None = Field(default=None, max_length=10)
    enabled: bool | None = None


class NotificationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    name: str
    kind: str
    enabled: bool
    hint: str  # the end of the secret, to tell targets apart; the rest is never shown
    events: list[str]
    last_sent_at: datetime | None
    last_error: str
    created_at: datetime


class NotificationTestOut(BaseModel):
    ok: bool
    detail: str = ""


class NotificationFieldOut(BaseModel):
    name: str
    label: str
    placeholder: str
    help: str


class NotificationKindOut(BaseModel):
    key: str
    label: str
    description: str
    fields: list[NotificationFieldOut]


class NotificationEventOut(BaseModel):
    key: str
    label: str


class NotificationOptions(BaseModel):
    """What a target can be: the services Themis can talk to and the events it can listen for. The form is built from
    this, so a new service needs no change in the app."""

    kinds: list[NotificationKindOut]
    events: list[NotificationEventOut]


# control tokens: how an outside agent gets into a project through MCP (see app/control.py)


class ControlTokenIn(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    scope: Literal["read", "write"] = "read"

    @field_validator("name")
    @classmethod
    def _name(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("A token needs a name")
        return v.strip()


class ControlTokenOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int | None  # None: reaches all of the owner's projects
    name: str
    scope: Literal["read", "write"]
    token_hint: str  # the last characters, to tell tokens apart
    last_used_at: datetime | None
    created_at: datetime


class ControlConnect(BaseModel):
    """Everything an owner pastes into an agent to connect it, with the secret in it."""

    url: str
    token: str
    claude_code: str  # the command that adds this project to Claude Code
    config_json: str  # the same for clients that read an mcpServers file
