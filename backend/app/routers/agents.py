"""Agents of a project: a name, a role, instructions, a harness and the cell and folders they run with."""

from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from ..deps import CurrentUser, SessionDep
from ..harness import CATALOG
from ..models import Agent, Task, TaskStatus, Volume
from ..profiles import ProfileOverrides
from ..volumes import MountRef
from .projects import _bad, _project

router = APIRouter(tags=["agents"])


def _clean_model(v: str) -> str:
    v = v.strip()
    if v and (v.startswith("-") or any(c.isspace() or c in "'\"$`\\;&|<>" for c in v)):
        raise ValueError("Invalid model name")
    return v


class AgentIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    role: str = Field(default="", max_length=200)
    description: str = Field(default="", max_length=2000)
    instructions: str = Field(default="", max_length=20_000)
    harness: Literal["codex"] = "codex"
    model: str = Field(default="", max_length=100)  # empty: the model in Settings
    reasoning_effort: Literal["", "low", "medium", "high"] = ""  # empty: the effort in Settings
    cell_profile: ProfileOverrides | None = None
    mounts: list[MountRef] = Field(default_factory=list, max_length=50)

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
        return _clean_model(v)


class AgentPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    role: str | None = Field(default=None, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    instructions: str | None = Field(default=None, max_length=20_000)
    harness: Literal["codex"] | None = None
    model: str | None = Field(default=None, max_length=100)
    reasoning_effort: Literal["", "low", "medium", "high"] | None = None
    cell_profile: ProfileOverrides | None = None  # sent as null: back to the project's cell
    mounts: list[MountRef] | None = Field(default=None, max_length=50)

    @field_validator("model")
    @classmethod
    def valid_model(cls, v: str | None) -> str | None:
        return None if v is None else _clean_model(v)


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
    created_at: datetime
    updated_at: datetime


class HarnessOut(BaseModel):
    id: str
    label: str
    description: str
    supports_skills: bool
    supports_mcp: bool


async def _agent(session, agent_id: int, user) -> Agent:
    agent = await session.get(Agent, agent_id)
    if agent is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Agent not found")
    await _project(session, agent.project_id, user)
    return agent


async def _mounts(session, project_id: int, refs: list[MountRef]) -> list[dict]:
    """The folders an agent mounts: each must belong to the project. Asking for one twice keeps the last."""
    by_id = {r.volume_id: r for r in refs}
    if by_id:
        found = set(
            await session.scalars(
                select(Volume.id).where(Volume.project_id == project_id, Volume.id.in_(list(by_id)))
            )
        )
        if missing := set(by_id) - found:
            raise _bad(f"Folder {min(missing)} does not exist in this project")
    return [r.model_dump() for r in by_id.values()]


@router.get("/harnesses", response_model=list[HarnessOut])
async def list_harnesses(_: CurrentUser) -> list[HarnessOut]:
    return [HarnessOut(**vars(h)) for h in CATALOG]


@router.get("/projects/{project_id}/agents", response_model=list[AgentOut])
async def list_agents(project_id: int, session: SessionDep, user: CurrentUser) -> list[Agent]:
    await _project(session, project_id, user)
    return list(
        (
            await session.scalars(select(Agent).where(Agent.project_id == project_id).order_by(Agent.name))
        ).all()
    )


@router.post("/projects/{project_id}/agents", response_model=AgentOut, status_code=status.HTTP_201_CREATED)
async def create_agent(project_id: int, body: AgentIn, session: SessionDep, user: CurrentUser) -> Agent:
    await _project(session, project_id, user)
    agent = Agent(
        project_id=project_id,
        name=body.name,
        role=body.role,
        description=body.description,
        instructions=body.instructions,
        harness=body.harness,
        model=body.model,
        reasoning_effort=body.reasoning_effort,
        cell_profile=body.cell_profile.clean() if body.cell_profile else None,
        mounts=await _mounts(session, project_id, body.mounts),
    )
    session.add(agent)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT, "This project already has an agent with that name"
        ) from None
    return agent


@router.get("/agents/{agent_id}", response_model=AgentOut)
async def get_agent(agent_id: int, session: SessionDep, user: CurrentUser) -> Agent:
    return await _agent(session, agent_id, user)


@router.patch("/agents/{agent_id}", response_model=AgentOut)
async def update_agent(agent_id: int, body: AgentPatch, session: SessionDep, user: CurrentUser) -> Agent:
    agent = await _agent(session, agent_id, user)
    fields = body.model_fields_set
    for key in ("name", "role", "description", "instructions", "harness", "model", "reasoning_effort"):
        value = getattr(body, key)
        if key in fields and value is not None:
            setattr(agent, key, value.strip() if key in ("name", "role") else value)
    if not agent.name:
        raise _bad("Name cannot be empty")
    if "cell_profile" in fields:
        agent.cell_profile = body.cell_profile.clean() if body.cell_profile else None
    if "mounts" in fields and body.mounts is not None:
        agent.mounts = await _mounts(session, agent.project_id, body.mounts)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT, "This project already has an agent with that name"
        ) from None
    return agent


@router.delete("/agents/{agent_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_agent(agent_id: int, session: SessionDep, user: CurrentUser) -> None:
    agent = await _agent(session, agent_id, user)
    running = await session.scalar(
        select(func.count()).where(Task.agent_id == agent.id, Task.status == TaskStatus.RUNNING)
    )
    if running:
        raise HTTPException(status.HTTP_409_CONFLICT, "This agent is running a task. Cancel it first.")
    await session.delete(agent)
    await session.commit()
