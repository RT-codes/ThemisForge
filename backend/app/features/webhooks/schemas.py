from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.execution.harnesses.types import AgentHarness
from app.features.tasks.schemas import MAX_STAGES
from app.persistence.models import TaskStatus


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
    harness: Literal["", AgentHarness, "workflow"] = ""
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
    harness: Literal["", AgentHarness, "workflow"] | None = None
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
