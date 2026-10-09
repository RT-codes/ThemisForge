from datetime import datetime
from typing import Any, Literal, Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

from .models import AttemptStatus, ScheduleKind, TaskStatus
from .profiles import ProfileOverrides
from .properties import HEX_COLOR, PropertyDef
from .scheduling import validate_cron


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


class ProjectIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: str = Field(default="", max_length=2000)
    cell_profile: ProfileOverrides | None = None  # overrides of the global cell defaults

    @field_validator("name")
    @classmethod
    def strip_name(cls, v: str) -> str:
        if not (v := v.strip()):
            raise ValueError("Name cannot be empty")
        return v


class ProjectPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=2000)
    properties: list[PropertyDef] | None = None
    cell_profile: ProfileOverrides | None = None  # sent as null: back to the global defaults


class ProjectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str
    properties: list[PropertyDef]
    cell_profile: dict[str, Any] | None
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

    _strip_name = field_validator("name")(_name)


class WorkspacePatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=60)
    purpose: str | None = Field(default=None, max_length=200)
    description: str | None = Field(default=None, max_length=5000)
    position: float | None = None

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

    _strip_name = field_validator("name")(_name)
    _check_color = field_validator("color")(_color)


class StatusPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=40)
    color: str | None = None  # sent as null: no colour
    index: int | None = Field(default=None, ge=0)

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


class BoardOut(BaseModel):
    id: int
    project_id: int
    workspace_id: int
    name: str
    purpose: str
    position: float
    columns: list[ColumnOut]
    created_at: datetime


class WorkspaceOut(BaseModel):
    id: int
    project_id: int
    name: str
    purpose: str
    description: str
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
    workflow_id: int | None = None  # the workflow to play when harness is "workflow"
    agent_id: int | None = None  # the agent that does it; its harness replaces the one above

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
    workflow_id: int | None = None
    agent_id: int | None = None

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
    workflow_id: int | None
    agent_id: int | None


class ProjectEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    kind: str
    title: str
    actor: str
    data: dict[str, Any]
    created_at: datetime


class TaskWorkflowRun(BaseModel):
    """A workflow run that this task started and that is still going (what the board shows on the card)."""

    run_id: int
    workflow_id: int
    workflow_name: str
    step: str  # the node it is working on right now ("" between nodes)


class TaskOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    board_id: int
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
    workflow_id: int | None
    agent_id: int | None
    created_at: datetime
    updated_at: datetime
    last_attempt_status: AttemptStatus | None = None
    workflow_run: TaskWorkflowRun | None = None


class AttemptOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    task_id: int
    status: AttemptStatus
    started_at: datetime
    finished_at: datetime | None
    exit_code: int | None
    workflow_run_id: int | None = None  # the run that did the work, when the task played a workflow


class AttemptDetail(AttemptOut):
    workflow_id: int | None = None  # the workflow behind workflow_run_id, so the UI can link to the run
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
