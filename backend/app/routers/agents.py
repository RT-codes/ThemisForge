"""Agents of a project: a name, a role, instructions, a harness and the cell and folders they run with."""

from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from .. import project_config
from .. import skills as skill_store
from ..app_settings import load_settings
from ..deps import CurrentUser, SessionDep
from ..harness import CATALOG, clean_model_name
from ..models import Agent, McpServer, Project, Secret, Task, TaskStatus, Volume
from ..profiles import ProfileOverrides
from ..toolcheck import image_for, missing_commands
from ..volumes import MountRef
from .projects import _bad, _project

router = APIRouter(tags=["agents"])


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
    skills: list[str] = Field(default_factory=list, max_length=50)  # skill names, see app/skills.py
    mcp_servers: list[int] = Field(default_factory=list, max_length=50)  # tool servers of the project
    secrets: list[int] = Field(
        default_factory=list, max_length=50
    )  # keys, available to the agent as variables

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
    harness: Literal["codex"] | None = None
    model: str | None = Field(default=None, max_length=100)
    reasoning_effort: Literal["", "low", "medium", "high"] | None = None
    cell_profile: ProfileOverrides | None = None  # sent as null: back to the project's cell
    mounts: list[MountRef] | None = Field(default=None, max_length=50)
    skills: list[str] | None = Field(default=None, max_length=50)
    mcp_servers: list[int] | None = Field(default=None, max_length=50)
    secrets: list[int] | None = Field(default=None, max_length=50)

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
    path: str  # the agent's file in the project's config folder
    config_error: str  # why that file cannot be used right now ("" when it is fine)
    created_at: datetime
    updated_at: datetime


class CheckIn(BaseModel):
    harness: Literal["codex"] = "codex"
    cell_profile: ProfileOverrides | None = None
    mcp_servers: list[int] = Field(default_factory=list, max_length=50)


class CheckOut(BaseModel):
    image: str  # the image the agent would run in
    warnings: list[str]


class HarnessOut(BaseModel):
    id: str
    label: str
    description: str
    supports_skills: bool
    supports_mcp: bool
    supports_keys: bool


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
                # the config folder is never mounted: it is where agents are set up
                select(Volume.id).where(
                    Volume.project_id == project_id, Volume.id.in_(list(by_id)), Volume.kind != "config"
                )
            )
        )
        if missing := set(by_id) - found:
            raise _bad(f"Folder {min(missing)} does not exist in this project")
    return [r.model_dump() for r in by_id.values()]


async def _capabilities(session, project_id: int, body, user, before: Agent | None = None) -> dict:
    """Checks and returns the skills, tool servers and keys an agent is given (only what the request sets).

    Skills and tool servers must exist in the project, keys must exist, and only an administrator may change which
    keys an agent has, because a key is paid for or trusted by the whole installation."""
    out: dict = {}
    if body.skills is not None:
        names = list(dict.fromkeys(body.skills))
        if gone := skill_store.missing(project_id, names):
            raise _bad(f"The skill '{gone[0]}' does not exist in this project")
        out["skills"] = names
    if body.mcp_servers is not None:
        ids = list(dict.fromkeys(body.mcp_servers))
        found = set(
            await session.scalars(
                select(McpServer.id).where(McpServer.project_id == project_id, McpServer.id.in_(ids))
            )
        )
        if gone := set(ids) - found:
            raise _bad(f"Tool {min(gone)} does not exist in this project")
        out["mcp_servers"] = ids
    if body.secrets is not None:
        ids = list(dict.fromkeys(body.secrets))
        found = set(await session.scalars(select(Secret.id).where(Secret.id.in_(ids)))) if ids else set()
        if gone := set(ids) - found:
            raise _bad(f"Key {min(gone)} does not exist")
        if set(ids) != set(before.secrets if before else []) and not user.is_admin:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Only an administrator can give an agent keys")
        out["secrets"] = ids
    return out


@router.post("/projects/{project_id}/agents/check", response_model=CheckOut)
async def check_agent_tools(
    project_id: int, body: CheckIn, session: SessionDep, user: CurrentUser
) -> CheckOut:
    """Before saving: would the agent's tool servers start in the image it will run in?"""
    project: Project = await _project(session, project_id, user)
    cfg = await load_settings(session)
    image = image_for(project, cfg, body.harness, body.cell_profile.clean() if body.cell_profile else None)
    commands = {}
    if body.mcp_servers:
        rows = await session.scalars(
            select(McpServer).where(
                McpServer.project_id == project_id,
                McpServer.id.in_(body.mcp_servers),
                McpServer.kind == "stdio",
            )
        )
        commands = {r.name: r.command for r in rows}
    return CheckOut(image=image, warnings=await missing_commands(image, commands, cfg.docker_host))


@router.get("/harnesses", response_model=list[HarnessOut])
async def list_harnesses(_: CurrentUser) -> list[HarnessOut]:
    return [HarnessOut(**vars(h)) for h in CATALOG]


@router.get("/projects/{project_id}/agents", response_model=list[AgentOut])
async def list_agents(project_id: int, session: SessionDep, user: CurrentUser) -> list[Agent]:
    await _project(session, project_id, user)
    await project_config.sync_project(
        session, project_id
    )  # a file may have been edited in the Files page or on disk
    return list(
        (
            await session.scalars(select(Agent).where(Agent.project_id == project_id).order_by(Agent.name))
        ).all()
    )


@router.post("/projects/{project_id}/agents", response_model=AgentOut, status_code=status.HTTP_201_CREATED)
async def create_agent(project_id: int, body: AgentIn, session: SessionDep, user: CurrentUser) -> Agent:
    await _project(session, project_id, user)
    async with project_config.lock:
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
            **await _capabilities(session, project_id, body, user),
        )
        session.add(agent)
        await _save(session, agent)
    return agent


async def _save(session, agent: Agent, *, renamed: bool = False) -> None:
    """Commits an agent row together with its file (the caller holds the config lock). The row goes first, so a name
    that is taken is refused before any file is written."""
    try:
        await session.flush()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT, "This project already has an agent with that name"
        ) from None
    try:
        await project_config.write_agent(session, agent, renamed=renamed)
        await session.commit()
    except BaseException:
        await session.rollback()
        raise


@router.get("/agents/{agent_id}", response_model=AgentOut)
async def get_agent(agent_id: int, session: SessionDep, user: CurrentUser) -> Agent:
    agent = await _agent(session, agent_id, user)
    await project_config.sync_project(session, agent.project_id)
    await session.refresh(agent)
    return agent


@router.patch("/agents/{agent_id}", response_model=AgentOut)
async def update_agent(agent_id: int, body: AgentPatch, session: SessionDep, user: CurrentUser) -> Agent:
    agent = await _agent(session, agent_id, user)
    async with project_config.lock:
        await session.refresh(agent)  # a sync may have changed it since it was loaded
        return await _update(session, agent, body, user)


async def _update(session, agent: Agent, body: AgentPatch, user) -> Agent:
    old_name = agent.name
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
    for key, value in (await _capabilities(session, agent.project_id, body, user, before=agent)).items():
        setattr(agent, key, value)
    await _save(session, agent, renamed=agent.name != old_name)
    return agent


@router.delete("/agents/{agent_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_agent(agent_id: int, session: SessionDep, user: CurrentUser) -> None:
    agent = await _agent(session, agent_id, user)
    running = await session.scalar(
        select(func.count()).where(Task.agent_id == agent.id, Task.status == TaskStatus.RUNNING)
    )
    if running:
        raise HTTPException(status.HTTP_409_CONFLICT, "This agent is running a task. Cancel it first.")
    async with project_config.lock:
        project_config.remove_agent_file(agent)
        await session.delete(agent)
        await session.commit()
