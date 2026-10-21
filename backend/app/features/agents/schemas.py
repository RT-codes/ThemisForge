from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.execution.harnesses.catalog import clean_model_name
from app.execution.harnesses.types import AgentHarness, Effort
from app.execution.profiles import ProfileOverrides
from app.features.storage.volumes import MountRef


class AgentIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    role: str = Field(default="", max_length=200)
    description: str = Field(default="", max_length=2000)
    instructions: str = Field(default="", max_length=20_000)
    harness: AgentHarness = "codex"
    model: str = Field(default="", max_length=100)  # empty: the model in Settings
    reasoning_effort: Effort | Literal[""] = ""  # empty: the effort in Settings
    cell_profile: ProfileOverrides | None = None
    mounts: list[MountRef] = Field(default_factory=list, max_length=50)
    skills: list[str] = Field(
        default_factory=list, max_length=50
    )  # skill names, see app/features/agents/skills.py
    mcp_servers: list[int] = Field(default_factory=list, max_length=50)  # tool servers of the project
    secrets: list[int] = Field(
        default_factory=list, max_length=50
    )  # keys, available to the agent as variables
    connections: list[str] = Field(
        default_factory=list, max_length=50
    )  # provider ids, see app/features/connections/service.py

    @field_validator("name")
    @classmethod
    def strip_name(cls, v: str) -> str:
        if not (v := v.strip()):
            raise ValueError("Name cannot be empty")
        return v

    @field_validator("role")
    @classmethod
    def strip_role(cls, v: str) -> str:
        return v.strip()

    @field_validator("model")
    @classmethod
    def valid_model(cls, v: str) -> str:
        return clean_model_name(v)


class AgentPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    role: str | None = Field(default=None, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    instructions: str | None = Field(default=None, max_length=20_000)
    harness: AgentHarness | None = None
    model: str | None = Field(default=None, max_length=100)
    reasoning_effort: Effort | Literal[""] | None = None
    cell_profile: ProfileOverrides | None = None  # sent as null: back to the project's cell
    mounts: list[MountRef] | None = Field(default=None, max_length=50)
    skills: list[str] | None = Field(default=None, max_length=50)
    mcp_servers: list[int] | None = Field(default=None, max_length=50)
    secrets: list[int] | None = Field(default=None, max_length=50)
    connections: list[str] | None = Field(default=None, max_length=50)

    @field_validator("model")
    @classmethod
    def valid_model(cls, v: str | None) -> str | None:
        return None if v is None else clean_model_name(v)


class AgentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    name: str
    role: str
    description: str
    instructions: str
    harness: str
    model: str
    reasoning_effort: str
    cell_profile: dict[str, Any] | None
    mounts: list[MountRef]
    skills: list[str]
    mcp_servers: list[int]
    secrets: list[int]
    connections: list[str]
    path: str  # the agent's file in the project's config folder
    config_error: str  # why that file cannot be used right now ("" when it is fine)
    created_at: datetime
    updated_at: datetime


class CheckIn(BaseModel):
    harness: AgentHarness = "codex"
    cell_profile: ProfileOverrides | None = None
    mcp_servers: list[int] = Field(default_factory=list, max_length=50)


class CheckOut(BaseModel):
    image: str  # the image the agent would run in
    warnings: list[str]


class ModelOut(BaseModel):
    id: str
    label: str
    efforts: list[str]
    default_effort: str


class HarnessOut(BaseModel):
    id: str
    label: str
    description: str
    supports_skills: bool
    supports_mcp: bool
    supports_keys: bool
    models: list[ModelOut]
    # what an empty model and an empty effort mean (the ones in Settings), so the editors can name them
    default_model: str
    default_effort: str
