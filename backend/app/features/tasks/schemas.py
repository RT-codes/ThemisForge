from datetime import datetime
from typing import Any, Literal, Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator

from app.execution.harnesses.types import AgentHarness
from app.features.tasks.scheduling import validate_cron
from app.persistence.models import AttemptStatus, ScheduleKind, TaskStatus

MAX_STAGES = 20  # workflows one task can play in a row


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
    harness: Literal["", AgentHarness, "workflow"] = ""
    # the workflows to play, in order, when harness is "workflow" (each is a stage of the task)
    workflow_ids: list[int] = Field(default_factory=list, max_length=MAX_STAGES)
    agent_id: int | None = None  # the agent that does it; its harness replaces the one above
    # the automation guard for this task; left out: the project's (see app/features/projects/automation.py)
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

    # Published OpenAPI component identity predates the package organization.
    __module__ = "app.schemas"

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
    harness: Literal["", AgentHarness, "workflow"] | None = None
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
